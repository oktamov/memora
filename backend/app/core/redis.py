"""Redis client factory. One pool per process, stored on `app.state`."""

from redis.asyncio import Redis, from_url

from app.core.config import settings


def create_redis() -> Redis:
    return from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )
