"""Fixed-window rate limiting on Redis (SPEC §8.3).

Fixed windows are chosen over sliding ones deliberately: one `INCR` plus one
conditional `EXPIRE` per request, and the abuse this guards against is bulk, not
burst-at-the-boundary.
"""

from redis.asyncio import Redis

from app.core.errors import RateLimitedError
from app.core.logging import get_logger

logger = get_logger(__name__)


async def hit(redis: Redis, key: str, *, limit: int, window_seconds: int) -> int:
    """Count one request against `key`. Returns the remaining allowance.

    Raises `RateLimitedError` with a `Retry-After` header once the limit is passed.
    A Redis outage must not take the API down with it, so failures here open the gate
    and log loudly.
    """
    try:
        pipeline = redis.pipeline()
        pipeline.incr(key)
        pipeline.ttl(key)
        count, ttl = await pipeline.execute()

        if ttl is None or ttl < 0:
            await redis.expire(key, window_seconds)
            ttl = window_seconds
    except Exception as exc:  # Redis down: fail open, never 500 the user
        logger.warning(
            "rate_limit_unavailable",
            extra={"event": "rate_limit_unavailable", "error": str(exc)},
        )
        return limit

    if count > limit:
        raise RateLimitedError(
            "Juda ko'p so'rov. Biroz kuting.",
            details={"limit": limit, "window_seconds": window_seconds},
            headers={"Retry-After": str(max(ttl, 1))},
        )
    return max(limit - int(count), 0)
