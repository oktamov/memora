"""The daily reminder (SPEC §9a, §13).

"Never send a reminder to a user with zero due cards. An empty reminder is the fastest
way to get blocked." That rule gets the most tests here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from aiogram.exceptions import TelegramForbiddenError
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.card import STATE_REVIEW, CardState
from app.models.user import User
from app.telegram import notify
from tests.factories import make_init_data


@dataclass
class SentReminder:
    chat_id: int
    text: str


@dataclass
class FakeBot:
    sent: list[SentReminder] = field(default_factory=list)
    raise_forbidden_for: set[int] = field(default_factory=set)

    async def send_message(self, chat_id: int, text: str, **kwargs: Any) -> None:
        if chat_id in self.raise_forbidden_for:
            raise TelegramForbiddenError(method=None, message="bot was blocked by the user")  # type: ignore[arg-type]
        self.sent.append(SentReminder(chat_id=chat_id, text=text))


async def _make_user(
    client: AsyncClient,
    db_session: AsyncSession,
    *,
    telegram_id: int,
    timezone: str = "Asia/Tashkent",
    reminder_hour: int | None = 20,
    reminder_enabled: bool = True,
    is_active: bool = True,
) -> User:
    await client.post(
        "/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id=telegram_id)}
    )
    user = await db_session.scalar(select(User).where(User.telegram_id == telegram_id))
    assert user is not None
    user.timezone = timezone
    user.reminder_hour = reminder_hour
    user.reminder_enabled = reminder_enabled
    user.is_active = is_active
    await db_session.commit()
    return user


# 15:00 UTC is 20:00 in Tashkent — the default reminder hour.
AT_LOCAL_20 = datetime(2026, 5, 10, 15, 0, tzinfo=UTC)


async def _give_due_card(
    client: AsyncClient,
    db_session: AsyncSession,
    telegram_id: int,
    *,
    due_days_ago: int = 1,
    reference: datetime = AT_LOCAL_20,
) -> None:
    """Due dates are set relative to the moment the test queries with, not to real now."""
    auth = await client.post(
        "/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id=telegram_id)}
    )
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}
    created = await client.post(
        "/api/v1/cards",
        headers=headers,
        json={"term": f"word{telegram_id}", "meanings": [{"definition": "ma'no"}]},
    )
    from uuid import UUID as Uuid

    state = await db_session.get(CardState, Uuid(created.json()["id"]))
    assert state is not None
    state.state = STATE_REVIEW
    state.due = reference - timedelta(days=due_days_ago)
    state.stability, state.difficulty, state.reps = 9.0, 5.0, 2
    await db_session.commit()


async def test_a_user_with_due_cards_at_their_local_hour_is_reminded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_user(client, db_session, telegram_id=101)
    await _give_due_card(client, db_session, 101)

    recipients = await notify.select_recipients(db_session, now=AT_LOCAL_20)

    assert [r.telegram_id for r in recipients] == [101]
    assert recipients[0].due_count == 1


async def test_a_user_with_nothing_due_is_never_reminded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SPEC §13: the fastest way to get blocked."""
    await _make_user(client, db_session, telegram_id=102)

    recipients = await notify.select_recipients(db_session, now=AT_LOCAL_20)

    assert recipients == []


