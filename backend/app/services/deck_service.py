"""Deck CRUD and lazy daily-deck creation (SPEC §1, §5, §7).

A daily deck is created on the first save of a calendar day, in the *user's* local
timezone — the whole point of the deck is that it matches the day the user was
reading, not a UTC day boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Select, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.errors import ConflictError, NotFoundError
from app.models.deck import DAILY_DECK_PREDICATE, Deck, DeckKind
from app.models.user import User

# Uzbek month names, so a daily deck reads like a diary entry rather than an ISO date.
_UZ_MONTHS = (
    "yanvar",
    "fevral",
    "mart",
    "aprel",
    "may",
    "iyun",
    "iyul",
    "avgust",
    "sentabr",
    "oktabr",
    "noyabr",
    "dekabr",
)


def user_timezone(user: User) -> ZoneInfo:
    """The user's IANA zone, falling back to UTC if the stored value went bad."""
    try:
        return ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local_today(user: User, *, now: datetime | None = None) -> date:
    """Today's calendar date in the user's own timezone."""
    moment = now or datetime.now(UTC)
    return moment.astimezone(user_timezone(user)).date()


def daily_deck_name(day: date, source_lang: str, target_lang: str) -> str:
    """Reads like a diary entry, and names the pair so two same-day decks are telling
    apart at a glance."""
    return f"{day.day}-{_UZ_MONTHS[day.month - 1]} · {source_lang.upper()} → {target_lang.upper()}"


def _visible(user_id: UUID) -> Select[tuple[Deck]]:
    return select(Deck).where(Deck.user_id == user_id)


async def list_decks(
    session: AsyncSession, user: User, *, include_archived: bool = False
) -> list[Deck]:
    """Decks newest-first, with today's daily deck pinned to the top (SPEC §10)."""
    statement = _visible(user.id)
    if not include_archived:
        statement = statement.where(Deck.archived_at.is_(None))

    decks = list((await session.scalars(statement.order_by(Deck.created_at.desc()))).all())

    today = local_today(user)
    decks.sort(key=lambda deck: not (deck.kind is DeckKind.daily and deck.daily_date == today))
    return decks


async def get_deck(session: AsyncSession, user: User, deck_id: UUID) -> Deck:
    deck = await session.scalar(_visible(user.id).where(Deck.id == deck_id))
    if deck is None:
        raise NotFoundError("To'plam topilmadi.", code="deck_not_found")
    return deck


async def create_deck(
    session: AsyncSession, user: User, *, name: str, source_lang: str, target_lang: str
) -> Deck:
    deck = Deck(
        id=uuid7(),
        user_id=user.id,
        name=name.strip(),
        source_lang=source_lang,
        target_lang=target_lang,
        kind=DeckKind.normal,
    )
    session.add(deck)
    await session.commit()
    await session.refresh(deck)
    return deck


async def update_deck(
    session: AsyncSession,
    user: User,
    deck_id: UUID,
    *,
    name: str | None = None,
    archived: bool | None = None,
) -> Deck:
    deck = await get_deck(session, user, deck_id)

    if name is not None:
        if deck.kind is DeckKind.daily:
            raise ConflictError(
                "Kunlik to'plam nomini o'zgartirib bo'lmaydi.", code="daily_deck_immutable"
            )
        deck.name = name.strip()

    if archived is not None:
        deck.archived_at = datetime.now(UTC) if archived else None

    await session.commit()
    await session.refresh(deck)
    return deck


async def delete_deck(session: AsyncSession, user: User, deck_id: UUID) -> None:
    deck = await get_deck(session, user, deck_id)
    await session.execute(delete(Deck).where(Deck.id == deck.id))
    await session.commit()


async def get_or_create_daily_deck(
    session: AsyncSession,
    user: User,
    *,
    source_lang: str | None = None,
    target_lang: str | None = None,
    now: datetime | None = None,
) -> Deck:
    """Today's daily deck for a language pair, created on the day's first save.

    Two concurrent first-saves (the Mini App and the bot, say) would both find nothing
    and both insert. The partial unique index makes one of them lose; `ON CONFLICT DO
    NOTHING` plus a re-select turns that loss into the same correct answer instead of
    a 500.
    """
    today = local_today(user, now=now)
    source = source_lang or user.source_lang
    target = target_lang or user.native_lang

    def _find() -> Select[tuple[Deck]]:
        return _visible(user.id).where(
            Deck.kind == DeckKind.daily,
            Deck.daily_date == today,
            Deck.source_lang == source,
            Deck.target_lang == target,
        )

    existing = await session.scalar(_find())
    if existing is not None:
        return existing

    statement = (
        pg_insert(Deck)
        .values(
            id=uuid7(),
            user_id=user.id,
            name=daily_deck_name(today, source, target),
            source_lang=source,
            target_lang=target,
            kind=DeckKind.daily,
            daily_date=today,
        )
        .on_conflict_do_nothing(
            index_elements=["user_id", "daily_date", "source_lang", "target_lang"],
            index_where=DAILY_DECK_PREDICATE,
        )
        .returning(Deck)
    )

    try:
        created = (await session.execute(statement)).scalar_one_or_none()
        await session.commit()
    except IntegrityError:
        await session.rollback()
        created = None

    if created is not None:
        await session.refresh(created)
        return created

    # We lost the race; the winner's row is the answer.
    deck = await session.scalar(_find())
    if deck is None:  # pragma: no cover — only reachable if the row vanished mid-flight
        raise ConflictError("Kunlik to'plam yaratilmadi.", code="daily_deck_unavailable")
    return deck


@dataclass(frozen=True, slots=True)
class DeckCounts:
    """Per-deck tallies shown on the decks list (SPEC §7)."""

    total: int = 0
    due: int = 0
    new: int = 0
