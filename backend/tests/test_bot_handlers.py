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
from app.telegram import keyboards, texts
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

    assert len(message.sent) == 2
    assert "Memora" in message.sent[0].text

    # The first message clears any reply keyboard a previous version left behind: its
    # buttons open the app with no initData and strand the user on the error screen.
    assert message.sent[0].reply_markup.remove_keyboard is True

    # The second offers an *inline* WebApp button, which does carry initData (D26).
    button = message.sent[1].reply_markup.inline_keyboard[0][0]
    assert button.text == keyboards.OPEN_APP_LABEL
    assert button.web_app is not None

    user = await db_session.scalar(select(User).where(User.telegram_id == 555_000_111))
    assert user is not None


# --- /review --------------------------------------------------------------------


async def test_review_says_nothing_is_due_when_nothing_is(context: BotContext) -> None:
    message = FakeMessage(text="/review")

    await commands.handle_review(message, context=context)  # type: ignore[arg-type]

    assert message.sent[0].text == texts.NOTHING_DUE


async def test_review_deep_links_into_the_review_screen(context: BotContext) -> None:
    """SPEC §10: the reminder button depends on `startapp=review`."""
    await commands.handle_start(FakeMessage(text="/start"), context=context)  # type: ignore[arg-type]
    await capture.handle_bare_word(FakeMessage(text="serendipity"), context=context)  # type: ignore[arg-type]

    review = FakeMessage(text="/review")
    await commands.handle_review(review, context=context)  # type: ignore[arg-type]

    assert "1" in review.sent[0].text
    url = review.sent[0].reply_markup.inline_keyboard[0][0].web_app.url
    assert "startapp=review" in url


# --- Bare-word capture -----------------------------------------------------------


async def test_a_bare_word_is_translated_and_saved_in_one_step(
    context: BotContext, db_session: AsyncSession
) -> None:
    """The product loop: type a word, read one line, it is already kept."""
    message = FakeMessage(text="run")

    await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]

    # One reply, no buttons: there is nothing for the user to do.
    assert len(message.sent) == 1
    assert message.sent[0].reply_markup is None

    body = message.sent[0].text
    assert "run" in body
    assert "yugurmoq, chopmoq, boshqarmoq, yugurish" in body
    assert "Saqlandi" in body

    card = await db_session.scalar(select(Card).where(Card.term == "run"))
    assert card is not None


async def test_the_word_lands_in_todays_deck_for_the_users_pair(
    context: BotContext, client: AsyncClient, db_session: AsyncSession
) -> None:
    """M6 acceptance, restated: the card is immediately visible in the Mini App."""
    await capture.handle_bare_word(FakeMessage(text="serendipity"), context=context)  # type: ignore[arg-type]

    from tests.factories import make_init_data

    auth = await client.post(
        "/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id=555_000_111)}
    )
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}

    decks = await client.get("/api/v1/decks", headers=headers)
    daily = decks.json()[0]
    assert daily["kind"] == "daily"
    assert daily["source_lang"] == "en"
    assert daily["target_lang"] == "uz"
    assert "EN → UZ" in daily["name"]

    cards = await client.get(f"/api/v1/decks/{daily['id']}/cards", headers=headers)
    assert [item["term"] for item in cards.json()["items"]] == ["serendipity"]


async def test_the_same_word_twice_is_not_an_error(
    context: BotContext, db_session: AsyncSession
) -> None:
    """Asking the same question twice deserves the same answer, not a complaint."""
    await capture.handle_bare_word(FakeMessage(text="run"), context=context)  # type: ignore[arg-type]
    second = FakeMessage(text="run")
    await capture.handle_bare_word(second, context=context)  # type: ignore[arg-type]

    assert "yugurmoq" in second.sent[0].text
    assert "to'plamida bor" in second.sent[0].text

    cards = (await db_session.scalars(select(Card).where(Card.term == "run"))).all()
    assert len(cards) == 1


