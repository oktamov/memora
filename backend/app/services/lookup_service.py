"""The lookup pipeline (SPEC §6).

    normalize(term)
      → Redis GET  (TTL 24h)   → hit? return
      → lookup_cache SELECT    → hit? warm Redis, increment hit_count, return
      → provider chain
      → persist to lookup_cache + Redis
      → return

The cache is global and shared across every user (SPEC §5, §13). Cache hits cost
nothing and are never counted against a user's quota (SPEC §8.2).
"""

from __future__ import annotations

import json
import time
import unicodedata
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.config import settings
from app.core.errors import NotFoundError, ProviderUnavailableError, ValidationError
from app.core.logging import get_logger, log_provider_call
from app.models.lookup import LookupCache
from app.models.user import User
from app.providers.base import DictionaryProvider, LookupResult, ProviderError
from app.providers.registry import ProviderRegistry
from app.services import quota_service

logger = get_logger(__name__)

CACHE_MISS = "miss"

#: Providers that serve fixture data. Anything they produced must never outlive the
#: moment a real credential appears — see `_is_stale_fixture`.
FIXTURE_PROVIDERS = ("fake_dictionary", "fake_translation")
CACHE_REDIS = "redis"
CACHE_DATABASE = "db"


@dataclass(frozen=True, slots=True)
class LookupOutcome:
    """A result plus how it was obtained — the API surfaces this for the frontend."""

    result: LookupResult
    cache: str
    quota_used: int
    quota_limit: int


def joined_translation(result: LookupResult) -> str:
    """Every translation as one comma-separated line.

    This is the product's actual output: the user types a word and reads one line, with
    nothing to select and nothing to tap.
    """
    return ", ".join(meaning.definition for meaning in result.meanings)


def normalize_term(term: str) -> str:
    """Trim, collapse inner whitespace, NFC-normalize, casefold.

    Casefolding is unconditional: the cache key must be stable, and a word saved onto a
    card keeps the user's own spelling in `display_term` anyway.
    """
    collapsed = " ".join(term.strip().split())
    return unicodedata.normalize("NFC", collapsed).casefold()


def validate_term(term: str) -> str:
    """SPEC §8.4: ≤64 characters, ≤4 whitespace-separated tokens.

    This is what stops the app becoming a free translation proxy — the realistic abuse
    vector, and the one that arrives as a bill at the end of the month (SPEC §13).
    """
    normalized = normalize_term(term)

    if not normalized:
        raise ValidationError("So'z kiritilmadi.", code="term_empty")
    if len(normalized) > settings.LOOKUP_MAX_CHARS:
        raise ValidationError(
            f"So'z juda uzun. Ko'pi bilan {settings.LOOKUP_MAX_CHARS} belgi.",
            code="term_too_long",
            details={"max_chars": settings.LOOKUP_MAX_CHARS, "length": len(normalized)},
        )

    tokens = normalized.split(" ")
    if len(tokens) > settings.LOOKUP_MAX_TOKENS:
        raise ValidationError(
            f"Bu ilova so'z va qisqa iboralar uchun. Ko'pi bilan "
            f"{settings.LOOKUP_MAX_TOKENS} ta so'z.",
            code="term_too_many_tokens",
            details={"max_tokens": settings.LOOKUP_MAX_TOKENS, "tokens": len(tokens)},
        )
    return normalized


def _redis_key(term: str, source_lang: str, target_lang: str) -> str:
    return f"lookup:{source_lang}:{target_lang}:{term}"


