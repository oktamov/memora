"""Bot keyboards (SPEC §9a)."""

from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.core.config import settings

OPEN_APP_LABEL = "Memorani ochish"
REVIEW_LABEL = "Takrorlash"
SAVE_LABEL = "Saqlash"

# Callback data is bounded to 64 bytes by Telegram, so the payloads stay terse.
TOGGLE_PREFIX = "m"
SAVE_PREFIX = "s"
CANCEL_PREFIX = "x"


def persistent_keyboard() -> ReplyKeyboardMarkup:
    """A plain reply keyboard — no WebApp button on it.

    SPEC §9a asks for "a persistent reply keyboard with a WebAppInfo button", but a
    Mini App opened from a `KeyboardButton` receives **no initData**: Telegram reserves
    that launch type for `sendData` flows, and the SDK's own types say so —
    "Current launch init data. Can be missing in case, application was launched via
    KeyboardButton." Without initData there is no HMAC to validate (SPEC §7), so the
    app can only show "open me through Telegram" — from inside Telegram.

    The persistent entry point is therefore the BotFather menu button, and every
    message that offers to open the app uses an *inline* WebApp button, which does
    carry initData. See DECISIONS.md D26.
    """
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=REVIEW_LABEL)]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="So'zni yozing…",
    )


def open_app_button(
    label: str = OPEN_APP_LABEL, *, start_param: str | None = None
) -> InlineKeyboardMarkup:
    """An inline WebApp button, optionally deep-linking into a screen (SPEC §10)."""
    url = settings.MINI_APP_URL
    if start_param:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}startapp={start_param}"

    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))]]
    )


def lookup_keyboard(
    token: str, meaning_count: int, selected: set[int], *, can_save: bool
) -> InlineKeyboardMarkup:
    """One toggle button per meaning, then Saqlash (SPEC §9a).

    `token` identifies the pending lookup held in Redis; the message is edited in
    place on every toggle, so the keyboard is rebuilt from the current selection.
    """
    rows: list[list[InlineKeyboardButton]] = []

    for index in range(meaning_count):
        mark = "☑" if index in selected else "☐"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} {index + 1}-ma'no",
                    callback_data=f"{TOGGLE_PREFIX}:{token}:{index}",
                )
            ]
        )

    actions = [InlineKeyboardButton(text="Bekor qilish", callback_data=f"{CANCEL_PREFIX}:{token}")]
    if can_save:
        actions.insert(
            0, InlineKeyboardButton(text=SAVE_LABEL, callback_data=f"{SAVE_PREFIX}:{token}")
        )
    rows.append(actions)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_keyboard(reminder_enabled: bool, reminder_hour: int | None) -> InlineKeyboardMarkup:
    """Reminder on/off and hour adjustment (SPEC §9a)."""
    toggle_label = "Eslatma: yoqilgan ✓" if reminder_enabled else "Eslatma: o'chirilgan"
    hour_label = (
        f"Soat: {reminder_hour:02d}:00" if reminder_hour is not None else "Soat: belgilanmagan"
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_label, callback_data="set:toggle")],
            [
                InlineKeyboardButton(text="−1 soat", callback_data="set:hour:-1"),
                InlineKeyboardButton(text=hour_label, callback_data="set:noop"),
                InlineKeyboardButton(text="+1 soat", callback_data="set:hour:+1"),
            ],
        ]
    )
