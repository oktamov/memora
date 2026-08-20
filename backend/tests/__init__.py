"""Test package bootstrap.

This module runs before `conftest.py` (pytest imports the package first), which is the
only place early enough to redirect the database and Redis URLs before
`app.db.session` builds its engine at import time.
"""

import asyncio
import os
from urllib.parse import urlsplit, urlunsplit

_DEFAULT_DB = "postgresql+asyncpg://memora:memora@localhost:5433/memora"
_DEFAULT_REDIS = "redis://localhost:6380/0"


def _test_database_url() -> str:
    """A `_test` sibling of the configured database.

    The development database belongs to Alembic; tests drop and recreate tables on
    every case, so they must never share it.
    """
    parts = urlsplit(os.environ.get("DATABASE_URL") or _DEFAULT_DB)
    if parts.path.endswith("_test"):
        return urlunsplit(parts)
    return urlunsplit(parts._replace(path=f"{parts.path}_test"))


def _test_redis_url() -> str:
    """Redis DB 15 is scratch space for tests; the app uses 0."""
    base = (os.environ.get("REDIS_URL") or _DEFAULT_REDIS).rsplit("/", 1)[0]
    return f"{base}/15"


async def _create_test_database_if_missing(url: str) -> None:
    import asyncpg

    parts = urlsplit(url)
    database = parts.path.lstrip("/")
    dsn = urlunsplit(parts._replace(scheme="postgresql", path="/postgres", query=""))

    connection = await asyncpg.connect(dsn)
    try:
        exists = await connection.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database)
        if not exists:
            await connection.execute(f'CREATE DATABASE "{database}"')
    finally:
        await connection.close()


os.environ["JWT_SECRET"] = os.environ.get("JWT_SECRET", "test-secret-long-enough-for-hmac-sha256")
os.environ["DATABASE_URL"] = _test_database_url()
os.environ["REDIS_URL"] = _test_redis_url()

asyncio.run(_create_test_database_if_missing(os.environ["DATABASE_URL"]))
