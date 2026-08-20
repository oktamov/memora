"""Authentication and user upsert (SPEC §7).

No FastAPI imports — this layer is callable from the bot as well as from the API.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.config import settings
from app.core.logging import get_logger
from app.models.user import User
from app.telegram.init_data import TelegramUser, validate_init_data

logger = get_logger(__name__)

# Language codes we can serve meanings in. Anything else falls back to the default.
_SUPPORTED_NATIVE_LANGS = {"uz", "ru", "en", "kk", "ky", "tg", "tr"}


def native_lang_from_telegram(language_code: str | None) -> str:
    """SPEC §5: default from `language_code`, fallback `uz`."""
    if not language_code:
        return settings.DEFAULT_NATIVE_LANG
    base = language_code.split("-")[0].lower()
    return base if base in _SUPPORTED_NATIVE_LANGS else settings.DEFAULT_NATIVE_LANG


async def upsert_user(session: AsyncSession, tg_user: TelegramUser) -> User:
    """Insert or refresh a user, keyed on `telegram_id`.

    `username` is display-only and gets overwritten every time; it is mutable and
    transferable, so it is never the key (SPEC §13).
    """
    statement = (
        pg_insert(User)
        .values(
            id=uuid7(),
            telegram_id=tg_user.telegram_id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            native_lang=native_lang_from_telegram(tg_user.language_code),
            ui_lang=settings.DEFAULT_UI_LANG,
            timezone=settings.DEFAULT_TIMEZONE,
        )
        .on_conflict_do_update(
            index_elements=[User.telegram_id],
            set_={
                "username": tg_user.username,
                "first_name": tg_user.first_name,
                # A user who comes back has un-blocked the bot.
                "is_active": True,
            },
        )
        .returning(User)
    )

    user = (await session.execute(statement)).scalar_one()
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate_init_data(session: AsyncSession, init_data: str) -> tuple[User, str | None]:
    """Validate initData, then upsert. Returns `(user, start_param)`.

    The order matters: nothing touches the database until the HMAC has passed.
    """
    validated = validate_init_data(
        init_data,
        settings.TELEGRAM_BOT_TOKEN,
        max_age_seconds=settings.INIT_DATA_MAX_AGE_SECONDS,
    )
    user = await upsert_user(session, validated.user)
    logger.info(
        "auth_success",
        extra={"event": "auth_success", "user_id": str(user.id)},
    )
    return user, validated.start_param


async def get_user_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    result: User | None = await session.scalar(select(User).where(User.telegram_id == telegram_id))
    return result