async def lookup(
    *,
    session: AsyncSession,
    redis: Redis,
    registry: ProviderRegistry,
    user: User,
    term: str,
    source_lang: str,
    target_lang: str,
    now: datetime | None = None,
) -> LookupOutcome:
    """Run the pipeline for one term."""
    normalized = validate_term(term)
    moment = now or datetime.now(UTC)
    limit = quota_service.effective_quota(user, now=moment)

    cached = await _from_redis(redis, normalized, source_lang, target_lang)
    if cached is not None and _is_stale_fixture(cached, registry):
        cached = None
    if cached is not None:
        used = await quota_service.quota_used(redis, user, now=moment)
        _log(normalized, source_lang, target_lang, cached.provider, 0.0, CACHE_REDIS, False, True)
        return LookupOutcome(cached, CACHE_REDIS, used, limit)

    from_db = await _from_database(session, normalized, source_lang, target_lang)
    if from_db is not None and _is_stale_fixture(from_db, registry):
        from_db = None
    if from_db is not None:
        await _write_redis(redis, normalized, source_lang, target_lang, from_db)
        used = await quota_service.quota_used(redis, user, now=moment)
        _log(
            normalized, source_lang, target_lang, from_db.provider, 0.0, CACHE_DATABASE, False, True
        )
        return LookupOutcome(from_db, CACHE_DATABASE, used, limit)

    # Only a real provider call is gated and counted.
    await quota_service.assert_quota_available(redis, user, now=moment)
    await quota_service.assert_budget_available(redis, now=moment)

    result = await _from_providers(registry, normalized, source_lang, target_lang)

    used = await quota_service.consume_quota(redis, user, now=moment)
    await quota_service.consume_budget(redis, now=moment)

    await _persist(session, normalized, source_lang, target_lang, result)
    await _write_redis(redis, normalized, source_lang, target_lang, result)

    return LookupOutcome(result, CACHE_MISS, used, limit)


async def _from_redis(
    redis: Redis, term: str, source_lang: str, target_lang: str
) -> LookupResult | None:
    try:
        raw = await redis.get(_redis_key(term, source_lang, target_lang))
    except Exception as exc:  # a cold cache is not an outage
        logger.warning(
            "lookup_cache_unavailable",
            extra={"event": "lookup_cache_unavailable", "layer": "redis", "error": str(exc)},
        )
        return None

    if not raw:
        return None
    try:
        return LookupResult.from_dict(json.loads(raw))
    except (ValueError, KeyError):
        # A poisoned entry should not break the request; fall through to the database.
        return None


async def _write_redis(
    redis: Redis, term: str, source_lang: str, target_lang: str, result: LookupResult
) -> None:
    try:
        await redis.set(
            _redis_key(term, source_lang, target_lang),
            json.dumps(result.to_dict(), ensure_ascii=False),
            ex=settings.REDIS_LOOKUP_TTL_SECONDS,
        )
    except Exception as exc:
        logger.warning(
            "lookup_cache_write_failed",
            extra={"event": "lookup_cache_write_failed", "layer": "redis", "error": str(exc)},
        )


async def _from_database(
    session: AsyncSession, term: str, source_lang: str, target_lang: str
) -> LookupResult | None:
    """Read the global cache and bump `hit_count` in the same round trip."""
    statement = (
        update(LookupCache)
        .where(
            LookupCache.term == term,
            LookupCache.source_lang == source_lang,
            LookupCache.target_lang == target_lang,
        )
        .values(hit_count=LookupCache.hit_count + 1)
        .returning(LookupCache.payload)
    )
    payload = await session.scalar(statement)
    await session.commit()

    if payload is None:
        return None
    try:
        return LookupResult.from_dict(payload)
    except (ValueError, KeyError):
        return None


async def _persist(
    session: AsyncSession, term: str, source_lang: str, target_lang: str, result: LookupResult
) -> None:
    """Upsert into the global cache. Two users racing on the same new word is normal."""
    statement = (
        pg_insert(LookupCache)
        .values(
            id=uuid7(),
            term=term,
            source_lang=source_lang,
            target_lang=target_lang,
            provider=result.provider[:32],
            payload=result.to_dict(),
        )
        .on_conflict_do_nothing(index_elements=["term", "source_lang", "target_lang"])
    )
    await session.execute(statement)
    await session.commit()


