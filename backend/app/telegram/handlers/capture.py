"""Bare-word capture — the product loop, in a chat.

"While holding a physical book, typing one word into a chat is faster than opening an
app." A plain message is a translation: same service, same §8 validation, same quota as
the Mini App.

There are no buttons to press. The word is translated and filed in one step, because
the whole point is that keeping a word costs nothing.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from app.core.config import settings
from app.core.errors import (
    NotFoundError,
    ProviderBudgetExceededError,
    ProviderUnavailableError,
    QuotaExceededError,
    RateLimitedError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.ratelimit import hit
from app.services import translate_service
from app.telegram import keyboards, texts
from app.telegram.handlers.commands import resolve_user
from app.telegram.handlers.deps import BotContext

logger = get_logger(__name__)

router = Router(name="capture")

_ERRORS = {
    "term_too_long": texts.TERM_TOO_LONG,
    "term_too_many_tokens": texts.TERM_TOO_MANY_TOKENS,
    "term_empty": texts.TERM_EMPTY,
    "term_not_found": texts.TERM_NOT_FOUND,
    "quota_exceeded": texts.QUOTA_EXCEEDED,
    "provider_budget_exceeded": texts.QUOTA_EXCEEDED,
    "rate_limited": texts.RATE_LIMITED,
    "provider_unavailable": texts.PROVIDER_DOWN,
}


@router.message(F.text & ~F.text.startswith("/"))
async def handle_bare_word(message: Message, context: BotContext) -> None:
    if message.from_user is None or not message.text:
        return

    # Reply-keyboard shortcuts post their own label back as text; those are commands.
    if message.text.strip() in keyboards.RESERVED_LABELS:
        return

    user = await resolve_user(context, message.from_user)

    try:
        # SPEC §8.3: the same per-user rate limit the API enforces.
        await hit(
            context.redis,
            f"rl:lookup:user:{user.id}",
            limit=settings.LOOKUP_RATE_PER_MINUTE,
            window_seconds=60,
        )

        async with context.session_factory() as session:
            outcome = await translate_service.translate_and_save(
                session=session,
                redis=context.redis,
                registry=context.registry,
                user=user,
                term=message.text,
                source_lang=user.source_lang,
                target_lang=user.native_lang,
            )
    except (
        ValidationError,
        NotFoundError,
        QuotaExceededError,
        RateLimitedError,
        ProviderBudgetExceededError,
        ProviderUnavailableError,
    ) as error:
        await message.answer(_ERRORS.get(error.code, texts.PROVIDER_DOWN))
        return

    await message.answer(
        texts.format_translation(
            term=outcome.card.display_term,
            translation=outcome.translation,
            ipa=outcome.card.ipa,
            deck_name=outcome.deck_name,
            already_saved=outcome.already_saved,
        ),
        parse_mode="HTML",
    )
