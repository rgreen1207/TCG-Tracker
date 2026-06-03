from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, PriceHistory, Product, Card, AlertLog
from services.fx_service import get_usd_jpy
import poller

router = APIRouter(prefix="/api/prices")


@router.get("/lowest/{item_type}/{item_id}")
async def get_lowest(
    item_type: str,
    item_id: int,
    hours: int = 24,
    db: AsyncSession = Depends(get_db),
):
    """Return the current lowest price listing for an item."""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    result = await db.execute(
        select(PriceHistory)
        .where(
            PriceHistory.item_type == item_type,
            PriceHistory.item_id == item_id,
            PriceHistory.ts >= cutoff,
            PriceHistory.price_usd.isnot(None),
        )
        .order_by(PriceHistory.price_usd.asc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        return {"lowest": None}

    fx = await get_usd_jpy()
    return {
        "lowest": {
            "price_usd":  row.price_usd,
            "price_jpy":  round(row.price_usd * fx) if row.price_usd else None,
            "url":        row.url,
            "source":     row.source,
            "seller":     row.seller,
            "ts":         row.ts.isoformat(),
        }
    }


@router.get("/history/{item_type}/{item_id}")
async def get_history(
    item_type: str,
    item_id: int,
    limit: int = Query(200, le=1000),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PriceHistory)
        .where(PriceHistory.item_type == item_type, PriceHistory.item_id == item_id)
        .order_by(PriceHistory.ts.asc())
        .limit(limit)
    )
    rows = result.scalars().all()
    fx = await get_usd_jpy()
    return [
        {
            "ts":          r.ts.isoformat(),
            "price_usd":   r.price_usd,
            "price_jpy":   round(r.price_usd * fx) if r.price_usd else None,
            "source":      r.source,
            "url":         r.url,
        }
        for r in rows
    ]


@router.get("/sparkline/{item_type}/{item_id}")
async def sparkline(
    item_type: str,
    item_id: int,
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Daily min prices for sparkline chart — last N days."""
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(
            func.date(PriceHistory.ts).label("day"),
            func.min(PriceHistory.price_usd).label("min_price"),
        )
        .where(
            PriceHistory.item_type == item_type,
            PriceHistory.item_id == item_id,
            PriceHistory.ts >= cutoff,
        )
        .group_by(func.date(PriceHistory.ts))
        .order_by(func.date(PriceHistory.ts))
    )
    rows = result.all()
    return [{"day": r.day, "min_usd": r.min_price} for r in rows]


@router.get("/status")
async def get_status():
    job = poller.scheduler.get_job("price_check")
    return {
        "running":   poller.state.get("running", False),
        "last_run":  poller.state.get("last_run"),
        "next_run":  job.next_run_time if job else None,
        "last_error": poller.state.get("last_error"),
    }


@router.post("/poll/trigger")
async def trigger_poll():
    import asyncio
    asyncio.create_task(poller.run_price_check())
    return {"message": "Poll triggered."}