async def test_a_card_not_yet_due_does_not_earn_a_reminder(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_user(client, db_session, telegram_id=103)
    await _give_due_card(client, db_session, 103, due_days_ago=-5)  # due in the future

    assert await notify.select_recipients(db_session, now=AT_LOCAL_20) == []


async def test_a_suspended_card_does_not_earn_a_reminder(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_user(client, db_session, telegram_id=104)
    await _give_due_card(client, db_session, 104)

    state = await db_session.scalar(select(CardState))
    assert state is not None
    state.suspended = True
    await db_session.commit()

    assert await notify.select_recipients(db_session, now=AT_LOCAL_20) == []


async def test_the_wrong_local_hour_is_skipped(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_user(client, db_session, telegram_id=105)
    await _give_due_card(client, db_session, 105)

    # 09:00 UTC is 14:00 in Tashkent, not 20:00.
    at_local_14 = datetime(2026, 5, 10, 9, 0, tzinfo=UTC)

    assert await notify.select_recipients(db_session, now=at_local_14) == []


async def test_the_hour_is_the_users_own_local_hour(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Two users, same reminder_hour, different zones — different UTC moments."""
    await _make_user(client, db_session, telegram_id=106, timezone="Asia/Tashkent")
    await _give_due_card(client, db_session, 106)
    await _make_user(client, db_session, telegram_id=107, timezone="Europe/London")
    await _give_due_card(
        client, db_session, 107, reference=datetime(2026, 5, 10, 19, 0, tzinfo=UTC)
    )

    tashkent_evening = await notify.select_recipients(db_session, now=AT_LOCAL_20)
    # 19:00 UTC is 20:00 BST in London.
    london_evening = await notify.select_recipients(
        db_session, now=datetime(2026, 5, 10, 19, 0, tzinfo=UTC)
    )

    assert [r.telegram_id for r in tashkent_evening] == [106]
    assert [r.telegram_id for r in london_evening] == [107]


async def test_reminders_disabled_means_no_reminder(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_user(client, db_session, telegram_id=108, reminder_enabled=False)
    await _give_due_card(client, db_session, 108)

    assert await notify.select_recipients(db_session, now=AT_LOCAL_20) == []


async def test_a_null_reminder_hour_disables_reminders(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """SPEC §5: `reminder_hour` null disables."""
    await _make_user(client, db_session, telegram_id=109, reminder_hour=None)
    await _give_due_card(client, db_session, 109)

    assert await notify.select_recipients(db_session, now=AT_LOCAL_20) == []


async def test_an_inactive_user_is_skipped(client: AsyncClient, db_session: AsyncSession) -> None:
    user = await _make_user(client, db_session, telegram_id=110)
    await _give_due_card(client, db_session, 110)

    # Deactivated *after* the card exists: authenticating reactivates a user, which is
    # deliberate — coming back means they un-blocked the bot.
    user.is_active = False
    await db_session.commit()

    assert await notify.select_recipients(db_session, now=AT_LOCAL_20) == []


async def test_send_reminders_delivers_one_message_with_the_count(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_user(client, db_session, telegram_id=111)
    await _give_due_card(client, db_session, 111)
    bot = FakeBot()

    delivered = await notify.send_reminders(
        bot,  # type: ignore[arg-type]
        async_session_factory,
        now=AT_LOCAL_20,
    )

    assert delivered == 1
    assert len(bot.sent) == 1
    assert bot.sent[0].chat_id == 111
    assert "1" in bot.sent[0].text


async def test_a_blocked_user_is_deactivated(client: AsyncClient, db_session: AsyncSession) -> None:
    """SPEC §9a: `TelegramForbiddenError` means the user blocked the bot."""
    user = await _make_user(client, db_session, telegram_id=112)
    await _give_due_card(client, db_session, 112)
    bot = FakeBot(raise_forbidden_for={112})

    delivered = await notify.send_reminders(
        bot,  # type: ignore[arg-type]
        async_session_factory,
        now=AT_LOCAL_20,
    )

    assert delivered == 0
    await db_session.refresh(user)
    assert user.is_active is False

    # ...and they are not considered again.
    assert await notify.select_recipients(db_session, now=AT_LOCAL_20) == []


async def test_send_reminders_does_nothing_when_nobody_qualifies(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_user(client, db_session, telegram_id=113)
    bot = FakeBot()

    delivered = await notify.send_reminders(
        bot,  # type: ignore[arg-type]
        async_session_factory,
        now=AT_LOCAL_20,
    )

    assert delivered == 0
    assert bot.sent == []


def test_the_send_rate_is_chunked_at_about_25_per_second() -> None:
    """SPEC §9a: respect Telegram's limits."""
    assert notify.SENDS_PER_SECOND == 25
