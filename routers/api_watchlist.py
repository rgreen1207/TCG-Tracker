from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin
from database import get_db, WatchlistItem, Product, Card, PriceHistory
from services.fx_service import get_usd_jpy

router = APIRouter(prefix="/api/watchlist")


class WatchlistCreate(BaseModel):
    item_type:        str
    item_id:          int
    target_price_usd: Optional[float] = None
    notes:            Optional[str] = None


@router.get("")
async def list_watchlist(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(WatchlistItem))).scalars().all()
    fx = await get_usd_jpy()
    result = []
    for w in rows:
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
            .order_by(PriceHistory.price_usd.asc())
            .limit(1)
        )).scalar_one_or_none()

        current_usd = ph.price_usd if ph else None
        result.append({
            "id":               w.id,
            "item_type":        w.item_type,
            "item_id":          w.item_id,
            "name_en":          name_en,
            "name_jp":          name_jp,
            "image_url":        image_url,
            "target_price_usd": w.target_price_usd,
            "target_price_jpy": round(w.target_price_usd * fx) if w.target_price_usd else None,
            "current_usd":      current_usd,
            "current_jpy":      round(current_usd * fx) if current_usd else None,
            "is_deal":          (current_usd <= w.target_price_usd)
                                if (current_usd and w.target_price_usd) else False,
            "notes":            w.notes,
            "added_at":         w.added_at.isoformat(),
        })
    return result


@router.post("", dependencies=[Depends(require_admin)])
async def add_watchlist(body: WatchlistCreate, db: AsyncSession = Depends(get_db)):
    item = WatchlistItem(**body.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id}


@router.delete("/{wid}", dependencies=[Depends(require_admin)])
async def remove_watchlist(wid: int, db: AsyncSession = Depends(get_db)):
    item = (await db.execute(
        select(WatchlistItem).where(WatchlistItem.id == wid)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Not found")
    await db.delete(item)
    await db.commit()
    return {"ok": True}
