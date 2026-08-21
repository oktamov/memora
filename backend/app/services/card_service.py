"""Card creation and CRUD (SPEC §5, §7).

A card and its `card_states` row are created together, in one transaction. There is no
moment at which a card exists without a scheduling state.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models.card import STATE_NEW, Card, CardState
from app.models.deck import Deck
from app.models.user import User
from app.services import deck_service
from app.services.lookup_service import normalize_term

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


@dataclass(frozen=True, slots=True)
class CardPage:
    items: list[Card]
    next_cursor: str | None


def _sort_examples(examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The reader's own sentence first — context from real reading is the point (SPEC §5)."""
    return sorted(examples, key=lambda example: example.get("source") != "user")


async def create_card(
    session: AsyncSession,
    user: User,
    *,
    term: str,
    meanings: list[dict[str, Any]],
    examples: list[dict[str, Any]] | None = None,
    deck_id: UUID | None = None,
    ipa: str | None = None,
    pos: str | None = None,
    note: str | None = None,
    now: datetime | None = None,
) -> Card:
    """Save a card. Without `deck_id`, today's daily deck is the target (SPEC §7)."""
    moment = now or datetime.now(UTC)

    deck = (
        await deck_service.get_deck(session, user, deck_id)
        if deck_id is not None
        else await deck_service.get_or_create_daily_deck(session, user, now=moment)
    )
    if deck.archived_at is not None:
        raise ConflictError("Arxivlangan to'plamga qo'shib bo'lmaydi.", code="deck_archived")

    # Snapshot what the error path needs. A failed flush expires the ORM objects, and
    # reading `deck.id` afterwards would attempt IO outside the async context.
    target_deck_id = deck.id
    source_lang = deck.source_lang
    target_lang = deck.target_lang

    display_term = " ".join(term.strip().split())
    normalized = normalize_term(term)
    if not normalized:
        raise ValidationError("So'z kiritilmadi.", code="term_empty")

    card = Card(
        id=uuid7(),
        deck_id=target_deck_id,
        user_id=user.id,
        term=normalized,
        display_term=display_term,
        ipa=ipa,
        pos=pos or (meanings[0].get("pos") if meanings else None),
        meanings=meanings,
        examples=_sort_examples(list(examples or [])),
        note=note,
        # Copied from the deck at creation, per SPEC §5 — a later deck rename or a
        # move must not silently retype existing cards.
        source_lang=source_lang,
        target_lang=target_lang,
    )
    session.add(card)

    # 1:1 with the card, created together. A new card is due immediately.
    session.add(
        CardState(
            card_id=card.id,
            user_id=user.id,
            due=moment,
            state=STATE_NEW,
        )
    )

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            f"“{display_term}” bu to'plamda allaqachon bor.",
            code="card_duplicate",
            details={"deck_id": str(target_deck_id), "term": normalized},
        ) from exc

    await session.refresh(card)
    return card


def _owned(user_id: UUID) -> Select[tuple[Card]]:
    return select(Card).where(Card.user_id == user_id)


async def get_card(session: AsyncSession, user: User, card_id: UUID) -> Card:
    card = await session.scalar(_owned(user.id).where(Card.id == card_id))
    if card is None:
        raise NotFoundError("Karta topilmadi.", code="card_not_found")
    return card


async def get_card_state(session: AsyncSession, card: Card) -> CardState:
    state = await session.get(CardState, card.id)
    if state is None:  # pragma: no cover — created with the card, in one transaction
        raise NotFoundError("Karta holati topilmadi.", code="card_state_not_found")
    return state


