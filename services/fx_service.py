"""
Live USD/JPY exchange rate via the free Frankfurter API (no key required).
Rate is cached in SQLite and refreshed once per day.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

from database import AsyncSessionLocal, FxRate

log = logging.getLogger(__name__)
_cached_rate: float = 155.0   # safe fallback


async def get_usd_jpy() -> float:
    """Return the current USD→JPY rate, refreshing from API if stale."""
    global _cached_rate
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(FxRate).order_by(FxRate.ts.desc()).limit(1)
        )
        row = result.scalar_one_or_none()

    if row and (datetime.utcnow() - row.ts) < timedelta(hours=24):
        _cached_rate = row.usd_jpy
        return _cached_rate

    # Fetch fresh rate
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                "https://api.frankfurter.app/latest",
                params={"from": "USD", "to": "JPY"},
            )
            r.raise_for_status()
            rate = r.json()["rates"]["JPY"]
        _cached_rate = rate
        async with AsyncSessionLocal() as db:
            db.add(FxRate(usd_jpy=rate))
            await db.commit()
        log.info("FX rate updated: 1 USD = %.2f JPY", rate)
    except Exception as exc:
        log.warning("FX rate fetch failed (%s) — using cached %.2f", exc, _cached_rate)

    return _cached_rate


def jpy_to_usd(jpy: float, rate: float) -> float:
    return round(jpy / rate, 2)


def usd_to_jpy(usd: float, rate: float) -> float:
    return round(usd * rate, 0)
