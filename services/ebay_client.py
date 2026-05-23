"""
Async eBay Browse API — active Buy-It-Now listings only.
Filters: NEW condition, FIXED_PRICE, excludes CN/HK sellers.
Docs: https://developer.ebay.com/api-docs/buy/browse/overview.html
"""
from __future__ import annotations
import base64
import logging
import time

import httpx
from config import settings

log = logging.getLogger(__name__)
_token_cache: dict = {"token": None, "expires_at": 0.0}


async def _get_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    creds = base64.b64encode(
        f"{settings.ebay_app_id}:{settings.ebay_client_secret}".encode()
    ).decode()
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers={"Authorization": f"Basic {creds}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data="grant_type=client_credentials"
                 "&scope=https://api.ebay.com/oauth/api_scope",
        )
        r.raise_for_status()
        data = r.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data["expires_in"]
    return _token_cache["token"]


async def search_listings(
    keyword: str,
    max_results: int = 20,
    grade_filter: str | None = None,
) -> list[dict]:
    """
    Returns active BIN listings.
    grade_filter: optional string appended to keyword e.g. "PSA 10"
    Each result: {title, price_usd, url, seller, seller_country, source}
    """
    if not settings.ebay_app_id:
        log.warning("eBay App ID not configured — skipping")
        return []

    query = keyword
    if grade_filter:
        query = f"{keyword} {grade_filter}"

    try:
        token = await _get_token()
    except Exception as e:
        log.error("eBay OAuth failed: %s", e)
        return []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://api.ebay.com/buy/browse/v1/item_summary/search",
                headers={"Authorization": f"Bearer {token}",
                         "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
                params={
                    "q":      query,
                    "limit":  max_results,
                    "filter": "buyingOptions:{FIXED_PRICE},conditions:{NEW}",
                    "sort":   "price",
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.error("eBay search error '%s': %s", keyword, e)
        return []

    results = []
    for item in data.get("itemSummaries", []):
        country = item.get("itemLocation", {}).get("country", "")
        if country in settings.excluded_seller_countries:
            continue
        try:
            price = float(item["price"]["value"])
        except (KeyError, ValueError, TypeError):
            continue
        results.append({
            "title":          item.get("title", ""),
            "price_usd":      price,
            "url":            item.get("itemWebUrl", ""),
            "seller":         item.get("seller", {}).get("username", "unknown"),
            "seller_country": country,
            "source":         "eBay",
        })

    return results
