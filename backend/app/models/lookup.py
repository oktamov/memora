"""The `lookup_cache` table (SPEC §5).

**Global, not per-user.** This is the single most important cost control in the system:
a per-user cache would multiply the provider bill by the user count (SPEC §13). There
is deliberately no `user_id` column here.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.db.base import Base


class LookupCache(Base):
    __tablename__ = "lookup_cache"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid7)
    term: Mapped[str] = mapped_column(Text, nullable=False)
    source_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    target_lang: Mapped[str] = mapped_column(String(8), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    hit_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    __table_args__ = (
        Index("uq_lookup_cache_term_langs", "term", "source_lang", "target_lang", unique=True),
    )
