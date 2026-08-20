"""SPEC §8.3: 60 requests/minute per IP on auth endpoints, answered with 429 +
`Retry-After`."""

from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import settings
from app.core.ratelimit import hit
from tests.factories import make_init_data


async def test_auth_is_rate_limited_per_ip(client: AsyncClient) -> None:
    payload = {"init_data": make_init_data(telegram_id=31337)}

    last = None
    for _ in range(settings.AUTH_RATE_PER_MINUTE_PER_IP + 1):
        last = await client.post("/api/v1/auth/telegram", json=payload)

    assert last is not None
    assert last.status_code == 429
    assert last.json()["error"]["code"] == "rate_limited"
    assert int(last.headers["Retry-After"]) > 0


async def test_the_window_is_scoped_per_ip(client: AsyncClient) -> None:
    payload = {"init_data": make_init_data(telegram_id=31338)}

    for _ in range(settings.AUTH_RATE_PER_MINUTE_PER_IP + 1):
        await client.post(
            "/api/v1/auth/telegram", json=payload, headers={"X-Forwarded-For": "1.1.1.1"}
        )

    # A different IP starts with a fresh allowance.
    other = await client.post(
        "/api/v1/auth/telegram", json=payload, headers={"X-Forwarded-For": "2.2.2.2"}
    )

    assert other.status_code == 200


async def test_rate_limiting_fails_open_when_redis_is_unreachable(app: FastAPI) -> None:
    """A Redis outage must degrade the limiter, not the API."""
    from redis.asyncio import from_url

    broken = from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.05)

    remaining = await hit(broken, "rl:test", limit=5, window_seconds=60)

    assert remaining == 5
    await broken.aclose()
