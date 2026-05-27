"""
pokemontcg.io API client.
Used for: set metadata, card lookup, EN name → JP name mapping, MSRP pull.
Free tier: 1000 req/day without key, 20000/day with key.
"""
from __future__ import annotations
import logging
from typing import Optional

import httpx
from config import settings

log = logging.getLogger(__name__)
BASE = "https://api.pokemontcg.io/v2"

_headers = {}
if settings.pokemontcg_api_key:
    _headers["X-Api-Key"] = settings.pokemontcg_api_key


async def search_cards(query: str, page_size: int = 20) -> list[dict]:
    """
    Search cards by English name. Returns raw API card objects.
    Example query: 'name:Charizard supertype:Pokémon'
    """
    try:
        async with httpx.AsyncClient(timeout=10, headers=_headers) as client:
            r = await client.get(f"{BASE}/cards", params={"q": query, "pageSize": page_size})
            r.raise_for_status()
            return r.json().get("data", [])
    except Exception as e:
        log.error("pokemontcg card search failed: %s", e)
        return []


async def get_sets(page_size: int = 250) -> list[dict]:
    """Fetch all sets (used to seed the sets table)."""
    try:
        async with httpx.AsyncClient(timeout=15, headers=_headers) as client:
            r = await client.get(f"{BASE}/sets", params={"pageSize": page_size})
            r.raise_for_status()
            return r.json().get("data", [])
    except Exception as e:
        log.error("pokemontcg sets fetch failed: %s", e)
        return []


async def get_card(card_id: str) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=10, headers=_headers) as client:
            r = await client.get(f"{BASE}/cards/{card_id}")
            r.raise_for_status()
            return r.json().get("data")
    except Exception as e:
        log.error("pokemontcg get_card %s failed: %s", card_id, e)
        return None


def extract_msrp_usd(card: dict) -> Optional[float]:
    """Pull TCGPlayer market price from card data as a USD MSRP proxy."""
    try:
        prices = card.get("tcgplayer", {}).get("prices", {})
        for variant in ("holofoil", "normal", "reverseHolofoil", "1stEditionHolofoil"):
            p = prices.get(variant, {}).get("market")
            if p:
                return float(p)
    except Exception:
        pass
    return None
