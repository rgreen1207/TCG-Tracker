"""
TCG Price Tracker — FastAPI application
Run: uvicorn main:app --host 0.0.0.0 --port 8888
"""
from __future__ import annotations
import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from config import settings
from database import init_db
from services import search_service, notifier
from services.source_registry import get_source_status
import poller
from routers import pages, api_auth, api_prices, api_collection, api_watchlist, api_admin, api_search
from routers.api_sources import router as sources_router

BASE_DIR = Path(__file__).parent

# ── Logging ───────────────────────────────────────────────────
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
fh  = logging.handlers.TimedRotatingFileHandler(
    LOG_DIR / "tracker.log", when="midnight", backupCount=14
)
fh.setFormatter(fmt)
ch = logging.StreamHandler()
ch.setFormatter(fmt)
root = logging.getLogger()
root.setLevel(logging.INFO)
root.addHandler(fh)
root.addHandler(ch)
log = logging.getLogger(__name__)


# ── Lifespan ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting TCG Price Tracker on port %d…", settings.port)
 
    # Warn about defaults but don't block startup
    if settings.using_default_secret:
        log.warning("SECRET_KEY is default — set a real value in .env before going public")
    if settings.using_default_password:
        log.warning("ADMIN_PASSWORD is default ('admin') — change it in .env")
 
    # Log which sources are active
    for src in get_source_status():
        state = "✓ enabled" if src["enabled"] else "✗ disabled (not configured)"
        log.info("  Source: %-24s %s", src["label"], state)
 
    await init_db()
    await search_service.rebuild_index()
    poller.start_scheduler()
 
    if settings.pushover_enabled:
        await notifier.notify_startup()
 
    yield
    poller.stop_scheduler()
    log.info("Tracker shut down cleanly.")
 
 
# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title="TCG Price Tracker",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)
 
# Security headers middleware
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"]        = "DENY"
    response.headers["X-XSS-Protection"]       = "1; mode=block"
    response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
    return response
 
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
 
app.include_router(pages.router)
app.include_router(api_auth.router)
app.include_router(api_prices.router)
app.include_router(api_collection.router)
app.include_router(api_watchlist.router)
app.include_router(api_admin.router)
app.include_router(api_search.router)
app.include_router(sources_router)
 
 
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)
    
