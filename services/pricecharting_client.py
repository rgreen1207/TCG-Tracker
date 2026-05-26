"""
PriceCharting API client — market averages for sealed and graded cards.
Free API key: https://www.pricecharting.com/api
"""
from __future__ import annotations
import logging

import httpx
from config import settings

log = logging.getLogger(__name__)
BASE = "https://www.pricecharting.com/api"

# Map our grade labels to PriceCharting price keys
_GRADE_KEY_MAP = {
    "PSA 10":  "graded-price-10",
    "PSA 9":   "graded-price-9",
    "PSA 8":   "graded-price-8",
    "TAG 10":  "graded-price-10",   # TAG uses same scale; best approximation
    "TAG 9":   "graded-price-9",
}


async def search_product(keyword: str, grade: str | None = None) -> list[dict]:
    """
    Search PriceCharting for a product and return price info.
    grade: optional e.g. "PSA 10" — picks the right price field.
    Returns list of {title, price_usd, url, seller, seller_country, source}
    """
    if not settings.pricecharting_api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BASE}/products",
                params={"q": keyword, "id": settings.pricecharting_api_key},
            )
            r.raise_for_status()
            products = r.json().get("products", [])
    except Exception as e:
        log.error("PriceCharting search '%s': %s", keyword, e)
        return []

    results = []
    for product in products[:3]:
        pid = product.get("id")
        if not pid:
            continue
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                dr = await client.get(
                    f"{BASE}/product",
                    params={"id": pid, "q": settings.pricecharting_api_key},
                )
                dr.raise_for_status()
                detail = dr.json()
        except Exception as e:
            log.warning("PriceCharting detail id=%s: %s", pid, e)
            continue

        # Pick the right price field
        if grade and grade in _GRADE_KEY_MAP:
            cents = detail.get(_GRADE_KEY_MAP[grade])
        else:
            cents = detail.get("new-price") or detail.get("complete-price")

        if not cents:
            continue

        results.append({
            "title":          detail.get("product-name", keyword),
            "price_usd":      round(cents / 100.0, 2),
            "url":            f"https://www.pricecharting.com/game/pokemon-japanese/{pid}",
            "seller":         "PriceCharting market avg",
            "seller_country": "US",
            "source":         "PriceCharting",
        })

    return results