async def _from_providers(
    registry: ProviderRegistry, term: str, source_lang: str, target_lang: str
) -> LookupResult:
    """Walk the chain. A provider that raises or times out is skipped (SPEC §6).

    If every provider fails, raise 503 — never a partial or invented result. If a
    provider answered honestly that the word does not exist, that is a 404 instead:
    the chain worked, the word did not.
    """
    chain = registry.chain_for(source_lang, target_lang)
    failures: list[str] = []
    answered_not_found = False

    for provider in chain.providers:
        started = time.perf_counter()
        try:
            raw = await _call_with_one_retry(provider, term, source_lang, target_lang)
        except Exception as exc:
            # ProviderError is the expected shape, but a provider bug of any kind must
            # not take the chain down — the next provider still gets its turn.
            failures.append(f"{provider.name}: {exc}")
            _log(
                term,
                source_lang,
                target_lang,
                provider.name,
                (time.perf_counter() - started) * 1000,
                CACHE_MISS,
                True,
                False,
                error=str(exc),
            )
            continue

        latency_ms = (time.perf_counter() - started) * 1000

        if raw is None:
            answered_not_found = True
            _log(term, source_lang, target_lang, provider.name, latency_ms, CACHE_MISS, True, True)
            continue

        raw.target_lang = target_lang
        _log(term, source_lang, target_lang, provider.name, latency_ms, CACHE_MISS, True, True)
        return raw

    if answered_not_found and not failures:
        raise NotFoundError("Bu so'z topilmadi.", code="term_not_found")

    logger.error(
        "lookup_chain_failed",
        extra={
            "event": "lookup_chain_failed",
            "source_lang": source_lang,
            "target_lang": target_lang,
            "failures": failures,
        },
    )
    raise ProviderUnavailableError(
        "Tarjimon hozir javob bermayapti. Birozdan so'ng urinib ko'ring.",
        details={"retryable": True},
    )


def _log(
    term: str,
    source_lang: str,
    target_lang: str,
    provider: str,
    latency_ms: float,
    cache: str,
    counted: bool,
    ok: bool,
    error: str | None = None,
) -> None:
    """SPEC §12: log the call, never the payload."""
    log_provider_call(
        logger,
        provider=provider,
        term_length=len(term),
        source_lang=source_lang,
        target_lang=target_lang,
        latency_ms=latency_ms,
        cache=cache,
        counted_against_quota=counted,
        ok=ok,
        error=error,
    )


async def _call_with_one_retry(
    provider: DictionaryProvider, term: str, source_lang: str, target_lang: str
) -> LookupResult | None:
    """Call a provider, retrying once on a connection-level failure.

    Measured at roughly one transient failure in sixteen live calls. Without a retry
    that is a user typing a word, reading "the translator is not responding", and
    typing it again — in an app whose entire premise is that they do nothing extra.
    A 4xx is never retried: the same request earns the same refusal.
    """
    # Every provider in this chain takes target_lang; the two-argument form in the
    # Protocol is the default for a plain dictionary, which nothing routes to now.
    call = cast(
        "Callable[[str, str, str], Awaitable[LookupResult | None]]",
        provider.lookup,
    )

    try:
        return await call(term, source_lang, target_lang)
    except ProviderError as exc:
        if not exc.retryable:
            raise
        logger.warning(
            "provider_retry",
            extra={"event": "provider_retry", "provider": exc.provider, "error": str(exc)},
        )
        return await call(term, source_lang, target_lang)


def _is_stale_fixture(result: LookupResult, registry: ProviderRegistry) -> bool:
    """True for a cached entry that fixture providers produced, once real ones exist.

    The cache has no TTL in the database, so a word looked up before a provider key was
    configured would keep serving placeholder text forever — the user adds a key,
    nothing changes for any word they already tried, and there is no signal why.
    Detected rather than cleared by hand, because the same thing happens on every
    environment that runs without keys first.
    """
    return result.provider in FIXTURE_PROVIDERS and not registry.uses_fakes
