"""Auth request/response schemas (SPEC §7)."""

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import ApiModel


class TelegramAuthRequest(ApiModel):
    """The client sends only initData. A `telegram_id` in a body is never trusted."""

    init_data: str = Field(min_length=1, max_length=4096)


class TokenResponse(ApiModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(ApiModel):
    id: UUID
    telegram_id: int
    username: str | None
    first_name: str | None
    source_lang: str
    native_lang: str
    ui_lang: str
    daily_new_limit: int
    daily_review_limit: int
    lookup_quota_per_day: int
    timezone: str
    reminder_hour: int | None
    reminder_enabled: bool
    is_active: bool
    created_at: datetime


class UserUpdateRequest(ApiModel):
    """PATCH /auth/me. Every field optional; unset fields are left alone."""

    source_lang: str | None = Field(default=None, min_length=2, max_length=8)
    native_lang: str | None = Field(default=None, min_length=2, max_length=8)
    ui_lang: str | None = Field(default=None, min_length=2, max_length=8)
    daily_new_limit: int | None = Field(default=None, ge=0, le=1000)
    daily_review_limit: int | None = Field(default=None, ge=0, le=10_000)
    timezone: str | None = Field(default=None, min_length=1, max_length=48)
    reminder_hour: int | None = Field(default=None, ge=0, le=23)
    reminder_enabled: bool | None = None

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Vaqt mintaqasi noto'g'ri.") from exc
        return value
