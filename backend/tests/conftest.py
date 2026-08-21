"""Shared test fixtures.

`tests/__init__.py` has already redirected the database and Redis URLs by the time
this module is imported.

Tests run against the ASGI app in-process via `httpx.ASGITransport` (SPEC §3) and
against a real Postgres — the schema uses partial unique indexes and `ON CONFLICT`,
neither of which SQLite can stand in for.

The database is the one Compose publishes (`docker compose up -d db redis`); each test
gets its own transaction-less schema reset so tests stay independent.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.redis import create_redis
from app.db.base import Base
from app.db.session import async_session_factory, engine
from app.main import create_app
from app.models.user import User
from app.providers.registry import ProviderRegistry
from app.services import auth_service
from tests.factories import DUMMY_BOT_TOKEN, make_init_data


def pytest_configure() -> None:
    """Tests sign initData with the dummy token, so the app must verify against it."""
    settings.TELEGRAM_BOT_TOKEN = DUMMY_BOT_TOKEN


@pytest.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    """Drop and recreate every table before each test.

    `Base.metadata.create_all` is used *only here*. Production schema changes always go
    through Alembic (SPEC §12).
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


@pytest.fixture
async def app() -> AsyncIterator[FastAPI]:
    """The real app, with the resources the lifespan would normally create."""
    instance = create_app()
    instance.state.http_client = httpx.AsyncClient()
    instance.state.redis = create_redis()
    instance.state.provider_registry = ProviderRegistry(instance.state.http_client)
    try:
        await instance.state.redis.flushdb()
        yield instance
    finally:
        await instance.state.http_client.aclose()
        await instance.state.redis.aclose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http_client:
        yield http_client


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    """A user created the way production creates one: through validated initData."""
    created, _ = await auth_service.authenticate_init_data(
        db_session, make_init_data(telegram_id=777_000_111, username="reader")
    )
    return created


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    """A live `Authorization: Bearer` header for the default test user."""
    response = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": make_init_data(telegram_id=777_000_111, username="reader")},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def other_auth_headers(client: AsyncClient) -> dict[str, str]:
    """A second user, for cross-tenant isolation tests."""
    response = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": make_init_data(telegram_id=888_000_222, username="stranger")},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
