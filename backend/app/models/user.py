"""The `users` table (SPEC §5).

`telegram_id` is the identity. `username` is mutable and transferable between
accounts, so it is stored for display only and never used to look a user up (SPEC §13).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Integer, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid6 import uuid7

from app.core.config import settings
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.deck import Deck


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid7)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The pair the user is translating. `native_lang` is the target — what meanings
    # are shown in — and `source_lang` is the language being read.
    source_lang: Mapped[str] = mapped_column(
        String(8), nullable=False, default="en", server_default="en"
    )
    native_lang: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default=settings.DEFAULT_NATIVE_LANG,
        server_default=settings.DEFAULT_NATIVE_LANG,
    )
    ui_lang: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default=settings.DEFAULT_UI_LANG,
        server_default=settings.DEFAULT_UI_LANG,
    )

    daily_new_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20, server_default=text("20")
    )
    daily_review_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=200, server_default=text("200")
    )
    lookup_quota_per_day: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default=text("100")
    )

    timezone: Mapped[str] = mapped_column(
        String(48),
        nullable=False,
        default=settings.DEFAULT_TIMEZONE,
        server_default=settings.DEFAULT_TIMEZONE,
    )
    reminder_hour: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, default=20, server_default=text("20")
    )
    reminder_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    # SPEC §9: exists so review logs stay useful. The optimizer is not in v1;
    # null means py-fsrs library defaults.
    fsrs_params: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    decks: Mapped[list["Deck"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="raise"
    )
