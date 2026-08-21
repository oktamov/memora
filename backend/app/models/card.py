"""The `cards` and `card_states` tables (SPEC §5).

These are deliberately two tables. Merging scheduling state into `cards` makes
algorithm changes and full-deck resets painful, and SPEC §13 calls it out by name.
`cards` is content; `card_states` is FSRS's business and nothing else's.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.deck import Deck

# `card_states.state`, per SPEC §5. py-fsrs 4.x has no `New`; see DECISIONS.md D1.
STATE_NEW = 0
STATE_LEARNING = 1
STATE_REVIEW = 2
STATE_RELEARNING = 3

# The partial index predicate, named in one place so queries can reuse it.
NOT_SUSPENDED = text("suspended = false")


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid7)
    deck_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("decks.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalized so user-scoped queries never have to join through decks.
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    term: Mapped[str] = mapped_column(Text, nullable=False)
    display_term: Mapped[str] = mapped_column(Text, nullable=False)
    ipa: Mapped[str | None] = mapped_column(Text, nullable=True)
    pos: Mapped[str | None] = mapped_column(String(32), nullable=True)

    meanings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    examples: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    deck: Mapped["Deck"] = relationship(back_populates="cards", lazy="raise")
    # Named `card_state`, not `state`: `CardResponse.state` would otherwise try to
    # read this lazy="raise" relationship while serialising.
    card_state: Mapped["CardState"] = relationship(
        back_populates="card", cascade="all, delete-orphan", uselist=False, lazy="raise"
    )

    __table_args__ = (
        Index("uq_cards_deck_term", "deck_id", "term", unique=True),
        Index("ix_cards_user_created", "user_id", "created_at"),
    )


class CardState(Base):
    __tablename__ = "card_states"

    card_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("cards.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    due: Mapped[datetime] = mapped_column(nullable=False, index=True)
    stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    elapsed_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    scheduled_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    reps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    lapses: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    state: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=STATE_NEW, server_default=text("0")
    )
    last_review: Mapped[datetime | None] = mapped_column(nullable=True)
    suspended: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    card: Mapped["Card"] = relationship(back_populates="card_state", lazy="raise")

    __table_args__ = (
        # The review queue's only index. Suspended cards are never due.
        Index("ix_card_states_user_due", "user_id", "due", postgresql_where=NOT_SUSPENDED),
    )
