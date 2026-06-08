from __future__ import annotations
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import csv, io, json
 
from auth import is_admin
from services.source_registry import get_source_status
from database import (
    get_db, PokemonSet, Product, Card,
    CollectionItem, WatchlistItem, AlertLog,
    PriceHistory, NotificationConfig,
)
from services.fx_service import get_usd_jpy
from services import search_service
import poller
 
router = APIRouter()
templates = Jinja2Templates(directory="templates")
 
 
def _ctx(request: Request, **kwargs):
    """Base template context — always includes admin status."""
    return {"request": request, "admin": is_admin(request), **kwargs}
 
 
# ── Dashboard ─────────────────────────────────────────────────
 
@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    fx = await get_usd_jpy()
 
    # 24h lowest per watched product
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=24)
 
    products = (await db.execute(
        select(Product).where(Product.is_active == True).limit(12)  # noqa
    )).scalars().all()
 
    summary = []
    for p in products:
        ph = (await db.execute(
            select(PriceHistory)
            .where(
                PriceHistory.item_type == "product",
                PriceHistory.item_id == p.id,
                PriceHistory.ts >= cutoff,
            )
            .order_by(PriceHistory.price_usd.asc())
            .limit(1)
        )).scalar_one_or_none()
 
        lowest_usd = ph.price_usd if ph else None
        msrp_diff  = round(lowest_usd - (p.msrp_usd or 0), 2) if lowest_usd and p.msrp_usd else None
 
        summary.append({
            "id":          p.id,
            "name_en":     p.name_en,
            "name_jp":     p.name_jp or "",
            "product_type": p.product_type,
            "image_url":   p.image_url,
            "msrp_usd":    p.msrp_usd,
            "msrp_jpy":    p.msrp_jpy,
            "lowest_usd":  lowest_usd,
            "lowest_jpy":  round(lowest_usd * fx) if lowest_usd else None,
            "msrp_diff":   msrp_diff,
            "url":         ph.url if ph else None,
            "source":      ph.source if ph else None,
        })
 
    alerts = (await db.execute(
        select(AlertLog).order_by(AlertLog.ts.desc()).limit(5)
    )).scalars().all()
 
    job = poller.scheduler.get_job("price_check")
 
    # Build config warnings for the dashboard banner
    from config import settings as app_settings
    config_warnings = []
    if app_settings.using_default_secret:
        config_warnings.append({
            "title":      "Insecure secret key",
            "message":    "SECRET_KEY is using the default value. Change it in .env before exposing this to the internet.",
            "action":     None, "action_url": None,
        })
    if app_settings.using_default_password:
        config_warnings.append({
            "title":      "Default admin password",
            "message":    "ADMIN_PASSWORD is 'admin'. Change it in .env.",
            "action":     None, "action_url": None,
        })
 
    return templates.TemplateResponse("dashboard.html", _ctx(
        request,
        summary=summary,
        alerts=alerts,
        fx_rate=fx,
        last_run=poller.state.get("last_run"),
        next_run=job.next_run_time if job else None,
        poll_hours=poller.settings.poll_interval_seconds / 3600,
        sources=get_source_status(),
        config_warnings=config_warnings,
    ))
 
 
# ── Sets browser ──────────────────────────────────────────────
 
@router.get("/sets", response_class=HTMLResponse)
async def sets_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    lang: Optional[str] = None,      # "jp" | "en"
    q: Optional[str] = None,
):
    stmt = select(PokemonSet).order_by(PokemonSet.release_date.desc())
    if lang == "jp":
        stmt = stmt.where(PokemonSet.is_japanese == True)   # noqa
    elif lang == "en":
        stmt = stmt.where(PokemonSet.is_japanese == False)  # noqa
    sets = (await db.execute(stmt)).scalars().all()
 
    if q:
        from rapidfuzz import fuzz, process
        names = [s.name_en for s in sets]
        matches = process.extract(q, names, scorer=fuzz.WRatio, limit=20, score_cutoff=60)
        matched_names = {m[0] for m in matches}
        sets = [s for s in sets if s.name_en in matched_names]
 
    return templates.TemplateResponse("sets.html", _ctx(
        request, sets=sets, lang=lang or "all", q=q or ""
    ))
 
 
# ── Set detail ────────────────────────────────────────────────
 
