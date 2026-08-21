"""Translate a word and keep it — the whole product loop, in one call.

SPEC §7 says "`/lookup` never writes a card". That was written for a flow where the
user picked which meanings to keep. The product is a translator now: the user types a
word, reads one line, and the word is already saved. Requiring a second tap to keep it
would be the one piece of friction the app exists to remove.

So this module is the seam: `lookup_service` still does a pure read, and saving is a
separate, explicit step layered on top — which keeps the cache honest and leaves
`POST /lookup` usable as a read-only translation API for developers later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.core.logging import get_logger
from app.models.card import Card
from app.models.user import User
from app.providers.registry import ProviderRegistry
from app.services import card_service, deck_service, lookup_service

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TranslateOutcome:
    """What the user sees, plus where it went."""

    result: object  # LookupResult; kept loose so schemas own the wire shape
    translation: str
    cache: str
    quota_used: int
    quota_limit: int
    card: Card
    deck_name: str
    already_saved: bool


async def translate_and_save(
    *,
    session: AsyncSession,
    redis: Redis,
    registry: ProviderRegistry,
    user: User,
    term: str,
    source_lang: str,
    target_lang: str,
    now: datetime | None = None,
) -> TranslateOutcome:
    """Translate, then file the word into today's deck for that language pair."""
    moment = now or datetime.now(UTC)

    outcome = await lookup_service.lookup(
        session=session,
        redis=redis,
        registry=registry,
        user=user,
        term=term,
        source_lang=source_lang,
        target_lang=target_lang,
        now=moment,
    )

    deck = await deck_service.get_or_create_daily_deck(
        session, user, source_lang=source_lang, target_lang=target_lang, now=moment
    )
    # Snapshot before the write. A failed flush expires every ORM object, and reading
    # `deck.id` afterwards attempts lazy IO outside the async context — the same trap
    # as DECISIONS.md D12, which the duplicate path walks straight into.
    deck_id = deck.id
    deck_name = deck.name

    translation = lookup_service.joined_translation(outcome.result)

    # Look before inserting. Translating the same word twice is an ordinary thing to
    # do, not an exception — and recovering from the failed INSERT is worse than
    # avoiding it: `create_card` rolls the session back, after which the very next
    # SELECT on it re-raises the original IntegrityError.
    existing = await card_service.find_in_deck(session, user, deck_id=deck_id, term=term)
    already_saved = existing is not None

    if existing is not None:
        card = existing
    else:
        try:
            card = await card_service.create_card(
                session,
                user,
                deck_id=deck_id,
                term=term,
                ipa=outcome.result.ipa,
                pos=outcome.result.meanings[0].pos if outcome.result.meanings else None,
                # Exactly the SPEC §5 shape. `Meaning.to_dict()` also carries
                # `examples`, which the card schema rightly refuses.
                meanings=[
                    {
                        "pos": meaning.pos,
                        "definition": meaning.definition,
                        "gloss_en": meaning.gloss_en,
                    }
                    for meaning in outcome.result.meanings
                ],
                now=moment,
            )
        except ConflictError as exc:
            # Two devices saving the same word at once. The row the winner wrote is
            # the right answer, so re-read it on a session that is still usable.
            if exc.code != "card_duplicate":
                raise
            async with session.begin_nested():
                pass
            raced = await card_service.find_in_deck(session, user, deck_id=deck_id, term=term)
            if raced is None:  # pragma: no cover — the row was just reported present
                raise
            card = raced
            already_saved = True

    logger.info(
        "word_saved",
        extra={
            "event": "word_saved",
            "user_id": str(user.id),
            "source_lang": source_lang,
            "target_lang": target_lang,
            "cache": outcome.cache,
            "already_saved": already_saved,
        },
    )

    return TranslateOutcome(
        result=outcome.result,
        translation=translation,
        cache=outcome.cache,
        quota_used=outcome.quota_used,
        quota_limit=outcome.quota_limit,
        card=card,
        deck_name=deck_name,
        already_saved=already_saved,
    )
