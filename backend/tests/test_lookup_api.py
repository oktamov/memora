"""M2 acceptance (SPEC §11): `/lookup` for `run` (en→uz) returns ≥3 meanings, and a
second identical request from a *different* user hits the cache."""

import time
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.lookup import LookupCache
from app.services import lookup_service

RUN = {"term": "run", "source_lang": "en", "target_lang": "uz"}


async def test_lookup_run_en_uz_returns_at_least_three_meanings(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["term"] == "run"
    assert body["target_lang"] == "uz"
    assert len(body["meanings"]) >= 3
    assert body["cache"] == "miss"
    assert body["ipa"]


async def test_a_repeat_lookup_is_served_warm(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)

    started = time.perf_counter()
    second = await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert second.json()["cache"] == "redis"
    # SPEC §11 M2: <50ms warm. In-process, so this measures the cache path itself.
    assert elapsed_ms < 50


async def test_a_different_user_hits_the_same_global_cache(
    client: AsyncClient, auth_headers: dict[str, str], other_auth_headers: dict[str, str]
) -> None:
    """SPEC §5, §13: the cache is global. A per-user cache multiplies the bill."""
    first = await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)
    assert first.json()["cache"] == "miss"

    second = await client.post("/api/v1/lookup", headers=other_auth_headers, json=RUN)

    assert second.json()["cache"] in {"redis", "db"}
    assert second.json()["meanings"] == first.json()["meanings"]


async def test_a_cache_hit_does_not_count_against_quota(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """SPEC §8.2: only calls that reach a provider are counted."""
    first = await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)
    used_after_miss = first.json()["quota_used"]

    second = await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)

    assert used_after_miss == 1
    assert second.json()["quota_used"] == 1


async def test_the_database_layer_serves_a_lookup_when_redis_is_cold(
    client: AsyncClient, auth_headers: dict[str, str], app: FastAPI, db_session: AsyncSession
) -> None:
    await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)
    await app.state.redis.flushdb()

    second = await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)

    assert second.json()["cache"] == "db"

    row = await db_session.scalar(select(LookupCache).where(LookupCache.term == "run"))
    assert row is not None
    assert row.hit_count >= 1


async def test_lookup_never_writes_a_card(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """SPEC §7: `/lookup` is a pure read plus cache."""
    await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)

    decks = await client.get("/api/v1/decks", headers=auth_headers)

    assert decks.json() == []


@pytest.mark.parametrize(
    ("term", "code"),
    [
        ("a" * 65, "term_too_long"),
        ("bir ikki uch to'rt besh", "term_too_many_tokens"),
        ("   ", "term_empty"),
    ],
)
async def test_abusive_input_is_rejected_before_any_provider_call(
    client: AsyncClient, auth_headers: dict[str, str], term: str, code: str
) -> None:
    """SPEC §8.4, §13: this is what stops the app becoming a translation proxy."""
    response = await client.post(
        "/api/v1/lookup",
        headers=auth_headers,
        json={"term": term, "source_lang": "en", "target_lang": "uz"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


async def test_a_paragraph_is_rejected_by_the_schema(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/lookup",
        headers=auth_headers,
        json={"term": "word " * 100, "source_lang": "en", "target_lang": "uz"},
    )

    assert response.status_code == 422


async def test_lookup_requires_authentication(client: AsyncClient) -> None:
    assert (await client.post("/api/v1/lookup", json=RUN)).status_code == 401


async def test_lookup_is_rate_limited_per_user(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """SPEC §8.3: 20 lookups/minute per user."""
    last = None
    for index in range(settings.LOOKUP_RATE_PER_MINUTE + 1):
        last = await client.post(
            "/api/v1/lookup",
            headers=auth_headers,
            json={"term": f"word{index}", "source_lang": "en", "target_lang": "uz"},
        )

    assert last is not None
    assert last.status_code == 429
    assert last.json()["error"]["code"] == "rate_limited"
    assert int(last.headers["Retry-After"]) > 0


async def test_quota_blocks_further_provider_calls(
    client: AsyncClient, auth_headers: dict[str, str], app: FastAPI, monkeypatch: Any
) -> None:
    """SPEC §8.2 and §8.5: a fresh account is capped at 30 lookups/day."""
    monkeypatch.setattr(settings, "NEW_ACCOUNT_LOOKUP_QUOTA", 2)
    monkeypatch.setattr(settings, "LOOKUP_RATE_PER_MINUTE", 100)

    for index in range(2):
        first = await client.post(
            "/api/v1/lookup",
            headers=auth_headers,
            json={"term": f"quota{index}", "source_lang": "en", "target_lang": "uz"},
        )
        assert first.status_code == 200, first.text

    blocked = await client.post(
        "/api/v1/lookup",
        headers=auth_headers,
        json={"term": "quota-overflow", "source_lang": "en", "target_lang": "uz"},
    )

    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "quota_exceeded"
    assert int(blocked.headers["Retry-After"]) > 0


async def test_a_cached_word_still_works_once_the_quota_is_spent(
    client: AsyncClient, auth_headers: dict[str, str], monkeypatch: Any
) -> None:
    """The point of the cache: the ceiling limits cost, not usefulness."""
    monkeypatch.setattr(settings, "LOOKUP_RATE_PER_MINUTE", 100)
    await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)
    monkeypatch.setattr(settings, "NEW_ACCOUNT_LOOKUP_QUOTA", 1)

    cached = await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)

    assert cached.status_code == 200
    assert cached.json()["cache"] == "redis"


async def test_the_global_budget_serves_cache_only_once_exceeded(
    client: AsyncClient, auth_headers: dict[str, str], app: FastAPI, monkeypatch: Any
) -> None:
    """SPEC §8.6."""
    monkeypatch.setattr(settings, "LOOKUP_RATE_PER_MINUTE", 100)
    await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)

    monkeypatch.setattr(settings, "DAILY_PROVIDER_BUDGET", 1)

    cached = await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)
    assert cached.status_code == 200  # cache still serves

    fresh = await client.post(
        "/api/v1/lookup",
        headers=auth_headers,
        json={"term": "budgetword", "source_lang": "en", "target_lang": "uz"},
    )

    assert fresh.status_code == 429
    assert fresh.json()["error"]["code"] == "provider_budget_exceeded"


