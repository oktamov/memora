"""Lookup request/response schemas (SPEC §6, §7)."""

from pydantic import Field

from app.schemas.common import ApiModel


class LookupRequest(ApiModel):
    """SPEC §8.4 bounds are enforced again in `lookup_service.validate_term`, which is
    the path the bot uses too — this is the cheap first gate, not the only one."""

    term: str = Field(min_length=1, max_length=128)
    source_lang: str = Field(default="en", min_length=2, max_length=8)
    target_lang: str = Field(default="uz", min_length=2, max_length=8)


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
    meanings: list[MeaningResponse]
    provider: str
    cache: str
    quota_used: int
    quota_limit: int
