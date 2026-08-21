"""The `review_logs` table (SPEC §5).

**Append-only. Never update, never delete.** This table is the only record FSRS's
optimizer can later fit per-user parameters from, and it cannot be reconstructed after
the fact — SPEC §13 lists skipping it early as one of the failures that cannot be
walked back. Every answer writes one row, from day one.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Float, ForeignKey, Index, Integer, SmallInteger, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.db.base import Base


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid7)
    card_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("cards.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    # Everything below describes the state *before* the review.
    state: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    due: Mapped[datetime] = mapped_column(nullable=False)
    stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    difficulty: Mapped[float | None] = mapped_column(Float, nullable=True)
    elapsed_days: Mapped[int] = mapped_column(Integer, nullable=False)
    last_elapsed_days: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_days: Mapped[int] = mapped_column(Integer, nullable=False)

    reviewed_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    __table_args__ = (
        # Stats (§7) reads this range; the optimizer will read it per user too.
        Index("ix_review_logs_user_reviewed", "user_id", "reviewed_at"),
        Index("ix_review_logs_card_reviewed", "card_id", "reviewed_at"),
    )