@router.get("/sets/{set_id}", response_class=HTMLResponse)
async def set_detail(set_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(
        select(PokemonSet).where(PokemonSet.id == set_id)
    )).scalar_one_or_none()
    if not s:
        return HTMLResponse("Set not found", status_code=404)
 
    fx = await get_usd_jpy()
    products = (await db.execute(
        select(Product).where(Product.set_id == set_id).order_by(Product.product_type)
    )).scalars().all()
    cards = (await db.execute(
        select(Card).where(Card.set_id == set_id).order_by(Card.card_number)
    )).scalars().all()
 
    # Enrich products with lowest price
    enriched_products = []
    for p in products:
        ph = (await db.execute(
            select(PriceHistory)
            .where(PriceHistory.item_type == "product", PriceHistory.item_id == p.id)
            .order_by(PriceHistory.price_usd.asc()).limit(1)
        )).scalar_one_or_none()
        lowest_usd = ph.price_usd if ph else None
        msrp_diff  = round(lowest_usd - (p.msrp_usd or 0), 2) if lowest_usd and p.msrp_usd else None
        enriched_products.append({
            "id": p.id, "name_en": p.name_en, "name_jp": p.name_jp or "",
            "product_type": p.product_type, "image_url": p.image_url,
            "msrp_usd": p.msrp_usd, "msrp_jpy": p.msrp_jpy,
            "lowest_usd": lowest_usd,
            "lowest_jpy": round(lowest_usd * fx) if lowest_usd else None,
            "msrp_diff": msrp_diff, "url": ph.url if ph else None,
        })
 
    return templates.TemplateResponse("set_detail.html", _ctx(
        request, pokemon_set=s, products=enriched_products, cards=list(cards), fx=fx
    ))
 
 
# ── Special boxes ─────────────────────────────────────────────
 
@router.get("/special-boxes", response_class=HTMLResponse)
async def special_boxes(request: Request, db: AsyncSession = Depends(get_db)):
    fx = await get_usd_jpy()
    specials = (await db.execute(
        select(Product)
        .where(Product.product_type.in_(["special_box", "etb", "gift_set", "promo"]))
        .where(Product.is_active == True)   # noqa
        .order_by(Product.name_en)
    )).scalars().all()
 
    enriched = []
    for p in specials:
        ph = (await db.execute(
            select(PriceHistory)
            .where(PriceHistory.item_type == "product", PriceHistory.item_id == p.id)
            .order_by(PriceHistory.price_usd.asc()).limit(1)
        )).scalar_one_or_none()
        lowest_usd = ph.price_usd if ph else None
        msrp_diff  = round(lowest_usd - (p.msrp_usd or 0), 2) if lowest_usd and p.msrp_usd else None
        enriched.append({
            "id": p.id, "name_en": p.name_en, "name_jp": p.name_jp or "",
            "product_type": p.product_type, "image_url": p.image_url,
            "msrp_usd": p.msrp_usd, "msrp_jpy": p.msrp_jpy,
            "lowest_usd": lowest_usd,
            "lowest_jpy": round(lowest_usd * fx) if lowest_usd else None,
            "msrp_diff": msrp_diff, "url": ph.url if ph else None,
        })
 
    return templates.TemplateResponse("special_boxes.html", _ctx(
        request, products=enriched, fx=fx
    ))
 
 
# ── Search ────────────────────────────────────────────────────
 
@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    results = []
    if q:
        results = search_service.fuzzy_search(q, limit=30)
    index_json = json.dumps(search_service.get_index_json())
    return templates.TemplateResponse("search.html", _ctx(
        request, q=q or "", results=results, index_json=index_json
    ))
 
 
# ── Collection (public read) ──────────────────────────────────
 
@router.get("/collection", response_class=HTMLResponse)
async def collection_page(request: Request, db: AsyncSession = Depends(get_db)):
    fx = await get_usd_jpy()
    items = (await db.execute(select(CollectionItem))).scalars().all()
 
    enriched = []
    for item in items:
        name_en, name_jp, image_url, msrp_usd, msrp_jpy = "", "", None, None, None
        if item.item_type == "product":
            row = (await db.execute(
                select(Product).where(Product.id == item.item_id)
            )).scalar_one_or_none()
            if row:
                name_en, name_jp = row.name_en, row.name_jp or ""
                image_url, msrp_usd, msrp_jpy = row.image_url, row.msrp_usd, row.msrp_jpy
        else:
            row = (await db.execute(
                select(Card).where(Card.id == item.item_id)
            )).scalar_one_or_none()
            if row:
                name_en, name_jp, image_url = row.name_en, row.name_jp or "", row.image_url
 
        ph = (await db.execute(
            select(PriceHistory)
            .where(PriceHistory.item_type == item.item_type, PriceHistory.item_id == item.item_id)
            .order_by(PriceHistory.price_usd.asc()).limit(1)
        )).scalar_one_or_none()
 
        market_usd = ph.price_usd if ph else None
        total_usd  = round(market_usd * item.quantity, 2) if market_usd else None
        grade_label = f"{item.grader} {item.grade}" if item.grader and item.grade else None
 
        enriched.append({
            "id": item.id, "item_type": item.item_type, "item_id": item.item_id,
            "name_en": name_en, "name_jp": name_jp, "image_url": image_url,
            "status": item.status, "grader": item.grader, "grade": item.grade,
            "grade_label": grade_label, "quantity": item.quantity,
            "acquired_price_usd": item.acquired_price_usd,
            "acquired_date": item.acquired_date, "notes": item.notes,
            "market_usd": market_usd,
            "market_jpy": round(market_usd * fx) if market_usd else None,
            "market_url": ph.url if ph else None,
            "msrp_usd": msrp_usd, "msrp_jpy": msrp_jpy,
            "total_value_usd": total_usd,
        })
 
    portfolio_usd = sum(r["total_value_usd"] or 0 for r in enriched)
    return templates.TemplateResponse("collection.html", _ctx(
        request, items=enriched,
        portfolio_usd=round(portfolio_usd, 2),
        portfolio_jpy=round(portfolio_usd * fx),
        fx=fx,
    ))
 
 
