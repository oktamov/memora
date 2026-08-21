"""`POST /lookup` (SPEC §7).

Never writes a card. Pure read plus cache, rate limited and quota'd.
"""

from fastapi import APIRouter, Request

from app.core.config import settings
from app.core.deps import CurrentUser, DbSession, RedisClient
from app.core.ratelimit import hit
from app.providers.registry import ProviderRegistry
from app.schemas.lookup import LookupRequest, LookupResponse, MeaningResponse
from app.services import lookup_service

router = APIRouter(tags=["lookup"])


@router.post("/lookup", response_model=LookupResponse)
async def lookup(
    payload: LookupRequest,
    request: Request,
    user: CurrentUser,
    session: DbSession,
    redis: RedisClient,
) -> LookupResponse:
    # SPEC §8.3: 20 lookups/minute per user.
    await hit(
        redis,
        f"rl:lookup:user:{user.id}",
        limit=settings.LOOKUP_RATE_PER_MINUTE,
        window_seconds=60,
    )

    registry: ProviderRegistry = request.app.state.provider_registry
    outcome = await lookup_service.lookup(
        session=session,
        redis=redis,
        registry=registry,
        user=user,
        term=payload.term,
        source_lang=payload.source_lang,
        target_lang=payload.target_lang,
    )

    return LookupResponse(
        term=outcome.result.term,
        source_lang=outcome.result.source_lang,
        target_lang=outcome.result.target_lang,
        ipa=outcome.result.ipa,
        meanings=[
            MeaningResponse(
                pos=meaning.pos,
                definition=meaning.definition,
                gloss_en=meaning.gloss_en,
                examples=list(meaning.examples),
            )
            for meaning in outcome.result.meanings
        ],
        provider=outcome.result.provider,
        cache=outcome.cache,
        quota_used=outcome.quota_used,
        quota_limit=outcome.quota_limit,
    )
