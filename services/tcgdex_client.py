"""
TCGdex API client — completely free, no API key required.
https://tcgdex.dev
 
Provides:
  - Card metadata (EN + JP + 10 other languages)
  - Card images (hosted on assets.tcgdex.net)
  - Set metadata and logos
  - Market prices from TCGPlayer and CardMarket (embedded in card response)
 
Rate limits: none published — cache aggressively, don't hammer.
Language codes: en, ja, fr, de, es, it, pt, ko, zh-tw, zh-cn, id, th
"""
from __future__ import annotations
import logging
from typing import Optional
 
import httpx
 
log = logging.getLogger(__name__)
 
BASE_EN = "https://api.tcgdex.net/v2/en"
BASE_JA = "https://api.tcgdex.net/v2/ja"
ASSETS  = "https://assets.tcgdex.net"
 
# Image quality suffixes: append to image URL from API
# e.g. https://assets.tcgdex.net/en/swsh/swsh3/136/high.webp
IMG_QUALITY = "high"    # high | low
IMG_FORMAT  = "webp"    # webp | png
 
 
def card_image_url(raw_url: str, quality: str = IMG_QUALITY, fmt: str = IMG_FORMAT) -> str:
    """Convert a raw TCGdex image URL to a full URL with quality and format."""
    if not raw_url:
        return ""
    return f"{raw_url}/{quality}.{fmt}"
 
 
# ── Sets ──────────────────────────────────────────────────────────────────
 
async def get_all_sets(lang: str = "en") -> list[dict]:
    """Fetch all sets for a language. Returns list of set summary objects."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"https://api.tcgdex.net/v2/{lang}/sets")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.error("TCGdex get_all_sets(%s): %s", lang, e)
        return []
 
 
async def get_set(set_id: str, lang: str = "en") -> Optional[dict]:
    """Fetch full set detail including card list."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"https://api.tcgdex.net/v2/{lang}/sets/{set_id}")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.error("TCGdex get_set(%s, %s): %s", set_id, lang, e)
        return None
 
 
async def get_all_series(lang: str = "en") -> list[dict]:
    """Fetch all series (groupings of sets)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"https://api.tcgdex.net/v2/{lang}/series")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.error("TCGdex get_all_series(%s): %s", lang, e)
        return []
 
 
# ── Cards ─────────────────────────────────────────────────────────────────
 
async def get_card(card_id: str, lang: str = "en") -> Optional[dict]:
    """
    Fetch a single card by its TCGdex ID (e.g. 'swsh3-136').
    Response includes image URL and pricing if available.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://api.tcgdex.net/v2/{lang}/cards/{card_id}")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        log.error("TCGdex get_card(%s, %s): %s", card_id, lang, e)
        return None
 
 
async def search_cards(name: str, lang: str = "en", limit: int = 20) -> list[dict]:
    """
    Search cards by name using TCGdex filtering.
    Returns brief card objects with id, name, image.
    """
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(
                f"https://api.tcgdex.net/v2/{lang}/cards",
                params={"name": name, "pagination[pageSize]": limit},
            )
            r.raise_for_status()
            return r.json() or []
    except Exception as e:
        log.error("TCGdex search_cards(%s, %s): %s", name, lang, e)
        return []
 
 
async def get_cards_in_set(set_id: str, lang: str = "en") -> list[dict]:
    """Get all card briefs for a set."""
    s = await get_set(set_id, lang)
    if not s:
        return []
    return s.get("cards", [])
 
 
# ── Prices ────────────────────────────────────────────────────────────────
 
def extract_prices(card: dict) -> list[dict]:
    """
    Extract pricing data from a full TCGdex card object.
    Returns list of:
      {source, variant, low, mid, high, market, currency, url, updated_at}
    """
    results = []
    pricing = card.get("pricing") or {}
 
    # TCGPlayer prices
    tcgplayer = pricing.get("tcgplayer")
    if tcgplayer:
        url = tcgplayer.get("url", "")
        updated = tcgplayer.get("updatedAt", "")
        for variant_name, data in tcgplayer.get("prices", {}).items():
            if not isinstance(data, dict):
                continue
            results.append({
                "source":     "TCGPlayer",
                "variant":    variant_name,
                "low":        data.get("lowPrice"),
                "mid":        data.get("midPrice"),
                "high":       data.get("highPrice"),
                "market":     data.get("marketPrice"),
                "currency":   "USD",
                "url":        url,
                "updated_at": updated,
            })
 
    # CardMarket prices
    cardmarket = pricing.get("cardmarket")
    if cardmarket:
        url = cardmarket.get("url", "")
        updated = cardmarket.get("updatedAt", "")
        for variant_name, data in cardmarket.get("prices", {}).items():
            if not isinstance(data, dict):
                continue
            results.append({
                "source":     "CardMarket",
                "variant":    variant_name,
                "low":        data.get("lowPrice"),
                "mid":        data.get("avg"),
                "high":       None,
                "market":     data.get("trendPrice"),
                "currency":   "EUR",
                "url":        url,
                "updated_at": updated,
            })
 
    return results
 
 
async def get_card_prices(card_id: str, lang: str = "en") -> list[dict]:
    """Convenience: fetch a card and return its prices."""
    card = await get_card(card_id, lang)
    if not card:
        return []
    return extract_prices(card)
  
