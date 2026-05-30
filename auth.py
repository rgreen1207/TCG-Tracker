from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Request, HTTPException, status, Depends
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db, LoginAttempt

ALGORITHM   = "HS256"
COOKIE_NAME = "pt_token"
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Hash is generated once at startup from the plaintext ADMIN_PASSWORD in .env
_admin_hash: str = pwd_ctx.hash(settings.admin_password)


def verify_password(plain: str) -> bool:
    return pwd_ctx.verify(plain, _admin_hash)


def create_token() -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours)
    return jwt.encode({"sub": "admin", "exp": expire}, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None


async def check_lockout(ip: str, db: AsyncSession) -> bool:
    """Return True if IP is locked out (too many recent failures)."""
    cutoff = datetime.utcnow() - timedelta(minutes=LOCKOUT_MINUTES)
    result = await db.execute(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.ip_address == ip,
            LoginAttempt.ts >= cutoff,
            LoginAttempt.success == False,        # noqa: E712
        )
    )
    return (result.scalar() or 0) >= MAX_ATTEMPTS


async def record_attempt(ip: str, success: bool, db: AsyncSession) -> None:
    db.add(LoginAttempt(ip_address=ip, success=success))
    await db.commit()


# ── FastAPI dependencies ──────────────────────────────────────

def get_token_from_cookie(request: Request) -> Optional[str]:
    return request.cookies.get(COOKIE_NAME)


async def require_admin(request: Request) -> bool:
    """Dependency — raises 401 / redirects to login if not authenticated."""
    token = get_token_from_cookie(request)
    if not token or not decode_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True


def is_admin(request: Request) -> bool:
    """Non-raising version — returns bool. Use for template context."""
    token = get_token_from_cookie(request)
    if not token:
        return False
    return decode_token(token) is not None
