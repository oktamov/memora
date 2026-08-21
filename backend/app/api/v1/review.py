"""Review endpoints (SPEC §7)."""

from uuid import UUID

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbSession
from app.schemas.card import CardResponse, CardStateResponse
from app.schemas.review import (
    AnswerBatchRequest,
    AnswerBatchResponse,
    AnswerResultResponse,
    DeckReviewCountsResponse,
    QueueItemResponse,
    QueueResponse,
    ReviewCountsOverview,
    ReviewCountsResponse,
)
from app.services import review_service

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/queue", response_model=QueueResponse)
async def read_queue(
    user: CurrentUser,
    session: DbSession,
    deck_id: UUID | None = Query(default=None),
    limit: int = Query(default=review_service.DEFAULT_QUEUE_LIMIT, ge=1, le=500),
) -> QueueResponse:
    """The full session up front: content plus current state, already ordered."""
    items = await review_service.build_queue(session, user, deck_id=deck_id, limit=limit)
    tallies = await review_service.counts(session, user, deck_id=deck_id)
    started = await review_service.count_new_started_today(session, user)

    return QueueResponse(
        items=[
            QueueItemResponse(
                card=CardResponse.model_validate(item.card),
                state=CardStateResponse.model_validate(item.state),
            )
            for item in items
        ],
        new_remaining=max(user.daily_new_limit - started, 0),
        counts=_counts(tallies),
    )


@router.post("/answer", response_model=AnswerBatchResponse)
async def submit_answers(
    payload: AnswerBatchRequest, user: CurrentUser, session: DbSession
) -> AnswerBatchResponse:
    """One transaction for the whole batch: states updated, logs written, or neither."""
    results = await review_service.answer_batch(
        session,
        user,
        [
            review_service.Answer(
                card_id=answer.card_id,
                rating=review_service.parse_rating(answer.rating),
                reviewed_at=answer.reviewed_at,
            )
            for answer in payload.answers
        ],
    )
    return AnswerBatchResponse(
        results=[
            AnswerResultResponse(
                card_id=result.card_id,
                due=result.due,
                state=result.state,
                scheduled_days=result.scheduled_days,
            )
            for result in results
        ]
    )


@router.get("/counts", response_model=ReviewCountsOverview)
async def read_counts(user: CurrentUser, session: DbSession) -> ReviewCountsOverview:
    total = await review_service.counts(session, user)
    per_deck = await review_service.counts_per_deck(session, user)

    return ReviewCountsOverview(
        total=_counts(total),
        decks=[
            DeckReviewCountsResponse(
                deck_id=deck_id,
                new=tallies.new,
                learning=tallies.learning,
                due=tallies.due,
                total=tallies.total,
            )
            for deck_id, tallies in per_deck.items()
        ],
    )


def _counts(tallies: review_service.ReviewCounts) -> ReviewCountsResponse:
    return ReviewCountsResponse(
        new=tallies.new, learning=tallies.learning, due=tallies.due, total=tallies.total
    )
