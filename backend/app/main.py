"""FastAPI app factory: lifespan, middleware, routers.

The single shared `httpx.AsyncClient` is created here and only here (SPEC §6, §13).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.telegram_webhook import router as telegram_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.redis import create_redis
from app.db.session import async_session_factory, engine
from app.providers.registry import ProviderRegistry
from app.telegram.bot import build_bot, build_dispatcher, configure_webhook
from app.telegram.scheduler import build_scheduler

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()

    # One client for the whole process. Per-request clients cost 200-300ms of
    # TLS handshake and defeat the latency goal outright (SPEC §6).
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(settings.PROVIDER_TIMEOUT_SECONDS),
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
        follow_redirects=True,
    )
    app.state.redis = create_redis()
    # Providers are constructed once and handed the shared client (SPEC §6).
    app.state.provider_registry = ProviderRegistry(app.state.http_client)

    # SPEC §9a: the bot runs in webhook mode, in this same process. It only mounts
    # when a token is configured (BLOCKERS.md B1).
    app.state.bot = None
    app.state.dispatcher = None
    app.state.scheduler = None

    if settings.bot_enabled:
        app.state.bot = build_bot(app.state.http_client)
        app.state.dispatcher = build_dispatcher(
            session_factory=async_session_factory,
            redis=app.state.redis,
            registry=app.state.provider_registry,
        )
        app.state.scheduler = build_scheduler(app.state.bot, async_session_factory)
        app.state.scheduler.start()
        try:
            await configure_webhook(app.state.bot)
        except Exception as exc:
            # A webhook we could not register is worth shouting about, but it must not
            # stop the API from serving the Mini App.
            logger.error(
                "webhook_registration_failed",
                extra={"event": "webhook_registration_failed", "error": str(exc)},
            )

    logger.info(
        "startup",
        extra={
            "event": "startup",
            "env": settings.ENV,
            "bot_enabled": settings.bot_enabled,
            "provider_fakes": app.state.provider_registry.uses_fakes,
        },
    )
    try:
        yield
    finally:
        if app.state.scheduler is not None:
            app.state.scheduler.shutdown(wait=False)
        if app.state.bot is not None:
            await app.state.bot.session.close()
        await app.state.http_client.aclose()
        await app.state.redis.aclose()
        await engine.dispose()
        logger.info("shutdown", extra={"event": "shutdown"})


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="Memora API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.ENV != "prod" else None,
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router)
    # Not under /api/v1, per SPEC §7.
    app.include_router(telegram_router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, Any]:
        """Reports dependency reachability. See DECISIONS.md D5 for why this is 200."""
        db_ok = await _check_db()
        redis_ok = await _check_redis(app)
        return {
            "status": "ok" if (db_ok and redis_ok) else "degraded",
            "db": "up" if db_ok else "down",
            "redis": "up" if redis_ok else "down",
            "version": app.version,
        }

    return app


async def _check_db() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # dependency probe: report, never raise
        logger.warning("db_unreachable", extra={"event": "db_unreachable", "error": str(exc)})
        return False
    return True


async def _check_redis(app: FastAPI) -> bool:
    try:
        await app.state.redis.ping()
    except Exception as exc:  # dependency probe: report, never raise
        logger.warning("redis_unreachable", extra={"event": "redis_unreachable", "error": str(exc)})
        return False
    return True


app = create_app()
