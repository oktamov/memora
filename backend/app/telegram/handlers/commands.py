"""`/start`, `/review` and `/settings` (SPEC §9a)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.core.logging import get_logger
from app.models.user import User
from app.services import auth_service, review_service
from app.telegram import keyboards, texts
from app.telegram.handlers.deps import BotContext
from app.telegram.init_data import TelegramUser

logger = get_logger(__name__)

router = Router(name="commands")


def telegram_user_from(message_from: object) -> TelegramUser:
    """Build our own user record from an aiogram `From`.

    Safe here in a way it never is on the web: a webhook body is authenticated by the
    path secret *and* the `X-Telegram-Bot-Api-Secret-Token` header before it is parsed
    (SPEC §7), so this identity comes from Telegram, not from a client (SPEC §13).
    """
    return TelegramUser(
        telegram_id=getattr(message_from, "id", 0),
        username=getattr(message_from, "username", None),
        first_name=getattr(message_from, "first_name", None),
        last_name=getattr(message_from, "last_name", None),
        language_code=getattr(message_from, "language_code", None),
        is_premium=bool(getattr(message_from, "is_premium", False)),
    )


async def resolve_user(context: BotContext, message_from: object) -> User:
    async with context.session_factory() as session:
        return await auth_service.upsert_user(session, telegram_user_from(message_from))


@router.message(CommandStart())
async def handle_start(message: Message, context: BotContext) -> None:
    if message.from_user is None:
        return

    user = await resolve_user(context, message.from_user)
    logger.info("bot_start", extra={"event": "bot_start", "user_id": str(user.id)})

    # Two messages, deliberately. A message carries exactly one reply_markup, and both
    # jobs are needed: clear any reply keyboard left over from an older version — those
    # buttons open the app with no initData and strand the user on the error screen
    # (DECISIONS.md D26) — and then offer an inline button, which authenticates.
    await message.answer(texts.GREETING, reply_markup=ReplyKeyboardRemove())
    await message.answer(texts.OPEN_PROMPT, reply_markup=keyboards.open_app_button())


@router.message(F.text == keyboards.REVIEW_LABEL)
@router.message(Command("review"))
async def handle_review(message: Message, context: BotContext) -> None:
    if message.from_user is None:
        return

    user = await resolve_user(context, message.from_user)
    async with context.session_factory() as session:
        counts = await review_service.counts(session, user)

    if counts.total == 0:
        await message.answer(texts.NOTHING_DUE)
        return

    await message.answer(
        texts.format_due_counts(counts.new, counts.learning, counts.due),
        # SPEC §10: `startapp=review` opens the review screen directly.
        reply_markup=keyboards.open_app_button("Takrorlashni boshlash", start_param="review"),
    )


@router.message(Command("settings"))
async def handle_settings(message: Message, context: BotContext) -> None:
    if message.from_user is None:
        return

    user = await resolve_user(context, message.from_user)
    await message.answer(
        texts.format_settings(user.reminder_enabled, user.reminder_hour, user.timezone),
        reply_markup=keyboards.settings_keyboard(user.reminder_enabled, user.reminder_hour),
    )


@router.callback_query(F.data.startswith("set:"))
async def handle_settings_callback(query: CallbackQuery, context: BotContext) -> None:
    """Reminder on/off and hour, edited in place like the lookup message."""
    if query.from_user is None or query.data is None:
        return

    action = query.data.removeprefix("set:")
    if action == "noop":
        await query.answer()
        return

    async with context.session_factory() as session:
        user = await auth_service.upsert_user(session, telegram_user_from(query.from_user))

        if action == "toggle":
            user.reminder_enabled = not user.reminder_enabled
        elif action.startswith("hour:"):
            delta = 1 if action.endswith("+1") else -1
            current = user.reminder_hour if user.reminder_hour is not None else 20
            user.reminder_hour = (current + delta) % 24
        await session.commit()

        enabled, hour, timezone = user.reminder_enabled, user.reminder_hour, user.timezone

    if isinstance(query.message, Message):
        await query.message.edit_text(
            texts.format_settings(enabled, hour, timezone),
            reply_markup=keyboards.settings_keyboard(enabled, hour),
        )
    await query.answer(texts.SETTINGS_SAVED)


@router.message(F.text == keyboards.LANGS_LABEL)
@router.message(Command("til"))
async def handle_languages(message: Message, context: BotContext) -> None:
    """Change the language pair without leaving the chat."""
    if message.from_user is None:
        return

    user = await resolve_user(context, message.from_user)
    await message.answer(
        texts.format_languages(user.source_lang, user.native_lang),
        reply_markup=keyboards.language_keyboard("src", user.source_lang),
    )


@router.callback_query(F.data.startswith(f"{keyboards.LANG_PREFIX}:"))
async def handle_language_choice(query: CallbackQuery, context: BotContext) -> None:
    if query.from_user is None or query.data is None:
        return

    _, field, value = query.data.split(":", 2)

    async with context.session_factory() as session:
        user = await auth_service.upsert_user(session, telegram_user_from(query.from_user))

        if field == "src":
            user.source_lang = value
        elif field == "dst":
            user.native_lang = value
        await session.commit()
        source, target = user.source_lang, user.native_lang

    # "switch" only moves the picker to the other side of the pair.
    showing = value if field == "switch" else ("dst" if field == "src" else "src")
    current = source if showing == "src" else target

    if isinstance(query.message, Message):
        await query.message.edit_text(
            texts.format_languages(source, target),
            reply_markup=keyboards.language_keyboard(showing, current),
        )
    await query.answer(texts.LANGUAGES_SAVED if field != "switch" else None)
