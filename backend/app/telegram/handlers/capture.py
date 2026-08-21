"""Bare-word capture (SPEC §9a).

"While holding a physical book, typing one word into a chat is faster than opening an
app." A plain message is a lookup: same `lookup_service`, same §8 validation, same
quota accounting as the Mini App — there is no second code path.

Every toggle **edits the message in place** rather than sending a new one, so the chat
stays a single tidy card instead of a wall of repeats.
"""

from __future__ import annotations

from contextlib import suppress

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

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
from app.services import card_service, deck_service, lookup_service
from app.telegram import keyboards, pending, texts
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

    # The Mini App button posts its own label back as text; that is not a lookup.
    if message.text.strip() == keyboards.OPEN_APP_LABEL:
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
            outcome = await lookup_service.lookup(
                session=session,
                redis=context.redis,
                registry=context.registry,
                user=user,
                term=message.text,
                source_lang="en",
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

    entry = pending.PendingLookup(
        token=pending.new_token(), user_id=str(user.id), result=outcome.result
    )
    await pending.save(context.redis, entry)

    await message.answer(
        texts.format_lookup(entry.result, entry.selected),
        parse_mode="HTML",
        reply_markup=keyboards.lookup_keyboard(
            entry.token, len(entry.result.meanings), entry.selected, can_save=False
        ),
    )


@router.callback_query(F.data.startswith(f"{keyboards.TOGGLE_PREFIX}:"))
async def handle_toggle(query: CallbackQuery, context: BotContext) -> None:
    """Toggle one meaning and redraw the same message (SPEC §9a)."""
    entry, index = await _load_for(query, context, with_index=True)
    if entry is None:
        return

    if index in entry.selected:
        entry.selected.discard(index)
    else:
        entry.selected.add(index)
    await pending.save(context.redis, entry)

    await _redraw(query, entry)
    await query.answer()


@router.callback_query(F.data.startswith(f"{keyboards.CANCEL_PREFIX}:"))
async def handle_cancel(query: CallbackQuery, context: BotContext) -> None:
    entry, _ = await _load_for(query, context)
    if entry is None:
        return

    await pending.drop(context.redis, entry.token)
    if isinstance(query.message, Message):
        await query.message.edit_text(texts.CANCELLED)
    await query.answer()


@router.callback_query(F.data.startswith(f"{keyboards.SAVE_PREFIX}:"))
async def handle_save(query: CallbackQuery, context: BotContext) -> None:
    """Save the selected meanings into today's daily deck (SPEC §9a)."""
    entry, _ = await _load_for(query, context)
    if entry is None:
        return

    if not entry.selected:
        await query.answer(texts.NOTHING_SELECTED, show_alert=True)
        return

    if query.from_user is None:
        return
    user = await resolve_user(context, query.from_user)

    chosen = [entry.result.meanings[index] for index in sorted(entry.selected)]
    examples = [
        {"text": example, "translation": None, "source": "provider"}
        for meaning in chosen
        for example in meaning.examples[:1]
    ]

    async with context.session_factory() as session:
        try:
            card = await card_service.create_card(
                session,
                user,
                term=entry.result.term,
                ipa=entry.result.ipa,
                pos=chosen[0].pos,
                meanings=[
                    {
                        "pos": meaning.pos,
                        "definition": meaning.definition,
                        "gloss_en": meaning.gloss_en,
                    }
                    for meaning in chosen
                ],
                examples=examples,
            )
        except Exception as error:
            code = getattr(error, "code", None)
            if code == "card_duplicate":
                await query.answer("Bu so'z bugungi to'plamda allaqachon bor.", show_alert=True)
                return
            raise

        deck = await deck_service.get_deck(session, user, card.deck_id)
        deck_name = deck.name
        term = card.display_term
        count = len(chosen)

    await pending.drop(context.redis, entry.token)
    if isinstance(query.message, Message):
        await query.message.edit_text(
            texts.format_saved(term, deck_name, count),
            parse_mode="HTML",
            reply_markup=keyboards.open_app_button(),
        )
    await query.answer("Saqlandi")


async def _load_for(
    query: CallbackQuery, context: BotContext, *, with_index: bool = False
) -> tuple[pending.PendingLookup | None, int]:
    """Resolve the callback's pending lookup, refusing another user's token."""
    if query.data is None or query.from_user is None:
        return None, -1

    parts = query.data.split(":")
    token = parts[1] if len(parts) > 1 else ""
    index = -1
    if with_index:
        try:
            index = int(parts[2])
        except (IndexError, ValueError):
            await query.answer()
            return None, -1

    entry = await pending.load(context.redis, token)
    if entry is None:
        if isinstance(query.message, Message):
            await query.message.edit_text(texts.EXPIRED)
        await query.answer()
        return None, -1

    user = await resolve_user(context, query.from_user)
    if entry.user_id != str(user.id):
        # A forwarded message would otherwise let someone press another user's buttons.
        await query.answer()
        return None, -1

    if with_index and not 0 <= index < len(entry.result.meanings):
        await query.answer()
        return None, -1

    return entry, index


async def _redraw(query: CallbackQuery, entry: pending.PendingLookup) -> None:
    if not isinstance(query.message, Message):
        return

    # "message is not modified" comes back on a double tap of the same button, which is
    # nothing to report.
    with suppress(TelegramBadRequest):
        await query.message.edit_text(
            texts.format_lookup(entry.result, entry.selected),
            parse_mode="HTML",
            reply_markup=keyboards.lookup_keyboard(
                entry.token,
                len(entry.result.meanings),
                entry.selected,
                can_save=bool(entry.selected),
            ),
        )
