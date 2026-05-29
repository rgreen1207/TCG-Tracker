"""Push notifications via Pushover. Respects the DB-stored enabled flag."""
from __future__ import annotations
import logging

import httpx
from sqlalchemy import select

from database import AsyncSessionLocal, NotificationConfig

log = logging.getLogger(__name__)
PUSHOVER_URL = "https://api.pushover.net/1/messages.json"


async def _get_config() -> NotificationConfig | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(NotificationConfig).where(NotificationConfig.id == 1))
        return result.scalar_one_or_none()


async def send_push(title: str, message: str, url: str = "", priority: int = 0) -> bool:
    cfg = await _get_config()
    if not cfg or not cfg.enabled:
        log.info("Notifications disabled — skipping push")
        return False
    if not cfg.pushover_user_key or not cfg.pushover_api_token:
        log.warning("Pushover credentials not configured")
        return False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(PUSHOVER_URL, data={
                "token":    cfg.pushover_api_token,
                "user":     cfg.pushover_user_key,
                "title":    title,
                "message":  message,
                "url":      url,
                "url_title": "View listing →",
                "priority": priority,
            })
            r.raise_for_status()
        log.info("Push sent: %s", title)
        return True
    except Exception as e:
        log.error("Push failed: %s", e)
        return False


async def notify_deal(item_name: str, price_usd: float, target_usd: float, url: str, source: str):
    pct = round((1 - price_usd / target_usd) * 100) if target_usd else 0
    msg = (
        f"💰 {pct}% below your ${target_usd:.2f} target!\n"
        f"${price_usd:.2f} via {source}\n{item_name[:80]}"
    )
    await send_push(f"🃏 Deal: {item_name[:45]}", msg, url=url, priority=1)


async def notify_startup():
    await send_push(
        "🃏 Pokemon Tracker Online",
        "Price tracker is running on your Raspberry Pi.",
        priority=-1,
    )
