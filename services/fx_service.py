"""
Live USD/JPY and EUR/USD exchange rates via open.er-api.com (no key required).
Provides mid-market rates matching Google/Wise. Cached in SQLite, refreshed once per day.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy import select

from database import AsyncSessionLocal, FxRate

log = logging.getLogger(__name__)
_cached_rate: float = 155.0    # safe fallback USD/JPY
_cached_eur_usd: float = 1.08  # safe fallback EUR/USD


async def get_usd_jpy() -> float:
    """Return the current USD→JPY rate, refreshing from API if stale."""
    global _cached_rate, _cached_eur_usd
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(FxRate).order_by(FxRate.ts.desc()).limit(1)
        )
        row = result.scalar_one_or_none()

    if row and (datetime.utcnow() - row.ts) < timedelta(hours=2):
        _cached_rate = row.usd_jpy
        return _cached_rate

    # Fetch both JPY and EUR in one request
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get("https://open.er-api.com/v6/latest/USD")
            r.raise_for_status()
            rates = r.json()["rates"]
        _cached_rate = rates["JPY"]
        _cached_eur_usd = 1 / rates["EUR"]  # USD/EUR → EUR/USD
        async with AsyncSessionLocal() as db:
            db.add(FxRate(usd_jpy=_cached_rate))
            await db.commit()
        log.info("FX rates updated: 1 USD = %.2f JPY, 1 EUR = %.4f USD", _cached_rate, _cached_eur_usd)
    except Exception as exc:
        log.warning("FX rate fetch failed (%s) — using cached values", exc)

    return _cached_rate


def get_eur_usd() -> float:
    """Return the cached EUR→USD rate (populated by get_usd_jpy)."""
    return _cached_eur_usd


def jpy_to_usd(jpy: float, rate: float) -> float:
    return round(jpy / rate, 2)


def usd_to_jpy(usd: float, rate: float) -> float:
    return round(usd * rate, 0)
