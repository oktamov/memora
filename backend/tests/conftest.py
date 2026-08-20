"""Shared test fixtures.

Tests run against the ASGI app in-process via `httpx.ASGITransport` (SPEC §3).
No network, no live providers.
"""

import os
from collections.abc import AsyncIterator

os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "")

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client:
        # Lifespan is not run by ASGITransport, so wire the shared resources by hand.
        import httpx as _httpx

        from app.core.redis import create_redis

        app.state.http_client = _httpx.AsyncClient()
        app.state.redis = create_redis()
        try:
            yield http_client
        finally:
            await app.state.http_client.aclose()
            await app.state.redis.aclose()
