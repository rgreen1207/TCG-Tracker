"""
Background price-polling via APScheduler.
Uses source_registry.collect_prices() — automatically skips unconfigured sources.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from typing import Optional
 
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
 
from config import settings
from database import (
    AsyncSessionLocal, Product, Card,
    WatchlistItem, PriceHistory, AlertLog, NotificationConfig,
)
from services import notifier
from services.source_registry import collect_prices
from services.fx_service import get_usd_jpy
 
log = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
 
state: dict = {
    "running":    False,
    "last_run":   None,
    "next_run":   None,
    "last_error": None,
}
 
 
async def _hours_since_last_alert(item_type: str, item_id: int) -> Optional[float]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AlertLog)
            .where(AlertLog.item_type == item_type, AlertLog.item_id == item_id)
            .order_by(AlertLog.ts.desc()).limit(1)
        )
        row = result.scalar_one_or_none()
    if not row:
        return None
    return (datetime.utcnow() - row.ts).total_seconds() / 3600
 
 
async def _get_cooldown() -> float:
    async with AsyncSessionLocal() as db:
        cfg = (await db.execute(select(NotificationConfig))).scalar_one_or_none()
    return cfg.cooldown_hours if cfg else settings.notify_cooldown_hours
 
 
async def _record_prices(item_type: str, item_id: int, listings: list[dict]):
    async with AsyncSessionLocal() as db:
        for item in listings:
            db.add(PriceHistory(
                item_type=item_type,
                item_id=item_id,
                source=item.get("source_label") or item.get("source", ""),
                price_usd=item.get("price_usd"),
                price_jpy=item.get("price_jpy"),
                url=item.get("url"),
                title=item.get("title"),
                seller=item.get("seller"),
                seller_country=item.get("seller_country"),
            ))
        await db.commit()
 
 
async def _maybe_notify(item_type: str, item_id: int, item_name: str,
                        best: dict, target_usd: float, cooldown: float):
    if not best or not target_usd or not best.get("price_usd"):
        return
    if best["price_usd"] > target_usd:
        return
    hours_ago = await _hours_since_last_alert(item_type, item_id)
    if hours_ago is not None and hours_ago < cooldown:
        return
    await notifier.notify_deal(
        item_name, best["price_usd"], target_usd,
        best.get("url", ""), best.get("source_label") or best.get("source", ""),
    )
    async with AsyncSessionLocal() as db:
        db.add(AlertLog(
            item_type=item_type, item_id=item_id, item_name=item_name,
            price_usd=best["price_usd"], url=best.get("url"),
            source=best.get("source_label") or best.get("source", ""),
        ))
        await db.commit()
 
 
async def run_price_check():
    if state["running"]:
        log.info("Poll already running — skipping")
        return
 
    state["running"] = True
    state["last_run"] = datetime.utcnow()
    log.info("=== Price check started ===")
 
    try:
        cooldown = await _get_cooldown()
 
        async with AsyncSessionLocal() as db:
            products  = (await db.execute(
                select(Product).where(Product.is_active == True)  # noqa
            )).scalars().all()
            watchlist = (await db.execute(select(WatchlistItem))).scalars().all()
 
        watch_map: dict[str, float] = {
            f"{w.item_type}:{w.item_id}": w.target_price_usd
            for w in watchlist if w.target_price_usd
        }
 
        for product in products:
            log.info("Polling: %s", product.name_en)
            listings = await collect_prices(product.name_en)
 
            if not listings:
                log.info("  No results from any source")
                await asyncio.sleep(1)
                continue
 
            await _record_prices("product", product.id, listings)
 
            priced = [l for l in listings if l.get("price_usd")]
            if priced:
                best   = min(priced, key=lambda x: x["price_usd"])
                target = watch_map.get(f"product:{product.id}")
                log.info("  Best: $%.2f via %s", best["price_usd"], best.get("source_label"))
                await _maybe_notify("product", product.id, product.name_en, best, target, cooldown)
 
            await asyncio.sleep(1.5)
 
        log.info("=== Price check complete ===")
 
    except Exception as e:
        log.exception("Price check error: %s", e)
        state["last_error"] = str(e)
    finally:
        state["running"] = False
        job = scheduler.get_job("price_check")
        if job:
            state["next_run"] = job.next_run_time
 
 
def start_scheduler():
    scheduler.add_job(
        run_price_check,
        trigger="interval",
        seconds=settings.poll_interval_seconds,
        id="price_check",
        replace_existing=True,
        next_run_time=datetime.utcnow(),
    )
    scheduler.add_job(
        get_usd_jpy,
        trigger="interval",
        hours=24,
        id="fx_refresh",
        replace_existing=True,
    )
    scheduler.start()
    log.info("Scheduler started — poll every %ds", settings.poll_interval_seconds)
 
 
def stop_scheduler():
    scheduler.shutdown(wait=False)
 
