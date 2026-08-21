"""Bot copy. Uzbek, sentence case, active voice (SPEC §10 copy rules)."""

from __future__ import annotations

GREETING = (
    "Salom! Men Memora — so'zlarni tarjima qilib, o'zim saqlab boraman.\n\n"
    "Notanish so'zni shu yerga yozing. Tarjimalarini olasiz va so'z bugungi "
    "lug'atingizga o'zi tushadi — boshqa hech narsa qilishingiz shart emas.\n\n"
    "Tilni almashtirish uchun <b>Til</b> tugmasini bosing."
)

OPEN_PROMPT = "Boshlash uchun ilovani oching:"

TERM_TOO_LONG = "So'z juda uzun. Bu ilova so'z va qisqa iboralar uchun — ko'pi bilan 64 belgi."
TERM_TOO_MANY_TOKENS = "Bu ilova so'z va qisqa iboralar uchun — ko'pi bilan 4 ta so'z."
TERM_EMPTY = "So'z kiritilmadi."
TERM_NOT_FOUND = "Bu so'z topilmadi. Imlosini tekshirib ko'ring."
LANGUAGES_SAVED = "Til o'zgartirildi."
QUOTA_EXCEEDED = "Bugungi lug'at limiti tugadi. Ertaga yana urinib ko'ring."
RATE_LIMITED = "Biroz sekinroq. Bir daqiqadan keyin urinib ko'ring."
PROVIDER_DOWN = "Lug'at hozir javob bermayapti. Birozdan so'ng urinib ko'ring."
SETTINGS_SAVED = "Saqlandi."

NOTHING_DUE = (
    "Hozircha takrorlash uchun karta yo'q. Yangi so'z qo'shsangiz, shu yerda paydo bo'ladi."
)


def format_translation(
    *, term: str, translation: str, ipa: str | None, deck_name: str, already_saved: bool
) -> str:
    """The whole reply: the word, its translations on one line, and where it went."""
    lines = [f"<b>{_escape(term)}</b>"]
    if ipa:
        lines.append(f"<code>{_escape(ipa)}</code>")
    lines.append("")
    lines.append(_escape(translation))
    lines.append("")
    lines.append(
        f"<i>{_escape(deck_name)} to'plamida bor</i>"
        if already_saved
        else f"<i>Saqlandi → {_escape(deck_name)}</i>"
    )
    return "\n".join(lines)


def format_languages(source_lang: str, target_lang: str) -> str:
    return (
        f"Hozir <b>{source_lang.upper()} → {target_lang.upper()}</b>.\n"
        f"O'zgartirish uchun tilni tanlang:"
    )


def format_due_counts(new: int, learning: int, due: int) -> str:
    total = new + learning + due
    if total == 0:
        return NOTHING_DUE
    return (
        f"Takrorlash uchun <b>{total}</b> ta karta bor.\n"
        f"Yangi: {new} · O'rganilayotgan: {learning} · Takror: {due}"
    )


def format_settings(reminder_enabled: bool, reminder_hour: int | None, timezone: str) -> str:
    state = "yoqilgan" if reminder_enabled else "o'chirilgan"
    when = f"{reminder_hour:02d}:00" if reminder_hour is not None else "belgilanmagan"
    return (
        f"<b>Sozlamalar</b>\n\n"
        f"Kunlik eslatma: {state}\n"
        f"Vaqti: {when} ({_escape(timezone)})\n\n"
        f"Qolgan sozlamalarni ilovadan o'zgartirasiz."
    )


def _escape(value: str) -> str:
    """Telegram HTML parse mode needs these three escaped, and only these three."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
