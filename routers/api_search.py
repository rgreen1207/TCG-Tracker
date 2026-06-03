from __future__ import annotations
from fastapi import APIRouter, Query
from services import search_service

router = APIRouter(prefix="/api/search")


@router.get("")
async def search(q: str = Query(..., min_length=1), limit: int = 20):
    """Server-side fuzzy search. Also used as fallback when Fuse.js misses."""
    return search_service.fuzzy_search(q, limit=limit)


@router.get("/index")
async def get_index():
    """Full name index for Fuse.js client-side search."""
    return search_service.get_index_json()
