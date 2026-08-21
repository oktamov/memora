"""The `decks` table (SPEC §5).

Two kinds. A `daily` deck is created lazily on the first save of a calendar day and is
unique per user per day — enforced in the database by a partial unique index, not by
application logic.
"""

import enum
from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.card import Card
    from app.models.user import User


# The predicate of the partial unique index. `ON CONFLICT` has to name the *same*
# expression to match the index, so it lives in one place.
DAILY_DECK_PREDICATE = text("kind = 'daily'")


class DeckKind(str, enum.Enum):
    normal = "normal"
    daily = "daily"


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    source_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    kind: Mapped[DeckKind] = mapped_column(
        Enum(DeckKind, name="deck_kind", native_enum=True),
        nullable=False,
        default=DeckKind.normal,
        server_default=DeckKind.normal.value,
    )
    daily_date: Mapped[date | None] = mapped_column(nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="decks", lazy="raise")
    cards: Mapped[list["Card"]] = relationship(
        back_populates="deck", cascade="all, delete-orphan", lazy="raise"
    )

    __table_args__ = (
        # One daily deck per user per calendar day. The partial index is what makes
        # concurrent first-saves of the day safe (SPEC §5).
        Index(
            "uq_decks_user_daily_date",
            "user_id",
            "daily_date",
            unique=True,
            postgresql_where=DAILY_DECK_PREDICATE,
        ),
        Index("ix_decks_user_archived", "user_id", "archived_at"),
    )
