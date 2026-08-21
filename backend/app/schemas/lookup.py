"""Lookup request/response schemas (SPEC §6, §7)."""

from uuid import UUID

from pydantic import Field

from app.schemas.common import ApiModel


class LookupRequest(ApiModel):
    """SPEC §8.4 bounds are enforced again in `lookup_service.validate_term`, which is
    the path the bot uses too — this is the cheap first gate, not the only one."""

    term: str = Field(min_length=1, max_length=128)
    #: Omitted means "the pair this user last chose", kept on `users`.
    source_lang: str | None = Field(default=None, min_length=2, max_length=8)
    target_lang: str | None = Field(default=None, min_length=2, max_length=8)


class MeaningResponse(ApiModel):
    pos: str | None = None
    definition: str
    gloss_en: str | None = None
    examples: list[str] = Field(default_factory=list)


class LookupResponse(ApiModel):
    term: str
    source_lang: str
    target_lang: str
    ipa: str | None
    #: Every translation as one comma-separated line — the product's actual output.
    translation: str
    #: The same translations, structured. Kept for the developer API (SPEC §7 note).
    meanings: list[MeaningResponse]
    provider: str
    cache: str
    quota_used: int
    quota_limit: int


class TranslateResponse(LookupResponse):
    """A translation that has already been filed into today's deck."""

    card_id: UUID
    deck_id: UUID
    deck_name: str
    #: True when the word was already in today's deck, so nothing new was created.
    already_saved: bool
