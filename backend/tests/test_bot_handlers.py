"""M6 acceptance (SPEC §11): sending `serendipity` to the bot returns meanings and
saves to today's daily deck, and the card is immediately visible in the Mini App."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.models.card import Card
from app.models.user import User
from app.telegram import keyboards, pending, texts
from app.telegram.handlers import capture, commands
from app.telegram.handlers.deps import BotContext

# --- Test doubles ---------------------------------------------------------------
#
# aiogram's Message/CallbackQuery need a live Bot to answer, so these stand in and
# record what the handler tried to send. The handlers themselves are the real ones.


@dataclass
class FakeFrom:
    id: int = 555_000_111
    username: str | None = "reader"
    first_name: str | None = "Aziz"
    last_name: str | None = None
    language_code: str | None = "uz"
    is_premium: bool = False


@dataclass
class SentMessage:
    text: str
    reply_markup: Any = None


@dataclass
class FakeMessage:
    text: str | None = None
    from_user: FakeFrom | None = field(default_factory=FakeFrom)
    sent: list[SentMessage] = field(default_factory=list)
    edits: list[SentMessage] = field(default_factory=list)

    async def answer(self, text: str, **kwargs: Any) -> None:
        self.sent.append(SentMessage(text=text, reply_markup=kwargs.get("reply_markup")))

    async def edit_text(self, text: str, **kwargs: Any) -> None:
        self.edits.append(SentMessage(text=text, reply_markup=kwargs.get("reply_markup")))


@dataclass
class FakeCallback:
    data: str
    message: FakeMessage
    from_user: FakeFrom | None = field(default_factory=FakeFrom)
    answers: list[dict[str, Any]] = field(default_factory=list)

    async def answer(self, text: str | None = None, **kwargs: Any) -> None:
        self.answers.append({"text": text, **kwargs})


@pytest.fixture
def context(app: FastAPI) -> BotContext:
    return BotContext(
        session_factory=async_session_factory,
        redis=app.state.redis,
        registry=app.state.provider_registry,
    )


@pytest.fixture(autouse=True)
def _patch_message_isinstance(monkeypatch: pytest.MonkeyPatch) -> None:
    """The handlers guard `isinstance(query.message, Message)` before editing.

    Our fake is not an aiogram `Message`, so the guard is widened for the test rather
    than removed from the code — the production check stays exactly as written.
    """
    monkeypatch.setattr(capture, "Message", (capture.Message, FakeMessage))
    monkeypatch.setattr(commands, "Message", (commands.Message, FakeMessage))


# --- /start ---------------------------------------------------------------------


async def test_start_upserts_the_user_and_offers_the_web_app_button(
    context: BotContext, db_session: AsyncSession
) -> None:
    message = FakeMessage(text="/start")

    await commands.handle_start(message, context=context)  # type: ignore[arg-type]

    assert len(message.sent) == 1
    assert "Memora" in message.sent[0].text
    keyboard = message.sent[0].reply_markup
    assert keyboard.keyboard[0][0].text == keyboards.OPEN_APP_LABEL
    assert keyboard.keyboard[0][0].web_app is not None

    user = await db_session.scalar(select(User).where(User.telegram_id == 555_000_111))
    assert user is not None


# --- /review --------------------------------------------------------------------


async def test_review_says_nothing_is_due_when_nothing_is(context: BotContext) -> None:
    message = FakeMessage(text="/review")

    await commands.handle_review(message, context=context)  # type: ignore[arg-type]

    assert message.sent[0].text == texts.NOTHING_DUE


async def test_review_deep_links_into_the_review_screen(
    context: BotContext, client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """SPEC §10: the reminder button depends on `startapp=review`."""
    await commands.handle_start(FakeMessage(text="/start"), context=context)  # type: ignore[arg-type]

    # Save a card for this same telegram user through the bot's own path.
    message = FakeMessage(text="serendipity")
    await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]
    token = _token_from(message.sent[0])
    await capture.handle_toggle(
        FakeCallback(data=f"{keyboards.TOGGLE_PREFIX}:{token}:0", message=message),  # type: ignore[arg-type]
        context=context,
    )
    await capture.handle_save(
        FakeCallback(data=f"{keyboards.SAVE_PREFIX}:{token}", message=message),  # type: ignore[arg-type]
        context=context,
    )

    review = FakeMessage(text="/review")
    await commands.handle_review(review, context=context)  # type: ignore[arg-type]

    assert "1" in review.sent[0].text
    url = review.sent[0].reply_markup.inline_keyboard[0][0].web_app.url
    assert "startapp=review" in url


# --- Bare-word capture ----------------------------------------------------------


def _token_from(sent: SentMessage) -> str:
    data = sent.reply_markup.inline_keyboard[0][0].callback_data
    return str(data).split(":")[1]


async def test_a_bare_word_returns_meanings_with_one_button_each(
    context: BotContext,
) -> None:
    """M6 acceptance, first half."""
    message = FakeMessage(text="serendipity")

    await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]

    assert len(message.sent) == 1
    body = message.sent[0].text
    assert "serendipity" in body
    assert "tasodifiy omad" in body

    rows = message.sent[0].reply_markup.inline_keyboard
    # One toggle per meaning, plus the action row.
    assert len(rows) == 3 + 1
    # Saqlash is hidden until something is selected.
    assert all(button.text != keyboards.SAVE_LABEL for button in rows[-1])


async def test_toggling_edits_the_message_in_place(context: BotContext) -> None:
    """SPEC §9a: edit in place rather than sending new messages."""
    message = FakeMessage(text="serendipity")
    await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]
    token = _token_from(message.sent[0])

    query = FakeCallback(data=f"{keyboards.TOGGLE_PREFIX}:{token}:1", message=message)
    await capture.handle_toggle(query, context=context)  # type: ignore[arg-type]

    # Edited, not resent.
    assert len(message.sent) == 1
    assert len(message.edits) == 1
    assert "1 ta ma'no belgilandi" in message.edits[0].text
    # Saqlash appears once something is selected.
    assert any(
        button.text == keyboards.SAVE_LABEL
        for button in message.edits[0].reply_markup.inline_keyboard[-1]
    )


async def test_toggling_twice_deselects(context: BotContext) -> None:
    message = FakeMessage(text="serendipity")
    await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]
    token = _token_from(message.sent[0])

    for _ in range(2):
        await capture.handle_toggle(
            FakeCallback(data=f"{keyboards.TOGGLE_PREFIX}:{token}:0", message=message),  # type: ignore[arg-type]
            context=context,
        )

    assert len(message.edits) == 2
    assert "belgilang" in message.edits[-1].text


async def test_saving_writes_to_todays_daily_deck_and_shows_in_the_mini_app(
    context: BotContext,
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """M6 acceptance, second half: the card is immediately visible in the Mini App."""
    message = FakeMessage(text="serendipity")
    await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]
    token = _token_from(message.sent[0])

    for index in (0, 2):
        await capture.handle_toggle(
            FakeCallback(data=f"{keyboards.TOGGLE_PREFIX}:{token}:{index}", message=message),  # type: ignore[arg-type]
            context=context,
        )

    save = FakeCallback(data=f"{keyboards.SAVE_PREFIX}:{token}", message=message)
    await capture.handle_save(save, context=context)  # type: ignore[arg-type]

    assert save.answers[-1]["text"] == "Saqlandi"
    assert "saqlandi" in message.edits[-1].text

    card = await db_session.scalar(select(Card).where(Card.term == "serendipity"))
    assert card is not None
    assert len(card.meanings) == 2

    # ...and the Mini App, authenticating as the same telegram user, sees it.
    from tests.factories import make_init_data

    auth = await client.post(
        "/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id=555_000_111)}
    )
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}

    daily = await client.get("/api/v1/decks/daily", headers=headers)
    assert daily.json()["id"] == str(card.deck_id)
    assert daily.json()["kind"] == "daily"

    cards = await client.get(f"/api/v1/decks/{daily.json()['id']}/cards", headers=headers)
    assert [item["term"] for item in cards.json()["items"]] == ["serendipity"]


async def test_saving_nothing_selected_is_refused(context: BotContext) -> None:
    message = FakeMessage(text="serendipity")
    await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]
    token = _token_from(message.sent[0])

    save = FakeCallback(data=f"{keyboards.SAVE_PREFIX}:{token}", message=message)
    await capture.handle_save(save, context=context)  # type: ignore[arg-type]

    assert save.answers[-1]["text"] == texts.NOTHING_SELECTED
    assert save.answers[-1]["show_alert"] is True


async def test_saving_the_same_word_twice_is_refused_clearly(context: BotContext) -> None:
    async def save_once() -> FakeCallback:
        message = FakeMessage(text="serendipity")
        await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]
        token = _token_from(message.sent[0])
        await capture.handle_toggle(
            FakeCallback(data=f"{keyboards.TOGGLE_PREFIX}:{token}:0", message=message),  # type: ignore[arg-type]
            context=context,
        )
        save = FakeCallback(data=f"{keyboards.SAVE_PREFIX}:{token}", message=message)
        await capture.handle_save(save, context=context)  # type: ignore[arg-type]
        return save

    await save_once()
    second = await save_once()

    assert "allaqachon bor" in str(second.answers[-1]["text"])


async def test_cancel_drops_the_pending_lookup(context: BotContext) -> None:
    message = FakeMessage(text="serendipity")
    await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]
    token = _token_from(message.sent[0])

    await capture.handle_cancel(
        FakeCallback(data=f"{keyboards.CANCEL_PREFIX}:{token}", message=message),  # type: ignore[arg-type]
        context=context,
    )

    assert message.edits[-1].text == texts.CANCELLED
    assert await pending.load(context.redis, token) is None


async def test_an_expired_token_says_so(context: BotContext) -> None:
    message = FakeMessage(text="x")

    await capture.handle_toggle(
        FakeCallback(data=f"{keyboards.TOGGLE_PREFIX}:nosuchtoken:0", message=message),  # type: ignore[arg-type]
        context=context,
    )

    assert message.edits[-1].text == texts.EXPIRED


async def test_another_users_buttons_do_nothing(context: BotContext) -> None:
    """A forwarded message must not let someone press another user's buttons."""
    message = FakeMessage(text="serendipity")
    await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]
    token = _token_from(message.sent[0])
    edits_before = len(message.edits)

    stranger = FakeCallback(
        data=f"{keyboards.TOGGLE_PREFIX}:{token}:0",
        message=message,
        from_user=FakeFrom(id=999_888_777, username="stranger"),
    )
    await capture.handle_toggle(stranger, context=context)  # type: ignore[arg-type]

    assert len(message.edits) == edits_before


# --- §8 validation, same rules as the API ---------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a" * 65, texts.TERM_TOO_LONG),
        ("bir ikki uch to'rt besh", texts.TERM_TOO_MANY_TOKENS),
    ],
)
async def test_abusive_input_is_refused_without_a_provider_call(
    context: BotContext, text: str, expected: str
) -> None:
    """SPEC §9a: the bot applies the same §8 validation as the API."""
    message = FakeMessage(text=text)

    await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]

    assert message.sent[0].text == expected
    # Nothing was staged, so nothing reached a provider.
    assert message.sent[0].reply_markup is None


async def test_the_web_app_button_label_is_not_treated_as_a_lookup(
    context: BotContext,
) -> None:
    message = FakeMessage(text=keyboards.OPEN_APP_LABEL)

    await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]

    assert message.sent == []


# --- /settings -------------------------------------------------------------------


async def test_settings_toggles_the_reminder_in_place(
    context: BotContext, db_session: AsyncSession
) -> None:
    message = FakeMessage(text="/settings")
    await commands.handle_settings(message, context=context)  # type: ignore[arg-type]
    assert "yoqilgan" in message.sent[0].text

    await commands.handle_settings_callback(
        FakeCallback(data="set:toggle", message=message),  # type: ignore[arg-type]
        context=context,
    )

    assert "o'chirilgan" in message.edits[-1].text
    user = await db_session.scalar(select(User).where(User.telegram_id == 555_000_111))
    assert user is not None
    await db_session.refresh(user)
    assert user.reminder_enabled is False


async def test_settings_shifts_the_reminder_hour(
    context: BotContext, db_session: AsyncSession
) -> None:
    message = FakeMessage(text="/settings")
    await commands.handle_settings(message, context=context)  # type: ignore[arg-type]

    await commands.handle_settings_callback(
        FakeCallback(data="set:hour:+1", message=message),  # type: ignore[arg-type]
        context=context,
    )

    user = await db_session.scalar(select(User).where(User.telegram_id == 555_000_111))
    assert user is not None
    await db_session.refresh(user)
    assert user.reminder_hour == 21
