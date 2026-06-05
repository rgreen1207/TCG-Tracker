"""
Pokemon Price Tracker — FastAPI application
Run: uvicorn main:app --host 0.0.0.0 --port 8888
"""
from __future__ import annotations
import logging
import logging.handlers
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from config import settings
from database import init_db
from services import search_service, notifier
import poller
from routers import pages, api_auth, api_prices, api_collection, api_watchlist, api_admin, api_search

# ── Logging ───────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
fh = logging.handlers.TimedRotatingFileHandler(
    os.path.join(LOG_DIR, "tracker.log"), when="midnight", backupCount=14
)
fh.setFormatter(fmt)
ch = logging.StreamHandler()
ch.setFormatter(fmt)
root = logging.getLogger()
root.setLevel(logging.INFO)
root.addHandler(fh)
root.addHandler(ch)
log = logging.getLogger(__name__)

# ── Rate limiter ──────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ── Lifespan ──────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting Pokemon Price Tracker on :%d", settings.port)
    await init_db()
    await search_service.rebuild_index()
    poller.start_scheduler()
    await notifier.notify_startup()
    yield
    poller.stop_scheduler()
    log.info("Tracker shut down cleanly.")


# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title="Pokemon Price Tracker",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Stricter rate limit on login
@app.post("/login")
@limiter.limit("10/minute")
async def _login_rate_guard(request: Request):
    pass   # actual handler is in api_auth router

app.mount("/static", StaticFiles(directory="static"), name="static")

# Security headers middleware
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

app.include_router(pages.router)
app.include_router(api_auth.router)
app.include_router(api_prices.router)
app.include_router(api_collection.router)
app.include_router(api_watchlist.router)
app.include_router(api_admin.router)
app.include_router(api_search.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)
