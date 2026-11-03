"""Shared FastAPI dependencies: current user, client IP and rate limiting."""

from datetime import timedelta

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db, utcnow
from .models import AuthSession, User
from .security import SESSION_COOKIE, hash_token, limiter, new_token


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_limit(key: str, limit: int, window_seconds: int) -> None:
    if not limiter.allow(key, limit, window_seconds):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Wait a minute and try again."
        )


def start_session(db: Session, user: User, response: Response, lifetime: timedelta) -> None:
    token = new_token()
    db.add(
        AuthSession(user_id=user.id, token_hash=hash_token(token), expires_at=utcnow() + lifetime)
    )
    db.commit()
    settings = get_settings()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        row = db.execute(
            select(User)
            .join(AuthSession, AuthSession.user_id == User.id)
            .where(AuthSession.token_hash == hash_token(token), AuthSession.expires_at > utcnow())
        ).scalar_one_or_none()
        if row:
            return row
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
