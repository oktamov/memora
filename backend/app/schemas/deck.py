"""Deck request/response schemas (SPEC §7)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import Field

from app.models.deck import DeckKind
from app.schemas.common import ApiModel


class DeckCreateRequest(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    source_lang: str = Field(min_length=2, max_length=8)
    target_lang: str = Field(min_length=2, max_length=8)


class DeckUpdateRequest(ApiModel):
    """Rename or archive. `archived=False` un-archives."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    archived: bool | None = None


class DeckResponse(ApiModel):
    id: UUID
    name: str
    source_lang: str
    target_lang: str
    kind: DeckKind
    daily_date: date | None
    archived_at: datetime | None
    created_at: datetime
    card_count: int = 0
    due_count: int = 0
    new_count: int = 0