class _AlwaysFails:
    name = "always_fails"

    def supports(self, source_lang: str) -> bool:
        del source_lang
        return True

    async def lookup(self, *args: Any, **kwargs: Any) -> None:
        from app.providers.base import ProviderError

        raise ProviderError(self.name, "boom")


class _NeverFinds:
    name = "never_finds"

    def supports(self, source_lang: str) -> bool:
        del source_lang
        return True

    async def lookup(self, *args: Any, **kwargs: Any) -> None:
        return None


async def test_a_whole_chain_failure_returns_a_retryable_503(
    client: AsyncClient, auth_headers: dict[str, str], app: FastAPI
) -> None:
    """SPEC §6: never a partial or invented result."""
    app.state.provider_registry.gemini = _AlwaysFails()

    response = await client.post(
        "/api/v1/lookup",
        headers=auth_headers,
        json={"term": "brokenword", "source_lang": "en", "target_lang": "uz"},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "provider_unavailable"
    assert body["error"]["details"]["retryable"] is True


async def test_the_chain_falls_through_to_the_next_provider(
    client: AsyncClient, auth_headers: dict[str, str], app: FastAPI, monkeypatch: Any
) -> None:
    from app.core.config import settings
    from app.providers.dictionary.azure_dictionary import AzureDictionaryProvider

    monkeypatch.setattr(settings, "UZ_PREFER_LLM", False)

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="azure is down")

    registry = app.state.provider_registry
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mocked:
        # Azure leads for en→ru and fails; the fake behind it still answers.
        registry.azure = AzureDictionaryProvider(mocked, key="k", region="r")

        response = await client.post(
            "/api/v1/lookup",
            headers=auth_headers,
            json={"term": "run", "source_lang": "en", "target_lang": "ru"},
        )

    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "fake_dictionary"


