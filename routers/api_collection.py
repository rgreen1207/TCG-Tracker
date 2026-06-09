from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import require_admin
from database import get_db, CollectionItem, Product, Card, PriceHistory
from services.fx_service import get_usd_jpy

router = APIRouter(prefix="/api/collection")


class CollectionCreate(BaseModel):
    item_type:         str            # product | card
    item_id:           str
    status:            str            # raw | graded
    grader:            Optional[str] = None   # PSA | TAG
    grade:             Optional[float] = None
    quantity:          int = 1
    acquired_price_usd: Optional[float] = None
    acquired_date:     Optional[str] = None
    notes:             Optional[str] = None


class CollectionUpdate(BaseModel):
    status:            Optional[str] = None
    grader:            Optional[str] = None
    grade:             Optional[float] = None
    quantity:          Optional[int] = None
    acquired_price_usd: Optional[float] = None
    acquired_date:     Optional[str] = None
    notes:             Optional[str] = None


@router.get("")
async def list_collection(db: AsyncSession = Depends(get_db)):
    """Public read — returns enriched collection with current market prices."""
    items = (await db.execute(select(CollectionItem))).scalars().all()
    fx = await get_usd_jpy()
    result = []

    for item in items:
        # Resolve item name and MSRP
        name_en, name_jp, msrp_usd, msrp_jpy, image_url = "", "", None, None, None
        if item.item_type == "product":
            row = (await db.execute(
                select(Product).where(Product.id == item.item_id)
            )).scalar_one_or_none()
            if row:
                name_en, name_jp = row.name_en, row.name_jp or ""
                msrp_usd, msrp_jpy = row.msrp_usd, row.msrp_jpy
                image_url = row.image_url
        else:
            row = (await db.execute(
                select(Card).where(Card.id == item.item_id)
            )).scalar_one_or_none()
            if row:
                name_en, name_jp = row.name_en, row.name_jp or ""
                image_url = row.image_url

        # Current lowest market price
        ph = (await db.execute(
            select(PriceHistory)
            .where(
                PriceHistory.item_type == item.item_type,
                PriceHistory.item_id == item.item_id,
            )
            .order_by(PriceHistory.price_usd.asc())
            .limit(1)
        )).scalar_one_or_none()

        market_usd = ph.price_usd if ph else None
        market_jpy = round(market_usd * fx) if market_usd else None
        total_usd  = round(market_usd * item.quantity, 2) if market_usd else None

        result.append({
            "id":              item.id,
            "item_type":       item.item_type,
            "item_id":         item.item_id,
            "name_en":         name_en,
            "name_jp":         name_jp,
            "image_url":       image_url,
            "status":          item.status,
            "grader":          item.grader,
            "grade":           item.grade,
            "quantity":        item.quantity,
            "acquired_price_usd": item.acquired_price_usd,
            "acquired_date":   item.acquired_date,
            "notes":           item.notes,
            "market_usd":      market_usd,
            "market_jpy":      market_jpy,
            "market_url":      ph.url if ph else None,
            "msrp_usd":        msrp_usd,
            "msrp_jpy":        msrp_jpy,
            "total_value_usd": total_usd,
        })

    portfolio_usd = sum(r["total_value_usd"] or 0 for r in result)
    return {"items": result, "portfolio_usd": round(portfolio_usd, 2),
            "portfolio_jpy": round(portfolio_usd * fx)}


@router.post("", dependencies=[Depends(require_admin)])
async def add_item(body: CollectionCreate, db: AsyncSession = Depends(get_db)):
    item = CollectionItem(**body.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id}


@router.patch("/{item_id}", dependencies=[Depends(require_admin)])
async def update_item(
    item_id: str,
    body: CollectionUpdate,
    db: AsyncSession = Depends(get_db),
):
    item = (await db.execute(
        select(CollectionItem).where(CollectionItem.id == item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(item, field, val)
    await db.commit()
    return {"ok": True}


@router.delete("/{item_id}", dependencies=[Depends(require_admin)])
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db)):
    item = (await db.execute(
        select(CollectionItem).where(CollectionItem.id == item_id)
    )).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    await db.delete(item)
    await db.commit()
    return {"ok": True}
