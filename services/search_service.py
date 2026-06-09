"""
Fuzzy search service.
- Loads all card + product names from the DB into memory
- Uses rapidfuzz for server-side matching (handles typos, partial matches)
- Provides EN→JP name lookup
- Client side gets the name list as JSON for Fuse.js instant search
"""
from __future__ import annotations
import logging
from typing import Optional

from rapidfuzz import process, fuzz
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import AsyncSessionLocal, Card, Product

log = logging.getLogger(__name__)

# In-memory search index rebuilt on startup and after DB writes
_card_index:    list[dict] = []   # {id, name_en, name_jp, set_name, type:"card"}
_product_index: list[dict] = []   # {id, name_en, name_jp, type:"product", product_type}


async def rebuild_index() -> None:
    """Reload search index from DB. Called at startup and after any add/edit."""
    global _card_index, _product_index
    async with AsyncSessionLocal() as db:
        cards = (await db.execute(
            select(Card).options(selectinload(Card.set))
        )).scalars().all()
        products = (await db.execute(
            select(Product).options(selectinload(Product.set))
        )).scalars().all()

        _card_index = [
            {
                "id":       c.id,
                "name_en":  c.name_en,
                "name_jp":  c.name_jp or "",
                "set_name": c.set.name_en if c.set else "",
                "rarity":   c.rarity or "",
                "type":     "card",
            }
            for c in cards
        ]
        _product_index = [
            {
                "id":           p.id,
                "name_en":      p.name_en,
                "name_jp":      p.name_jp or "",
                "set_name":     p.set.name_en if p.set else "",
                "product_type": p.product_type,
                "type":         "product",
            }
            for p in products
        ]
    log.info("Search index rebuilt: %d cards, %d products", len(_card_index), len(_product_index))


def get_index_json() -> list[dict]:
    """Return combined index for Fuse.js (serialisable)."""
    return _card_index + _product_index


def fuzzy_search(query: str, limit: int = 20, threshold: int = 65) -> list[dict]:
    """
    Server-side fuzzy search across cards and products.
    Returns list of matching items sorted by score, highest first.
    """
    if not query or not query.strip():
        return []

    combined = _card_index + _product_index
    if not combined:
        return []

    choices = [item["name_en"] for item in combined]
    matches = process.extract(
        query,
        choices,
        scorer=fuzz.WRatio,
        limit=limit,
        score_cutoff=threshold,
    )

    results = []
    seen: set[str] = set()
    for match_text, score, idx in matches:
        item = combined[idx]
        key = f"{item['type']}:{item['id']}"
        if key not in seen:
            seen.add(key)
            results.append({**item, "score": score})

    return sorted(results, key=lambda x: x["score"], reverse=True)


def get_jp_name(en_name: str) -> Optional[str]:
    """Best-effort EN→JP name lookup from the index."""
    all_items = _card_index + _product_index
    if not all_items:
        return None
    choices = [item["name_en"] for item in all_items]
    match = process.extractOne(en_name, choices, scorer=fuzz.WRatio, score_cutoff=80)
    if match:
        return all_items[match[2]].get("name_jp") or None
    return None