# ── Watchlist (public read) ───────────────────────────────────
 
@router.get("/watchlist", response_class=HTMLResponse)
async def watchlist_page(request: Request, db: AsyncSession = Depends(get_db)):
    fx = await get_usd_jpy()
    items = (await db.execute(select(WatchlistItem))).scalars().all()
 
    enriched = []
    for w in items:
        name_en, name_jp, image_url = "", "", None
        if w.item_type == "product":
            row = (await db.execute(
                select(Product).where(Product.id == w.item_id)
            )).scalar_one_or_none()
            if row:
                name_en, name_jp, image_url = row.name_en, row.name_jp or "", row.image_url
        else:
            row = (await db.execute(
                select(Card).where(Card.id == w.item_id)
            )).scalar_one_or_none()
            if row:
                name_en, name_jp, image_url = row.name_en, row.name_jp or "", row.image_url
 
        ph = (await db.execute(
            select(PriceHistory)
            .where(PriceHistory.item_type == w.item_type, PriceHistory.item_id == w.item_id)
            .order_by(PriceHistory.price_usd.asc()).limit(1)
        )).scalar_one_or_none()
 
        current_usd = ph.price_usd if ph else None
        enriched.append({
            "id": w.id, "item_type": w.item_type, "item_id": w.item_id,
            "name_en": name_en, "name_jp": name_jp, "image_url": image_url,
            "target_price_usd": w.target_price_usd,
            "target_price_jpy": round(w.target_price_usd * fx) if w.target_price_usd else None,
            "current_usd": current_usd,
            "current_jpy": round(current_usd * fx) if current_usd else None,
            "is_deal": (current_usd <= w.target_price_usd)
                       if (current_usd and w.target_price_usd) else False,
            "market_url": ph.url if ph else None,
            "notes": w.notes, "added_at": w.added_at,
        })
 
    return templates.TemplateResponse("watchlist.html", _ctx(
        request, items=enriched, fx=fx
    ))
 
 
# ── Alerts ────────────────────────────────────────────────────
 
@router.get("/alerts", response_class=HTMLResponse)
async def alerts_page(request: Request, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(NotificationConfig))).scalar_one_or_none()
    logs = (await db.execute(
        select(AlertLog).order_by(AlertLog.ts.desc()).limit(100)
    )).scalars().all()
    return templates.TemplateResponse("alerts.html", _ctx(
        request, logs=logs, cfg=cfg
    ))
 
 
# ── Admin panel ───────────────────────────────────────────────
 
@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, db: AsyncSession = Depends(get_db)):
    if not is_admin(request):
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/login", status_code=303)
 
    sets = (await db.execute(
        select(PokemonSet).order_by(PokemonSet.name_en)
    )).scalars().all()
    cfg = (await db.execute(select(NotificationConfig))).scalar_one_or_none()
 
    return templates.TemplateResponse("admin.html", _ctx(
        request, sets=list(sets), cfg=cfg
    ))
 
 
# ── Login ─────────────────────────────────────────────────────
 
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: Optional[int] = None):
    return templates.TemplateResponse("login.html", _ctx(request, error=error))
 
 
# ── Export ────────────────────────────────────────────────────
 
@router.get("/collection/export/csv")
async def export_csv(request: Request, db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(CollectionItem))).scalars().all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "item_type", "item_id", "status", "grader", "grade",
        "quantity", "acquired_price_usd", "acquired_date", "notes",
    ])
    for i in items:
        writer.writerow([
            i.id, i.item_type, i.item_id, i.status, i.grader or "",
            i.grade or "", i.quantity, i.acquired_price_usd or "",
            i.acquired_date or "", i.notes or "",
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=collection.csv"},
    )
 
 
@router.get("/collection/export/json")
async def export_json(request: Request, db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(CollectionItem))).scalars().all()
    data = [
        {
            "id": i.id, "item_type": i.item_type, "item_id": i.item_id,
            "status": i.status, "grader": i.grader, "grade": i.grade,
            "quantity": i.quantity, "acquired_price_usd": i.acquired_price_usd,
            "acquired_date": i.acquired_date, "notes": i.notes,
        }
        for i in items
    ]
    return StreamingResponse(
        iter([json.dumps(data, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=collection.json"},
    )
