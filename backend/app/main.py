"""Cirrus API entry point."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, text

from .advisor.providers import get_provider
from .config import get_settings
from .db import get_engine, open_session, utcnow
from .models import AuthSession, PasswordReset, User
from .routers import account, analytics, auth, chat, transactions

log = logging.getLogger("cirrus")
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def purge_expired() -> int:
    """Delete expired demo accounts (data cascades), stale sessions and old reset links."""
    with open_session() as db:
        removed = db.execute(
            delete(User).where(User.is_demo.is_(True), User.expires_at < utcnow())
        ).rowcount
        db.execute(delete(AuthSession).where(AuthSession.expires_at < utcnow()))
        db.execute(delete(PasswordReset).where(PasswordReset.expires_at < utcnow()))
        db.commit()
    return removed


async def _purge_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(purge_expired)
        except Exception:
            log.exception("Couldn't purge expired data")
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_settings().validate_for_runtime()
    task = asyncio.create_task(_purge_loop())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Cirrus API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.docs_enabled else None,
        openapi_url="/api/openapi.json" if settings.docs_enabled else None,
        redoc_url=None,
    )

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        """Sessions use SameSite=Lax cookies. This adds a second check on writes from other sites."""
        origin = request.headers.get("origin")
        if (
            request.method not in _SAFE_METHODS
            and origin
            and origin.rstrip("/") not in get_settings().origins
        ):
            return JSONResponse({"detail": "This site can't make that request."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = response.headers.get("Cache-Control", "no-store")
        return response

    for module in (auth, account, transactions, analytics, chat):
        app.include_router(module.router)

    @app.get("/api/health", tags=["health"])
    def health():
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "ai": get_provider().available()}

    return app


app = create_app()
