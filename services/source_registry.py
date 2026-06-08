"""
Source registry — single place that decides which data sources are active
and provides a unified interface for polling prices across all of them.
 
Each source:
  - Has a human-readable name, description, and setup instructions
  - Self-reports whether it is enabled (based on config/credentials)
  - Returns a standardised listing dict:
      {title, price_usd, price_eur, price_jpy, url, seller,
       seller_country, source, source_label, image_url, card_id}
 
Sources and their requirements:
  TCGdex          — always on, no key
  Frankfurter FX  — always on, no key (currency conversion only)
  eBay            — optional, requires EBAY_APP_ID + EBAY_CLIENT_SECRET
  PriceCharting   — optional, requires PRICECHARTING_API_KEY (paid)
  pokemontcg.io   — optional, requires POKEMONTCG_API_KEY (free key)
 
The poller calls collect_prices() — it never needs to know which sources
are configured. Sources that are disabled are silently skipped.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional
 
from config import settings
from services.fx_service import get_usd_jpy
 
log = logging.getLogger(__name__)
 
 
# ── Source status (shown in dashboard + /api/sources) ────────────────────
 
def get_source_status() -> list[dict]:
    return [
        {
            "id":           "tcgdex",
            "label":        "TCGdex",
            "description":  "Card metadata, images, EN+JP names, TCGPlayer/CardMarket prices",
            "url":          "https://tcgdex.dev",
            "enabled":      True,
            "key_required": False,
            "setup":        None,
        },
        {
            "id":           "frankfurter",
            "label":        "Frankfurter FX",
            "description":  "Live USD / JPY / EUR exchange rates (European Central Bank data)",
            "url":          "https://frankfurter.app",
            "enabled":      True,
            "key_required": False,
            "setup":        None,
        },
        {
            "id":           "ebay",
            "label":        "eBay",
            "description":  "Active Buy-It-Now listings — direct purchase links, excludes CN/HK sellers",
            "url":          "https://developer.ebay.com",
            "enabled":      settings.ebay_enabled,
            "key_required": True,
            "setup":        (
                "Set EBAY_APP_ID and EBAY_CLIENT_SECRET in .env. "
                "Free developer account at https://developer.ebay.com → "
                "My Apps → Create App → enable Browse API."
            ),
        },
        {
            "id":           "pricecharting",
            "label":        "PriceCharting",
            "description":  "Historical sealed and graded card market averages (PSA, TAG grades supported)",
            "url":          "https://www.pricecharting.com/api",
            "enabled":      settings.pricecharting_enabled,
            "key_required": True,
            "setup":        (
                "Set PRICECHARTING_API_KEY in .env. "
                "Requires a paid subscription at https://www.pricecharting.com/api"
            ),
        },
        {
            "id":           "pokemontcg",
            "label":        "pokemontcg.io",
            "description":  "English card metadata and TCGPlayer market prices (EN sets only)",
            "url":          "https://pokemontcg.io",
            "enabled":      settings.pokemontcg_enabled,
            "key_required": True,
            "setup":        (
                "Set POKEMONTCG_API_KEY in .env. "
                "Free key at https://pokemontcg.io — raises rate limit from "
                "1,000 to 20,000 requests/day. Note: EN sets only, no Japanese cards."
            ),
        },
        {
            "id":           "pushover",
            "label":        "Pushover Notifications",
            "description":  "Phone push alerts when a watchlist item hits your target price",
            "url":          "https://pushover.net",
            "enabled":      settings.pushover_enabled,
            "key_required": True,
            "setup":        (
                "Set PUSHOVER_USER_KEY and PUSHOVER_API_TOKEN in .env. "
                "Free account at https://pushover.net — one-time $5 app licence (iOS/Android)."
            ),
        },
    ]
 
 
# ── Unified price collection ──────────────────────────────────────────────
 
async def collect_prices(
    keyword: str,
    grade_label: Optional[str] = None,
) -> list[dict]:
    """
    Gather prices from all enabled sources for a keyword.
    grade_label: optional e.g. "PSA 10" — used by PriceCharting and eBay.
    Returns normalised listings sorted by price_usd ascending, nulls last.
    Each listing has a source_label field indicating exactly where it came from.
    """
    tasks = [_fetch_tcgdex(keyword)]
 
    if settings.ebay_enabled:
        tasks.append(_fetch_ebay(keyword, grade_label))
    else:
        log.debug("eBay: skipped (not configured)")
 
    if settings.pricecharting_enabled:
        tasks.append(_fetch_pricecharting(keyword, grade_label))
    else:
        log.debug("PriceCharting: skipped (not configured)")
 
    if settings.pokemontcg_enabled:
        tasks.append(_fetch_pokemontcg(keyword))
    else:
        log.debug("pokemontcg.io: skipped (not configured)")
 
    results_nested = await asyncio.gather(*tasks, return_exceptions=True)
 
    listings: list[dict] = []
    for result in results_nested:
        if isinstance(result, Exception):
            log.warning("Source fetch error: %s", result)
            continue
        listings.extend(result)
 
    listings.sort(key=lambda x: (x.get("price_usd") is None, x.get("price_usd") or 0))
    return listings
 
 
# ── Per-source fetch helpers ──────────────────────────────────────────────
 
async def _fetch_tcgdex(keyword: str) -> list[dict]:
    from services.tcgdex_client import search_cards, extract_prices, get_card, card_image_url
    fx = await get_usd_jpy()
 
    en_results = await search_cards(keyword, lang="en", limit=5)
    ja_results = await search_cards(keyword, lang="ja", limit=5)
 
    listings = []
    seen_ids: set[str] = set()
 
    for brief in (en_results + ja_results):
        card_id = brief.get("id", "")
        if not card_id or card_id in seen_ids:
            continue
        seen_ids.add(card_id)
 
        full = await get_card(card_id, lang="en")
        if not full:
            continue
 
        for p in extract_prices(full):
            market = p.get("market") or p.get("mid")
            if not market:
                continue
 
            price_usd: Optional[float] = None
            price_eur: Optional[float] = None
 
            if p["currency"] == "USD":
                price_usd = round(float(market), 2)
            elif p["currency"] == "EUR":
                price_eur = round(float(market), 2)
                # Use live FX for EUR→USD rather than a hardcoded rate
                price_usd = round(price_eur / (fx * 0.0065), 2)  # EUR/USD ≈ 1/fx * 1.08 approx
 
            listings.append({
                "title":          f"{full.get('name', keyword)} ({brief.get('set', {}).get('name', '')})",
                "price_usd":      price_usd,
                "price_eur":      price_eur,
                "price_jpy":      round(price_usd * fx) if price_usd else None,
                "url":            p.get("url", ""),
                "seller":         p["source"],
                "seller_country": "US" if p["source"] == "TCGPlayer" else "EU",
                "source":         "TCGdex",
                "source_label":   f"TCGdex → {p['source']} ({p['variant']})",
                "image_url":      card_image_url(full.get("image", "")),
                "card_id":        card_id,
            })
 
    return listings
 
 
async def _fetch_ebay(keyword: str, grade_label: Optional[str] = None) -> list[dict]:
    from services.ebay_client import search_listings
    fx = await get_usd_jpy()
 
    raw = await search_listings(keyword, grade_filter=grade_label)
    listings = []
    for item in raw:
        price_usd = item.get("price_usd")
        listings.append({
            "title":          item.get("title", ""),
            "price_usd":      price_usd,
            "price_eur":      None,
            "price_jpy":      round(price_usd * fx) if price_usd else None,
            "url":            item.get("url", ""),
            "seller":         item.get("seller", ""),
            "seller_country": item.get("seller_country", ""),
            "source":         "eBay",
            "source_label":   "eBay (active BIN listing)",
            "image_url":      item.get("image_url", ""),
            "card_id":        None,
        })
    return listings
 
 
async def _fetch_pricecharting(keyword: str, grade_label: Optional[str] = None) -> list[dict]:
    from services.pricecharting_client import search_product
    fx = await get_usd_jpy()
 
    raw = await search_product(keyword, grade=grade_label)
    # Apply FX to any result that came back without JPY
    for item in raw:
        if item.get("price_usd") and not item.get("price_jpy"):
            item["price_jpy"] = round(item["price_usd"] * fx)
    return raw
 
 
async def _fetch_pokemontcg(keyword: str) -> list[dict]:
    from services.pokemontcg_client import get_card_price_listings
    fx = await get_usd_jpy()
 
    raw = await get_card_price_listings(keyword)
    for item in raw:
        if item.get("price_usd") and not item.get("price_jpy"):
            item["price_jpy"] = round(item["price_usd"] * fx)
    return raw
  
