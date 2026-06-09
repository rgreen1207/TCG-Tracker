from __future__ import annotations
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    verify_password, create_token, check_lockout,
    record_attempt, COOKIE_NAME, require_admin,
)
from config import settings
from database import get_db

router = APIRouter()


@router.post("/login")
async def login(
    request: Request,
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host or "unknown"

    if await check_lockout(ip, db):
        return JSONResponse(
            {"detail": "Too many failed attempts. Try again in 15 minutes."},
            status_code=429,
        )

    if not verify_password(password):
        await record_attempt(ip, success=False, db=db)
        return RedirectResponse("/login?error=1", status_code=303)

    await record_attempt(ip, success=True, db=db)
    token = create_token()
    resp = RedirectResponse("/admin", status_code=303)
    resp.set_cookie(
        COOKIE_NAME, token,
        httponly=True, secure=settings.https,
        samesite="strict", max_age=86400,
    )
    return resp


@router.post("/logout")
async def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp
