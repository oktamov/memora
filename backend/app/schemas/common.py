"""Shared response primitives."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    """Base for every schema: ORM-friendly, no silent extra fields."""

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """The one error envelope (SPEC §7). Declared so it appears in the OpenAPI schema."""

    error: ErrorDetail


class Page(BaseModel, Generic[T]):
    """Cursor-paginated collection."""

    items: list[T]
    next_cursor: str | None = None
