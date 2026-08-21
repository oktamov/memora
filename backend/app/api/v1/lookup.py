"""Translation endpoints.

`POST /translate` is what the app uses: it translates and files the word in one call,
because the product's whole promise is that saving costs the user nothing.

`POST /lookup` is the same translation without the saving — a pure read, which is what
a public developer API needs to be.
"""

from fastapi import APIRouter, Request

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, RedisClient
from app.core.ratelimit import hit
from app.providers.registry import ProviderRegistry
from app.schemas.lookup import (
    LookupRequest,
    LookupResponse,
    MeaningResponse,
    TranslateResponse,
)
from app.services import lookup_service, translate_service

router = APIRouter(tags=["translate"])


async def _rate_limit(redis: RedisClient, user: CurrentUser) -> None:
    # SPEC §8.3: 20 lookups/minute per user.
    await hit(
        redis,
        f"rl:lookup:user:{user.id}",
        limit=settings.LOOKUP_RATE_PER_MINUTE,
        window_seconds=60,
    )


def _meanings(result: object) -> list[MeaningResponse]:
    return [
        MeaningResponse(
            pos=meaning.pos,
            definition=meaning.definition,
            gloss_en=meaning.gloss_en,
            examples=list(meaning.examples),
        )
        for meaning in result.meanings  # type: ignore[attr-defined]
    ]


@router.post("/translate", response_model=TranslateResponse)
async def translate(
    payload: LookupRequest,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    redis: RedisClient,
) -> TranslateResponse:
    """Translate a word and keep it. The user does nothing else."""
    await _rate_limit(redis, user)

    registry: ProviderRegistry = request.app.state.provider_registry
    outcome = await translate_service.translate_and_save(
        session=session,
        redis=redis,
        registry=registry,
        user=user,
        term=payload.term,
        source_lang=payload.source_lang or user.source_lang,
        target_lang=payload.target_lang or user.native_lang,
    )

    result = outcome.result
    return TranslateResponse(
        term=result.term,  # type: ignore[attr-defined]
        source_lang=result.source_lang,  # type: ignore[attr-defined]
        target_lang=result.target_lang,  # type: ignore[attr-defined]
        ipa=result.ipa,  # type: ignore[attr-defined]
        translation=outcome.translation,
        meanings=_meanings(result),
        provider=result.provider,  # type: ignore[attr-defined]
        cache=outcome.cache,
        quota_used=outcome.quota_used,
        quota_limit=outcome.quota_limit,
        card_id=outcome.card.id,
        deck_id=outcome.card.deck_id,
        deck_name=outcome.deck_name,
        already_saved=outcome.already_saved,
    )


@router.post("/lookup", response_model=LookupResponse)
async def lookup(
    payload: LookupRequest,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    redis: RedisClient,
) -> LookupResponse:
    """Translate without saving. Pure read plus cache — the shape a public API takes."""
    await _rate_limit(redis, user)

    registry: ProviderRegistry = request.app.state.provider_registry
    outcome = await lookup_service.lookup(
        session=session,
        redis=redis,
        registry=registry,
        user=user,
        term=payload.term,
        source_lang=payload.source_lang or user.source_lang,
        target_lang=payload.target_lang or user.native_lang,
    )

    return LookupResponse(
        term=outcome.result.term,
        source_lang=outcome.result.source_lang,
        target_lang=outcome.result.target_lang,
        ipa=outcome.result.ipa,
        translation=lookup_service.joined_translation(outcome.result),
        meanings=_meanings(outcome.result),
        provider=outcome.result.provider,
        cache=outcome.cache,
        quota_used=outcome.quota_used,
        quota_limit=outcome.quota_limit,
    )