async def test_an_unknown_word_is_a_404_not_a_503(
    client: AsyncClient, auth_headers: dict[str, str], app: FastAPI
) -> None:
    app.state.provider_registry.gemini = _NeverFinds()

    response = await client.post(
        "/api/v1/lookup",
        headers=auth_headers,
        json={"term": "zzqqxx", "source_lang": "en", "target_lang": "uz"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "term_not_found"


async def test_lookup_joins_every_translation_into_one_line(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """The product's actual output: one line, nothing to select."""
    response = await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)

    body = response.json()
    assert body["translation"] == "yugurmoq, chopmoq, boshqarmoq, yugurish"
    # ...and the structured form survives for the developer API.
    assert len(body["meanings"]) == 4


def test_normalize_collapses_case_and_whitespace() -> None:
    assert lookup_service.normalize_term("  Run  ") == "run"
    assert lookup_service.normalize_term("New   York") == "new york"
    assert lookup_service.normalize_term("İSTANBUL") == "i̇stanbul"


async def test_case_and_spacing_variants_share_one_cache_entry(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)
    await client.post(
        "/api/v1/lookup",
        headers=auth_headers,
        json={"term": "  RUN ", "source_lang": "en", "target_lang": "uz"},
    )

    rows = (await db_session.scalars(select(LookupCache).where(LookupCache.term == "run"))).all()

    assert len(rows) == 1


# --- Translate: the product loop -------------------------------------------------


async def test_translate_saves_the_word_without_the_user_doing_anything(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post("/api/v1/translate", headers=auth_headers, json=RUN)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["translation"] == "yugurmoq, chopmoq, boshqarmoq, yugurish"
    assert body["already_saved"] is False
    assert "EN → UZ" in body["deck_name"]

    # ...and it is genuinely in the deck, with no second call.
    cards = await client.get(f"/api/v1/decks/{body['deck_id']}/cards", headers=auth_headers)
    assert [item["term"] for item in cards.json()["items"]] == ["run"]


async def test_translating_the_same_word_twice_is_not_an_error(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Asking the same question twice deserves the same answer.

    This runs through the HTTP layer on purpose: the service-level path recovers from a
    failed insert differently than a real request does, and the first version of this
    endpoint returned 500 here while every service test passed.
    """
    first = await client.post("/api/v1/translate", headers=auth_headers, json=RUN)
    second = await client.post("/api/v1/translate", headers=auth_headers, json=RUN)

    assert first.status_code == 200
    assert second.status_code == 200, second.text
    assert second.json()["already_saved"] is True
    assert second.json()["card_id"] == first.json()["card_id"]
    assert second.json()["translation"] == first.json()["translation"]


async def test_translate_files_each_language_pair_in_its_own_deck(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await client.post("/api/v1/translate", headers=auth_headers, json=RUN)
    await client.post(
        "/api/v1/translate",
        headers=auth_headers,
        json={"term": "voda", "source_lang": "ru", "target_lang": "uz"},
    )

    decks = await client.get("/api/v1/decks", headers=auth_headers)
    pairs = {(deck["source_lang"], deck["target_lang"]) for deck in decks.json()}

    assert pairs == {("en", "uz"), ("ru", "uz")}


async def test_translate_falls_back_to_the_users_remembered_pair(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """The app sends the pair explicitly; the bot and a bare API call need not."""
    await client.patch(
        "/api/v1/auth/me", headers=auth_headers, json={"source_lang": "de", "native_lang": "ru"}
    )

    response = await client.post("/api/v1/translate", headers=auth_headers, json={"term": "haus"})

    assert response.json()["source_lang"] == "de"
    assert response.json()["target_lang"] == "ru"


async def test_lookup_does_not_save_anything(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """`/lookup` stays a pure read, which is what a public developer API must be."""
    await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)

    decks = await client.get("/api/v1/decks", headers=auth_headers)

    assert decks.json() == []


async def test_fixture_results_are_not_served_once_a_real_provider_exists(
    client: AsyncClient, auth_headers: dict[str, str], app: FastAPI, db_session: AsyncSession
) -> None:
    """A word translated before the key was added must not stay placeholder forever.

    The database cache has no TTL, so without this the user adds a Gemini key, sees no
    change for any word they already tried, and has no way to tell why.
    """
    from app.providers.base import LookupResult, Meaning

    # Cached while the app was running on fixtures.
    first = await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)
    assert first.json()["provider"] == "fake_dictionary"

    class RealProvider:
        name = "gemini"

        def supports(self, source_lang: str) -> bool:
            del source_lang
            return True

        async def lookup(self, term: str, source_lang: str, target_lang: str) -> LookupResult:
            return LookupResult(
                term=term,
                source_lang=source_lang,
                target_lang=target_lang,
                ipa="/rʌn/",
                meanings=[Meaning(pos="verb", definition="yugurmoq", gloss_en=None)],
                provider=self.name,
            )

    app.state.provider_registry.gemini = RealProvider()

    second = await client.post("/api/v1/lookup", headers=auth_headers, json=RUN)

    assert second.json()["provider"] == "gemini"
    assert second.json()["translation"] == "yugurmoq"