async def test_switching_language_files_into_a_separate_deck(
    context: BotContext, client: AsyncClient
) -> None:
    """A user who changes pair mid-day gets two decks, so review never mixes tongues."""
    await capture.handle_bare_word(FakeMessage(text="run"), context=context)  # type: ignore[arg-type]

    await commands.handle_language_choice(
        FakeCallback(data="l:src:ru", message=FakeMessage()),  # type: ignore[arg-type]
        context=context,
    )
    await capture.handle_bare_word(FakeMessage(text="voda"), context=context)  # type: ignore[arg-type]

    from tests.factories import make_init_data

    auth = await client.post(
        "/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id=555_000_111)}
    )
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}

    decks = await client.get("/api/v1/decks", headers=headers)
    pairs = {(deck["source_lang"], deck["target_lang"]) for deck in decks.json()}

    assert pairs == {("en", "uz"), ("ru", "uz")}


async def test_the_language_picker_saves_both_sides(
    context: BotContext, db_session: AsyncSession
) -> None:
    message = FakeMessage(text="Til")
    await commands.handle_languages(message, context=context)  # type: ignore[arg-type]
    assert "EN → UZ" in message.sent[0].text

    await commands.handle_language_choice(
        FakeCallback(data="l:src:de", message=message),  # type: ignore[arg-type]
        context=context,
    )
    await commands.handle_language_choice(
        FakeCallback(data="l:dst:ru", message=message),  # type: ignore[arg-type]
        context=context,
    )

    user = await db_session.scalar(select(User).where(User.telegram_id == 555_000_111))
    assert user is not None
    await db_session.refresh(user)
    assert (user.source_lang, user.native_lang) == ("de", "ru")


async def test_switch_only_moves_the_picker_without_changing_the_pair(
    context: BotContext, db_session: AsyncSession
) -> None:
    message = FakeMessage(text="Til")
    await commands.handle_languages(message, context=context)  # type: ignore[arg-type]

    await commands.handle_language_choice(
        FakeCallback(data="l:switch:dst", message=message),  # type: ignore[arg-type]
        context=context,
    )

    user = await db_session.scalar(select(User).where(User.telegram_id == 555_000_111))
    assert user is not None
    await db_session.refresh(user)
    assert (user.source_lang, user.native_lang) == ("en", "uz")


# --- §8 validation, same rules as the API ---------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("a" * 65, texts.TERM_TOO_LONG),
        ("bir ikki uch to'rt besh", texts.TERM_TOO_MANY_TOKENS),
    ],
)
async def test_abusive_input_is_refused_without_a_provider_call(
    context: BotContext, db_session: AsyncSession, text: str, expected: str
) -> None:
    """SPEC §9a: the bot applies the same §8 validation as the API."""
    message = FakeMessage(text=text)

    await capture.handle_bare_word(message, context=context)  # type: ignore[arg-type]

    assert message.sent[0].text == expected
    # Nothing reached a provider, and nothing was filed.
    assert (await db_session.scalars(select(Card))).all() == []


@pytest.mark.parametrize("label", ["Takrorlash", "Til", "Memorani ochish"])
async def test_a_keyboard_label_is_not_treated_as_a_word(context: BotContext, label: str) -> None:
    message = FakeMessage(text=label)

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


async def test_the_reply_keyboard_carries_no_web_app_button(context: BotContext) -> None:
    """The one launch type that yields no initData must not be offered at all."""
    keyboard = keyboards.persistent_keyboard()

    for row in keyboard.keyboard:
        for button in row:
            assert button.web_app is None


async def test_the_review_shortcut_is_not_treated_as_a_lookup(context: BotContext) -> None:
    """The reply keyboard posts its label back as plain text."""
    message = FakeMessage(text=keyboards.REVIEW_LABEL)

    await commands.handle_review(message, context=context)  # type: ignore[arg-type]

    assert message.sent[0].text == texts.NOTHING_DUE
