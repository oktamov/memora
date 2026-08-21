"""The daily reminder (SPEC §9a).

An hourly APScheduler job inside the API process. Each run picks the users whose local
time now matches their `reminder_hour`, who have reminders enabled, **and who have due
cards**.

SPEC §13 is blunt about the last one: "Reminders to users with nothing due" is the
fastest path to getting blocked. The due-count check is therefore part of the selecting
query, not an afterthought — a user with an empty queue is never even considered.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.models.card import CardState
from app.models.user import User
from app.telegram import keyboards

logger = get_logger(__name__)

# Telegram allows roughly 30 messages/second to different users. 25 leaves headroom.
SENDS_PER_SECOND = 25
_SEND_INTERVAL = 1 / SENDS_PER_SECOND


@dataclass(frozen=True, slots=True)
class Recipient:
    user_id: UUID
    telegram_id: int
    due_count: int


def _local_hour(user_timezone: str, now: datetime) -> int | None:
    try:
        return now.astimezone(ZoneInfo(user_timezone)).hour
    except (ZoneInfoNotFoundError, ValueError):
        return None


async def select_recipients(
    session: AsyncSession, *, now: datetime | None = None
) -> list[Recipient]:
    """Users to remind this hour, in one query.

    "Has due cards" is a join condition, not a check made after the message is already
    on its way. `due <= now` is the same predicate the review queue uses, so the count
    in the message is the count the user will actually see.

    The local-hour comparison happens in Python because it depends on each user's IANA
    zone, which Postgres would need a per-row `AT TIME ZONE` to evaluate — the set of
    reminder-enabled users is small enough that filtering here is cheaper than that.
    """
    moment = now or datetime.now(UTC)

    due_cards = (
        select(
            CardState.user_id.label("user_id"),
            func.count(CardState.card_id).label("due_count"),
        )
        .where(CardState.suspended.is_(False), CardState.due <= moment)
        .group_by(CardState.user_id)
        .subquery()
    )

    statement = (
        select(User.id, User.telegram_id, User.timezone, User.reminder_hour, due_cards.c.due_count)
        .join(due_cards, due_cards.c.user_id == User.id)
        .where(
            User.is_active.is_(True),
            User.reminder_enabled.is_(True),
            User.reminder_hour.isnot(None),
            due_cards.c.due_count > 0,
        )
    )

    return [
        Recipient(user_id=row.id, telegram_id=row.telegram_id, due_count=row.due_count)
        for row in (await session.execute(statement)).all()
        if _local_hour(row.timezone, moment) == row.reminder_hour
    ]


async def deactivate(session: AsyncSession, user_id: UUID) -> None:
    """The user blocked the bot; stop writing to them (SPEC §9a)."""
    await session.execute(update(User).where(User.id == user_id).values(is_active=False))
    await session.commit()
    logger.info("user_deactivated", extra={"event": "user_deactivated", "user_id": str(user_id)})


def reminder_text(due_count: int) -> str:
    return f"Bugun takrorlash uchun <b>{due_count}</b> ta karta bor.\n" f"Besh daqiqa yetadi."


async def send_reminders(
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    now: datetime | None = None,
) -> int:
    """One hourly pass. Returns how many messages were delivered."""
    async with session_factory() as session:
        recipients = await select_recipients(session, now=now)

    if not recipients:
        return 0

    delivered = 0
    for recipient in recipients:
        try:
            await bot.send_message(
                chat_id=recipient.telegram_id,
                text=reminder_text(recipient.due_count),
                reply_markup=keyboards.open_app_button(
                    "Takrorlashni boshlash", start_param="review"
                ),
            )
            delivered += 1
        except TelegramForbiddenError:
            async with session_factory() as session:
                await deactivate(session, recipient.user_id)
        except TelegramRetryAfter as flood:
            # Telegram told us exactly how long to wait; obey it rather than guess.
            await asyncio.sleep(flood.retry_after)
        except Exception as exc:
            logger.warning(
                "reminder_send_failed",
                extra={
                    "event": "reminder_send_failed",
                    "user_id": str(recipient.user_id),
                    "error": str(exc),
                },
            )

        # Chunk at ~25/second (SPEC §9a).
        await asyncio.sleep(_SEND_INTERVAL)

    logger.info(
        "reminders_sent",
        extra={
            "event": "reminders_sent",
            "delivered": delivered,
            "considered": len(recipients),
        },
    )
    return delivered
