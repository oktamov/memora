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
LANGS_LABEL = "Til"

#: Reply-keyboard labels arrive as ordinary text; they are commands, not words.
RESERVED_LABELS = {OPEN_APP_LABEL, REVIEW_LABEL, LANGS_LABEL}
SAVE_LABEL = "Saqlash"

# Callback data is bounded to 64 bytes by Telegram, so the payloads stay terse.
LANG_PREFIX = "l"


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
        keyboard=[[KeyboardButton(text=REVIEW_LABEL), KeyboardButton(text=LANGS_LABEL)]],
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


#: The pairs offered in the bot. Anything else is set from the Mini App, where a full
#: picker fits; a chat keyboard has room for the common cases only.
LANGUAGES = ("en", "ru", "uz", "tr", "de", "fr", "es", "ar")


def language_keyboard(field: str, current: str) -> InlineKeyboardMarkup:
    """Pick one side of the pair. `field` is `src` or `dst`."""
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []

    for code in LANGUAGES:
        mark = "· " if code == current else ""
        row.append(
            InlineKeyboardButton(
                text=f"{mark}{code.upper()}", callback_data=f"{LANG_PREFIX}:{field}:{code}"
            )
        )
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    other = "dst" if field == "src" else "src"
    rows.append(
        [
            InlineKeyboardButton(
                text="Qaysi tilga →" if field == "src" else "← Qaysi tildan",
                callback_data=f"{LANG_PREFIX}:switch:{other}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
