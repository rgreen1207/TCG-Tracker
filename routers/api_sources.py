"""
/api/sources — returns the status of all configured price data sources.
Used by the dashboard to display the "Active Sources" panel.
"""
from fastapi import APIRouter
from services.source_registry import get_source_status
 
router = APIRouter(prefix="/api/sources")
 
 
@router.get("")
async def list_sources():
    """Return all sources with their enabled state and setup instructions."""
    return get_source_status()
 
