"""
Pokemon TCG API client — card metadata, EN names, set info, TCGPlayer MSRP.
https://pokemontcg.io
 
A free account gives 1,000 req/day without a key.
Providing an API key raises the limit to 20,000 req/day.
 
Only used when pokemontcg_enabled is True (key provided).
Without a key the app uses TCGdex for all card/set metadata instead.
 
Key differences from TCGdex:
  - Better English card data coverage and TCGPlayer price history
  - Does NOT have Japanese card data — use TCGdex for JP
  - Provides MSRP proxies from TCGPlayer market prices
"""
from __future__ import annotations
import logging
from typing import Optional
 
import httpx
from config import settings
 
log = logging.getLogger(__name__)
BASE = "https://api.pokemontcg.io/v2"
 
 
def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if settings.pokemontcg_enabled:
        h["X-Api-Key"] = settings.pokemontcg_api_key
    return h
 
 
async def search_cards(query: str, page_size: int = 20) -> list[dict]:
    """
    Search cards by English name/query string.
    query examples: 'name:Charizard', 'name:Pikachu supertype:Pokémon'
    Returns raw API card objects.
    Only called when pokemontcg_enabled — without a key rate limits are
    too low for background polling, so we fall back to TCGdex.
    """
    if not settings.pokemontcg_enabled:
        return []
 
    try:
        async with httpx.AsyncClient(timeout=12, headers=_headers()) as client:
            r = await client.get(
                f"{BASE}/cards",
                params={"q": query, "pageSize": page_size},
            )
            r.raise_for_status()
            return r.json().get("data", [])
    except Exception as e:
        log.error("pokemontcg search '%s': %s", query, e)
        return []
 
 
async def get_sets(page_size: int = 250) -> list[dict]:
    """
    Fetch all sets. Used to seed/enrich the sets table with EN names,
    set codes, release dates, and logo images.
    Only called when pokemontcg_enabled.
    """
    if not settings.pokemontcg_enabled:
        return []
 
    try:
        async with httpx.AsyncClient(timeout=15, headers=_headers()) as client:
            r = await client.get(f"{BASE}/sets", params={"pageSize": page_size})
            r.raise_for_status()
            return r.json().get("data", [])
    except Exception as e:
        log.error("pokemontcg get_sets: %s", e)
        return []
 
 
async def get_card(card_id: str) -> Optional[dict]:
    """Fetch a single card by pokemontcg.io ID (e.g. 'xy7-54')."""
    if not settings.pokemontcg_enabled:
        return None
 
    try:
        async with httpx.AsyncClient(timeout=10, headers=_headers()) as client:
            r = await client.get(f"{BASE}/cards/{card_id}")
            r.raise_for_status()
            return r.json().get("data")
    except Exception as e:
        log.error("pokemontcg get_card %s: %s", card_id, e)
        return None
 
 
def extract_msrp_usd(card: dict) -> Optional[float]:
    """
    Pull TCGPlayer market price from a card object as a USD MSRP proxy.
    Tries holofoil → normal → reverseHolofoil → 1stEditionHolofoil.
    """
    try:
        prices = card.get("tcgplayer", {}).get("prices", {})
        for variant in ("holofoil", "normal", "reverseHolofoil", "1stEditionHolofoil"):
            p = prices.get(variant, {}).get("market")
            if p:
                return float(p)
    except Exception:
        pass
    return None
 
 
async def get_card_price_listings(keyword: str) -> list[dict]:
    """
    Search pokemontcg.io for keyword and return normalised price listings
    using TCGPlayer market prices embedded in the card data.
    Returns list of {title, price_usd, url, seller, seller_country, source, source_label}
    """
    if not settings.pokemontcg_enabled:
        return []
 
    cards = await search_cards(f"name:{keyword}", page_size=5)
    results = []
 
    for card in cards:
        price = extract_msrp_usd(card)
        if not price:
            continue
 
        tcgplayer_url = card.get("tcgplayer", {}).get("url", "")
        set_name = card.get("set", {}).get("name", "")
        name = card.get("name", keyword)
 
        results.append({
            "title":          f"{name} ({set_name})",
            "price_usd":      round(price, 2),
            "price_eur":      None,
            "price_jpy":      None,   # caller applies FX
            "url":            tcgplayer_url,
            "seller":         "TCGPlayer (via pokemontcg.io)",
            "seller_country": "US",
            "source":         "pokemontcg.io",
            "source_label":   "pokemontcg.io → TCGPlayer market price",
            "image_url":      card.get("images", {}).get("small", ""),
            "card_id":        card.get("id"),
        })
 
    return results
 