def _encode_cursor(card: Card) -> str:
    """Keyset cursor: UUIDv7 ids are time-ordered, so the id alone is a stable key."""
    return base64.urlsafe_b64encode(str(card.id).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> UUID:
    padded = cursor + "=" * (-len(cursor) % 4)
    try:
        return UUID(base64.urlsafe_b64decode(padded.encode()).decode())
    except (ValueError, binascii.Error) as exc:
        raise ValidationError("Sahifa belgisi noto'g'ri.", code="cursor_invalid") from exc


async def list_cards(
    session: AsyncSession,
    user: User,
    deck_id: UUID,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    cursor: str | None = None,
    search: str | None = None,
) -> CardPage:
    """Cursor-paginated, newest first. Offsets drift as cards are added; keysets do not."""
    await deck_service.get_deck(session, user, deck_id)  # 404s if it is not theirs

    size = max(1, min(limit, MAX_PAGE_SIZE))
    statement = _owned(user.id).where(Card.deck_id == deck_id).order_by(Card.id.desc())

    if cursor:
        statement = statement.where(Card.id < _decode_cursor(cursor))
    if search:
        needle = f"%{normalize_term(search)}%"
        statement = statement.where(Card.term.like(needle))

    rows = list((await session.scalars(statement.limit(size + 1))).all())
    has_more = len(rows) > size
    items = rows[:size]

    return CardPage(items=items, next_cursor=_encode_cursor(items[-1]) if has_more else None)


async def update_card(
    session: AsyncSession,
    user: User,
    card_id: UUID,
    *,
    deck_id: UUID | None = None,
    meanings: list[dict[str, Any]] | None = None,
    examples: list[dict[str, Any]] | None = None,
    note: str | None = None,
    note_set: bool = False,
) -> Card:
    card = await get_card(session, user, card_id)

    if deck_id is not None and deck_id != card.deck_id:
        target = await deck_service.get_deck(session, user, deck_id)
        card.deck_id = target.id

    if meanings is not None:
        card.meanings = meanings
        card.pos = meanings[0].get("pos") if meanings else card.pos
    if examples is not None:
        card.examples = _sort_examples(examples)
    if note_set:
        card.note = note

    # Same reason as in `create_card`: a failed flush expires the object, so the
    # message's ingredients are read before the write is attempted.
    display_term = card.display_term

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(
            f"“{display_term}” bu to'plamda allaqachon bor.",
            code="card_duplicate",
        ) from exc

    await session.refresh(card)
    return card


async def delete_card(session: AsyncSession, user: User, card_id: UUID) -> None:
    card = await get_card(session, user, card_id)
    await session.execute(delete(Card).where(Card.id == card.id))
    await session.commit()


async def set_suspended(
    session: AsyncSession, user: User, card_id: UUID, *, suspended: bool | None = None
) -> CardState:
    """Set `suspended`, or toggle it when the caller does not say (SPEC §7)."""
    card = await get_card(session, user, card_id)
    state = await get_card_state(session, card)

    state.suspended = (not state.suspended) if suspended is None else suspended
    await session.commit()
    await session.refresh(state)
    return state


async def deck_counts(
    session: AsyncSession, user: User, *, now: datetime | None = None
) -> dict[UUID, deck_service.DeckCounts]:
    """Card, due and new counts per deck, in one query."""
    moment = now or datetime.now(UTC)

    statement = (
        select(
            Card.deck_id,
            func.count(Card.id).label("total"),
            func.count(Card.id)
            .filter(CardState.due <= moment, CardState.suspended.is_(False))
            .label("due"),
            func.count(Card.id)
            .filter(CardState.state == STATE_NEW, CardState.suspended.is_(False))
            .label("new"),
        )
        .join(CardState, CardState.card_id == Card.id)
        .where(Card.user_id == user.id)
        .group_by(Card.deck_id)
    )

    rows = (await session.execute(statement)).all()
    return {
        row.deck_id: deck_service.DeckCounts(total=row.total, due=row.due, new=row.new)
        for row in rows
    }


async def deck_for_card(session: AsyncSession, card: Card) -> Deck | None:
    return await session.get(Deck, card.deck_id)


async def states_for(session: AsyncSession, card_ids: list[UUID]) -> dict[UUID, CardState]:
    """Scheduling states for a page of cards, in one query rather than N."""
    if not card_ids:
        return {}
    rows = await session.scalars(select(CardState).where(CardState.card_id.in_(card_ids)))
    return {state.card_id: state for state in rows}


async def find_in_deck(
    session: AsyncSession, user: User, *, deck_id: UUID, term: str
) -> Card | None:
    """The existing card for a term in a deck, if any. Used to make a repeat
    translation idempotent rather than an error."""
    card: Card | None = await session.scalar(
        _owned(user.id).where(Card.deck_id == deck_id, Card.term == normalize_term(term))
    )
    return card
