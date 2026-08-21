"""Review request/response schemas (SPEC §7)."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.card import CardResponse, CardStateResponse
from app.schemas.common import ApiModel


class QueueItemResponse(ApiModel):
    """Card content plus current state — the whole session arrives up front."""

    card: CardResponse
    state: CardStateResponse


class QueueResponse(ApiModel):
    items: list[QueueItemResponse]
    new_remaining: int
    counts: "ReviewCountsResponse"


class AnswerRequest(ApiModel):
    card_id: UUID
    rating: int = Field(ge=1, le=4, description="1 again, 2 hard, 3 good, 4 easy")
    reviewed_at: datetime | None = None


class AnswerBatchRequest(ApiModel):
    """A batch, so the client flushes every few answers instead of per card."""

    answers: list[AnswerRequest] = Field(min_length=1, max_length=200)


class AnswerResultResponse(ApiModel):
    card_id: UUID
    due: datetime
    state: int
    scheduled_days: int


class AnswerBatchResponse(ApiModel):
    results: list[AnswerResultResponse]


class ReviewCountsResponse(ApiModel):
    new: int
    learning: int
    due: int
    total: int


class DeckReviewCountsResponse(ApiModel):
    deck_id: UUID
    new: int
    learning: int
    due: int
    total: int


class ReviewCountsOverview(ApiModel):
    total: ReviewCountsResponse
    decks: list[DeckReviewCountsResponse]


QueueResponse.model_rebuild()
