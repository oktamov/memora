"""Per-user lookup quota and the global provider budget (SPEC §8).

Both counters live in Redis. Only calls that actually reach a provider are counted —
cache hits are free, which is the entire economic argument for the cache.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from redis.asyncio import Redis

from app.core.config import settings
from app.core.errors import ProviderBudgetExceededError, QuotaExceededError
from app.core.logging import get_logger
from app.models.user import User

logger = get_logger(__name__)


def _zone(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def seconds_until_local_midnight(user: User, *, now: datetime | None = None) -> int:
    """SPEC §8.2: the quota key expires at the *user's* local midnight."""
    moment = (now or datetime.now(UTC)).astimezone(_zone(user))
    tomorrow = (moment + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(int((tomorrow - moment).total_seconds()), 1)


def effective_quota(user: User, *, now: datetime | None = None) -> int:
    """SPEC §8.5: accounts younger than 24h get a reduced quota.

    There is no email verification here, so this is one of the few signals available.
    No heuristic goes beyond our own `users.created_at`, per the spec.
    """
    moment = now or datetime.now(UTC)
    created = user.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)

    if moment - created < timedelta(hours=settings.NEW_ACCOUNT_WINDOW_HOURS):
        return min(user.lookup_quota_per_day, settings.NEW_ACCOUNT_LOOKUP_QUOTA)
    return user.lookup_quota_per_day


def quota_key(user: User, *, now: datetime | None = None) -> str:
    day = (now or datetime.now(UTC)).astimezone(_zone(user)).date()
    return f"quota:lookup:{user.id}:{day.isoformat()}"


def budget_key(*, now: datetime | None = None) -> str:
    return f"budget:provider:{(now or datetime.now(UTC)).date().isoformat()}"


async def quota_used(redis: Redis, user: User, *, now: datetime | None = None) -> int:
    try:
        raw = await redis.get(quota_key(user, now=now))
    except Exception as exc:  # Redis down: report zero rather than 500 the lookup
        logger.warning("quota_unavailable", extra={"event": "quota_unavailable", "error": str(exc)})
        return 0
    return int(raw or 0)


async def assert_quota_available(redis: Redis, user: User, *, now: datetime | None = None) -> None:
    """Check before calling a provider. Raises `QuotaExceededError` at the ceiling."""
    limit = effective_quota(user, now=now)
    used = await quota_used(redis, user, now=now)
    if used >= limit:
        raise QuotaExceededError(
            "Bugungi lug'at limiti tugadi. Ertaga yana urinib ko'ring.",
            details={"limit": limit, "used": used},
            headers={"Retry-After": str(seconds_until_local_midnight(user, now=now))},
        )


async def consume_quota(redis: Redis, user: User, *, now: datetime | None = None) -> int:
    """Count one provider call. Never called on a cache hit (SPEC §8.2)."""
    key = quota_key(user, now=now)
    try:
        used = await redis.incr(key)
        if used == 1:
            await redis.expire(key, seconds_until_local_midnight(user, now=now))
    except Exception as exc:  # fail open; the budget below is the hard ceiling
        logger.warning(
            "quota_increment_failed",
            extra={"event": "quota_increment_failed", "error": str(exc)},
        )
        return 0
    return int(used)


async def assert_budget_available(redis: Redis, *, now: datetime | None = None) -> None:
    """SPEC §8.6: a hard global ceiling. Past it we serve cache only, and log loudly."""
    key = budget_key(now=now)
    try:
        spent = int(await redis.get(key) or 0)
    except Exception as exc:
        logger.warning(
            "budget_unavailable", extra={"event": "budget_unavailable", "error": str(exc)}
        )
        return

    if spent >= settings.DAILY_PROVIDER_BUDGET:
        logger.error(
            "provider_budget_exceeded",
            extra={
                "event": "provider_budget_exceeded",
                "spent": spent,
                "budget": settings.DAILY_PROVIDER_BUDGET,
            },
        )
        raise ProviderBudgetExceededError(
            "Tizim bugungi lug'at chekloviga yetdi. Keshdagi so'zlar ishlaydi.",
            details={"budget": settings.DAILY_PROVIDER_BUDGET},
        )


async def consume_budget(redis: Redis, *, now: datetime | None = None) -> int:
    key = budget_key(now=now)
    try:
        spent = await redis.incr(key)
        if spent == 1:
            await redis.expire(key, 2 * 24 * 60 * 60)
    except Exception as exc:
        logger.warning(
            "budget_increment_failed",
            extra={"event": "budget_increment_failed", "error": str(exc)},
        )
        return 0
    return int(spent)
