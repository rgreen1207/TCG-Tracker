"""
PriceCharting API client — historical and graded card market prices.
https://www.pricecharting.com/api
 
Requires a paid API key. Only called when pricecharting_enabled is True.
Provides: sealed product prices, raw card prices, PSA/TAG graded prices.
 
Grade key mapping:
  PriceCharting uses numeric grade keys: graded-price-10, graded-price-9, etc.
  We map our internal grade labels (e.g. "PSA 10", "TAG 9") to those keys.
"""
from __future__ import annotations
import logging
from typing import Optional
 
import httpx
from config import settings
 
log = logging.getLogger(__name__)
BASE = "https://www.pricecharting.com/api"
 
_GRADE_KEY_MAP: dict[str, str] = {
    "PSA 10": "graded-price-10",
    "PSA 9.5": "graded-price-9",   # PriceCharting doesn't have 9.5; nearest
    "PSA 9":  "graded-price-9",
    "PSA 8":  "graded-price-8",
    "PSA 7":  "graded-price-7",
    "TAG 10": "graded-price-10",
    "TAG 9":  "graded-price-9",
    "TAG 8":  "graded-price-8",
}
 
 
async def search_product(keyword: str, grade: Optional[str] = None) -> list[dict]:
    """
    Search PriceCharting for keyword and return normalised price listings.
    grade: optional label e.g. "PSA 10" — selects the graded price field.
    Returns list of {title, price_usd, url, seller, seller_country, source, source_label}
    """
    if not settings.pricecharting_enabled:
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
 
        # Select price field based on grade or fall back to sealed/complete
        if grade and grade in _GRADE_KEY_MAP:
            cents = detail.get(_GRADE_KEY_MAP[grade])
            price_label = f"graded ({grade})"
        else:
            cents = detail.get("new-price") or detail.get("complete-price")
            price_label = "sealed/complete"
 
        if not cents:
            continue
 
        url = f"https://www.pricecharting.com/game/pokemon-japanese/{pid}"
        results.append({
            "title":          detail.get("product-name", keyword),
            "price_usd":      round(cents / 100.0, 2),
            "price_eur":      None,
            "price_jpy":      None,   # caller applies FX
            "url":            url,
            "seller":         "PriceCharting",
            "seller_country": "US",
            "source":         "PriceCharting",
            "source_label":   f"PriceCharting ({price_label})",
            "image_url":      "",
            "card_id":        None,
        })
 
    return results
 
