"""Card request/response schemas.

`meanings` and `examples` follow the SPEC §5 shapes exactly; the API validates them
rather than accepting free-form JSON, because these are what the review screen renders.
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import Field

from app.schemas.common import ApiModel


class ExampleSource(str, Enum):
    """`user` when captured from the book the reader is holding (SPEC §5)."""

    user = "user"
    provider = "provider"


class CardMeaning(ApiModel):
    pos: str | None = Field(default=None, max_length=32)
    definition: str = Field(min_length=1, max_length=1000)
    gloss_en: str | None = Field(default=None, max_length=1000)


class CardExample(ApiModel):
    text: str = Field(min_length=1, max_length=1000)
    translation: str | None = Field(default=None, max_length=1000)
    source: ExampleSource = ExampleSource.provider


class CardCreateRequest(ApiModel):
    """Omitting `deck_id` targets today's daily deck (SPEC §7)."""

    deck_id: UUID | None = None
    term: str = Field(min_length=1, max_length=128)
    ipa: str | None = Field(default=None, max_length=128)
    pos: str | None = Field(default=None, max_length=32)
    meanings: list[CardMeaning] = Field(min_length=1, max_length=12)
    examples: list[CardExample] = Field(default_factory=list, max_length=10)
    note: str | None = Field(default=None, max_length=2000)


class CardUpdateRequest(ApiModel):
    """Edit meanings and note, or move the card to another deck."""

    deck_id: UUID | None = None
    meanings: list[CardMeaning] | None = Field(default=None, min_length=1, max_length=12)
    examples: list[CardExample] | None = Field(default=None, max_length=10)
    note: str | None = Field(default=None, max_length=2000)


class CardStateResponse(ApiModel):
    due: datetime
    state: int
    reps: int
    lapses: int
    suspended: bool
    stability: float | None = None
    difficulty: float | None = None
    last_review: datetime | None = None


class CardResponse(ApiModel):
    id: UUID
    deck_id: UUID
    term: str
    display_term: str
    ipa: str | None
    pos: str | None
    meanings: list[CardMeaning]
    examples: list[CardExample]
    note: str | None
    source_lang: str
    target_lang: str
    created_at: datetime
    state: CardStateResponse | None = None


class SuspendRequest(ApiModel):
    """Omitting `suspended` toggles the current value (SPEC §7)."""

    suspended: bool | None = None
