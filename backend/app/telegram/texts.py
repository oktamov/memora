"""Bot copy. Uzbek, sentence case, active voice (SPEC §10 copy rules)."""

from __future__ import annotations

from app.providers.base import LookupResult

GREETING = (
    "Salom! Men Memora — kitob o'qiyotganda uchragan so'zlarni saqlab, "
    "keyin yodlashga yordam beraman.\n\n"
    "Notanish so'zni shu yerga yozing — barcha ma'nolarini olasiz va "
    "kerakligini bugungi to'plamga saqlaysiz."
)

OPEN_PROMPT = "Boshlash uchun ilovani oching:"

TERM_TOO_LONG = "So'z juda uzun. Bu ilova so'z va qisqa iboralar uchun — ko'pi bilan 64 belgi."
TERM_TOO_MANY_TOKENS = "Bu ilova so'z va qisqa iboralar uchun — ko'pi bilan 4 ta so'z."
TERM_EMPTY = "So'z kiritilmadi."
TERM_NOT_FOUND = "Bu so'z topilmadi. Imlosini tekshirib ko'ring."
QUOTA_EXCEEDED = "Bugungi lug'at limiti tugadi. Ertaga yana urinib ko'ring."
RATE_LIMITED = "Biroz sekinroq. Bir daqiqadan keyin urinib ko'ring."
PROVIDER_DOWN = "Lug'at hozir javob bermayapti. Birozdan so'ng urinib ko'ring."
NOTHING_SELECTED = "Avval saqlanadigan ma'nolarni belgilang."
EXPIRED = "Bu qidiruv eskirdi. So'zni qaytadan yozing."
CANCELLED = "Bekor qilindi."
SETTINGS_SAVED = "Saqlandi."

NOTHING_DUE = (
    "Hozircha takrorlash uchun karta yo'q. Yangi so'z qo'shsangiz, shu yerda paydo bo'ladi."
)


def format_lookup(result: LookupResult, selected: set[int]) -> str:
    """The lookup reply, rebuilt on every toggle so the message can be edited in place."""
    lines = [f"<b>{_escape(result.term)}</b>"]
    if result.ipa:
        lines.append(f"<code>{_escape(result.ipa)}</code>")
    lines.append("")

    for index, meaning in enumerate(result.meanings):
        mark = "☑" if index in selected else "☐"
        pos = f" <i>{_escape(meaning.pos)}</i>" if meaning.pos else ""
        lines.append(f"{mark} <b>{index + 1}.</b>{pos} {_escape(meaning.definition)}")
        if meaning.gloss_en and meaning.gloss_en != meaning.definition:
            lines.append(f"    <i>{_escape(meaning.gloss_en)}</i>")

    lines.append("")
    lines.append(
        "Saqlanadigan ma'nolarni belgilang va <b>Saqlash</b>ni bosing."
        if not selected
        else f"{len(selected)} ta ma'no belgilandi."
    )
    return "\n".join(lines)


def format_saved(term: str, deck_name: str, count: int) -> str:
    return f"<b>{_escape(term)}</b> saqlandi — {deck_name} to'plamiga, {count} ta ma'no bilan."


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
