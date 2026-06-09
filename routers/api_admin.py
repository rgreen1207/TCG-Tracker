from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin
from database import get_db, PokemonSet, Product, Card, NotificationConfig
from services import search_service

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_admin)])


# ── Sets ─────────────────────────────────────────────────────

class SetCreate(BaseModel):
    name_en:      str
    name_jp:      Optional[str] = None
    set_code:     Optional[str] = None
    series:       Optional[str] = None
    release_date: Optional[str] = None
    image_url:    Optional[str] = None
    is_japanese:  bool = True


@router.post("/sets")
async def create_set(body: SetCreate, db: AsyncSession = Depends(get_db)):
    s = PokemonSet(**body.model_dump())
    db.add(s)
    await db.commit()
    await db.refresh(s)
    await search_service.rebuild_index()
    return {"id": s.id}


@router.get("/sets/{set_id}")
async def get_set(set_id: str, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(PokemonSet).where(PokemonSet.id == set_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Set not found")
    return {k: getattr(s, k) for k in ["id", "name_en", "name_jp", "set_code", "series", "release_date", "image_url", "is_japanese"]}


@router.patch("/sets/{set_id}")
async def update_set(set_id: str, body: SetCreate, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(PokemonSet).where(PokemonSet.id == set_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Set not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.commit()
    await search_service.rebuild_index()
    return {"ok": True}


@router.delete("/sets/{set_id}")
async def delete_set(set_id: str, db: AsyncSession = Depends(get_db)):
    s = (await db.execute(select(PokemonSet).where(PokemonSet.id == set_id))).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "Set not found")
    await db.delete(s)
    await db.commit()
    await search_service.rebuild_index()
    return {"ok": True}


# ── Products ─────────────────────────────────────────────────

class ProductCreate(BaseModel):
    set_id:       Optional[int] = None
    name_en:      str
    name_jp:      Optional[str] = None
    product_type: str   # booster_pack | booster_box | special_box | etb | gift_set | promo
    msrp_jpy:     Optional[float] = None
    msrp_usd:     Optional[float] = None
    image_url:    Optional[str] = None
    notes:        Optional[str] = None


@router.post("/products")
async def create_product(body: ProductCreate, db: AsyncSession = Depends(get_db)):
    p = Product(**body.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    await search_service.rebuild_index()
    return {"id": p.id}


@router.get("/products/{pid}")
async def get_product(pid: str, db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Product).where(Product.id == pid))).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Product not found")
    return {k: getattr(p, k) for k in ["id", "set_id", "name_en", "name_jp", "product_type", "msrp_jpy", "msrp_usd", "image_url", "notes"]}


@router.patch("/products/{pid}")
async def update_product(pid: str, body: ProductCreate, db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Product).where(Product.id == pid))).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Product not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    await db.commit()
    await search_service.rebuild_index()
    return {"ok": True}


@router.delete("/products/{pid}")
async def delete_product(pid: str, db: AsyncSession = Depends(get_db)):
    p = (await db.execute(select(Product).where(Product.id == pid))).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Product not found")
    await db.delete(p)
    await db.commit()
    await search_service.rebuild_index()
    return {"ok": True}


# ── Cards ─────────────────────────────────────────────────────

class CardCreate(BaseModel):
    set_id:      Optional[int] = None
    card_number: Optional[str] = None
    name_en:     str
    name_jp:     Optional[str] = None
    rarity:      Optional[str] = None
    image_url:   Optional[str] = None
    is_japanese: bool = True


@router.post("/cards")
async def create_card(body: CardCreate, db: AsyncSession = Depends(get_db)):
    c = Card(**body.model_dump())
    db.add(c)
    await db.commit()
    await db.refresh(c)
    await search_service.rebuild_index()
    return {"id": c.id}


@router.get("/cards/{cid}")
async def get_card(cid: str, db: AsyncSession = Depends(get_db)):
    c = (await db.execute(select(Card).where(Card.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Card not found")
    return {k: getattr(c, k) for k in ["id", "set_id", "name_en", "name_jp", "card_number", "rarity", "image_url", "is_japanese"]}


@router.patch("/cards/{cid}")
async def update_card(cid: str, body: CardCreate, db: AsyncSession = Depends(get_db)):
    c = (await db.execute(select(Card).where(Card.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Card not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    await db.commit()
    await search_service.rebuild_index()
    return {"ok": True}


@router.delete("/cards/{cid}")
async def delete_card(cid: str, db: AsyncSession = Depends(get_db)):
    c = (await db.execute(select(Card).where(Card.id == cid))).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Card not found")
    await db.delete(c)
    await db.commit()
    await search_service.rebuild_index()
    return {"ok": True}


# ── Notification config ───────────────────────────────────────

class NotifUpdate(BaseModel):
    enabled:             Optional[bool] = None
    pushover_user_key:   Optional[str] = None
    pushover_api_token:  Optional[str] = None
    cooldown_hours:      Optional[float] = None


@router.get("/notifications")
async def get_notif_config(db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(NotificationConfig))).scalar_one_or_none()
    if not cfg:
        raise HTTPException(404)
    return {
        "enabled":            cfg.enabled,
        "cooldown_hours":     cfg.cooldown_hours,
        "has_pushover_key":   bool(cfg.pushover_user_key),
        "has_pushover_token": bool(cfg.pushover_api_token),
    }


@router.patch("/notifications")
async def update_notif_config(body: NotifUpdate, db: AsyncSession = Depends(get_db)):
    cfg = (await db.execute(select(NotificationConfig))).scalar_one_or_none()
    if not cfg:
        raise HTTPException(404)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(cfg, k, v)
    await db.commit()
    return {"ok": True}
