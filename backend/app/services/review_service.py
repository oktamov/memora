"""Review queue building and batch answering (SPEC §9, §7).

Queue ordering, straight from SPEC §9:
  1. learning and relearning cards — time-sensitive, they come back in minutes
  2. due review cards, oldest-first
  3. new cards, up to `users.daily_new_limit`

`POST /review/answer` runs as one transaction per batch: `card_states` updated and
`review_logs` inserted together, or neither.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.errors import NotFoundError, ValidationError
from app.models.card import STATE_LEARNING, STATE_NEW, STATE_RELEARNING, Card, CardState
from app.models.review import ReviewLog
from app.models.user import User
from app.srs.scheduler import schedule
from app.srs.types import CardStateSnapshot, Rating

DEFAULT_QUEUE_LIMIT = 60

# SPEC §7: the client's `reviewed_at` is clamped into this window behind `now`.
REVIEWED_AT_TOLERANCE = timedelta(minutes=10)

# How far ahead a learning card counts as "due now".
#
# SPEC §11 M4 requires a card rated `again` to reappear in the *same* session, but FSRS
# puts the first learning step a minute out, so a strict `due <= now` queue could never
# show it again. Anki solves this with the same idea (its "learn ahead limit"). The
# window applies only to learning and relearning cards — review cards are days apart and
# pulling those forward would defeat the scheduling.
LEARNING_LOOKAHEAD = timedelta(minutes=20)


@dataclass(frozen=True, slots=True)
class QueueItem:
    card: Card
    state: CardState


@dataclass(frozen=True, slots=True)
class ReviewCounts:
    new: int = 0
    learning: int = 0
    due: int = 0

    @property
    def total(self) -> int:
        return self.new + self.learning + self.due


@dataclass(frozen=True, slots=True)
class Answer:
    card_id: UUID
    rating: Rating
    reviewed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AnswerResult:
    card_id: UUID
    due: datetime
    state: int
    scheduled_days: int


async def count_new_started_today(
    session: AsyncSession, user: User, *, now: datetime | None = None
) -> int:
    """How many new cards this user has already started today (SPEC §9).

    A card counts as started when its first review log lands, so the daily new limit
    survives a page reload mid-session.
    """
    moment = now or datetime.now(UTC)
    from app.services.deck_service import local_today, user_timezone

    zone = user_timezone(user)
    start_of_day = datetime.combine(
        local_today(user, now=moment), datetime.min.time(), tzinfo=zone
    ).astimezone(UTC)

    statement = select(func.count(func.distinct(ReviewLog.card_id))).where(
        ReviewLog.user_id == user.id,
        ReviewLog.reviewed_at >= start_of_day,
        ReviewLog.state == STATE_NEW,
    )
    return int(await session.scalar(statement) or 0)


async def build_queue(
    session: AsyncSession,
    user: User,
    *,
    deck_id: UUID | None = None,
    limit: int = DEFAULT_QUEUE_LIMIT,
    now: datetime | None = None,
) -> list[QueueItem]:
    """The full session up front — card content plus current state (SPEC §7)."""
    moment = now or datetime.now(UTC)
    size = max(1, min(limit, user.daily_review_limit))

    new_budget = max(
        user.daily_new_limit - await count_new_started_today(session, user, now=moment), 0
    )

    base = (
        select(Card, CardState)
        .join(CardState, CardState.card_id == Card.id)
        .where(Card.user_id == user.id, CardState.suspended.is_(False))
    )
    if deck_id is not None:
        from app.services import deck_service

        await deck_service.get_deck(session, user, deck_id)  # 404s if not theirs
        base = base.where(Card.deck_id == deck_id)

    # Learning and relearning first: they are due in minutes, not days.
    learning = base.where(
        CardState.state.in_((STATE_LEARNING, STATE_RELEARNING)),
        CardState.due <= moment + LEARNING_LOOKAHEAD,
    ).order_by(CardState.due.asc())

    # Then due reviews, oldest-first.
    reviews = base.where(
        CardState.state.notin_((STATE_NEW, STATE_LEARNING, STATE_RELEARNING)),
        CardState.due <= moment,
    ).order_by(CardState.due.asc())

    items: list[QueueItem] = []
    seen: set[UUID] = set()

    for statement in (learning, reviews):
        if len(items) >= size:
            break
        rows = (await session.execute(statement.limit(size - len(items)))).all()
        for card, state in rows:
            if card.id not in seen:
                seen.add(card.id)
                items.append(QueueItem(card=card, state=state))

    # New cards last, capped by whatever is left of today's new-card budget.
    remaining = min(size - len(items), new_budget)
    if remaining > 0:
        new_statement = (
            base.where(CardState.state == STATE_NEW).order_by(Card.id.asc()).limit(remaining)
        )
        for card, state in (await session.execute(new_statement)).all():
            if card.id not in seen:
                seen.add(card.id)
                items.append(QueueItem(card=card, state=state))

    return items


async def counts(
    session: AsyncSession,
    user: User,
    *,
    deck_id: UUID | None = None,
    now: datetime | None = None,
) -> ReviewCounts:
    """New / learning / due tallies (SPEC §7). One query."""
    moment = now or datetime.now(UTC)

    statement = (
        select(
            func.count(case((CardState.state == STATE_NEW, 1))).label("new"),
            func.count(
                case(
                    (
                        CardState.state.in_((STATE_LEARNING, STATE_RELEARNING))
                        & (CardState.due <= moment + LEARNING_LOOKAHEAD),
                        1,
                    )
                )
            ).label("learning"),
            func.count(
                case(
                    (
                        CardState.state.notin_((STATE_NEW, STATE_LEARNING, STATE_RELEARNING))
                        & (CardState.due <= moment),
                        1,
                    )
                )
            ).label("due"),
        )
        .select_from(CardState)
        .join(Card, Card.id == CardState.card_id)
        .where(CardState.user_id == user.id, CardState.suspended.is_(False))
    )
    if deck_id is not None:
        statement = statement.where(Card.deck_id == deck_id)

    row = (await session.execute(statement)).one()
    return ReviewCounts(new=row.new, learning=row.learning, due=row.due)


async def counts_per_deck(
    session: AsyncSession, user: User, *, now: datetime | None = None
) -> dict[UUID, ReviewCounts]:
    moment = now or datetime.now(UTC)

    statement = (
        select(
            Card.deck_id,
            func.count(case((CardState.state == STATE_NEW, 1))).label("new"),
            func.count(
                case(
                    (
                        CardState.state.in_((STATE_LEARNING, STATE_RELEARNING))
                        & (CardState.due <= moment + LEARNING_LOOKAHEAD),
                        1,
                    )
                )
            ).label("learning"),
            func.count(
                case(
                    (
                        CardState.state.notin_((STATE_NEW, STATE_LEARNING, STATE_RELEARNING))
                        & (CardState.due <= moment),
                        1,
                    )
                )
            ).label("due"),
        )
        .select_from(CardState)
        .join(Card, Card.id == CardState.card_id)
        .where(CardState.user_id == user.id, CardState.suspended.is_(False))
        .group_by(Card.deck_id)
    )

    rows = (await session.execute(statement)).all()
    return {
        row.deck_id: ReviewCounts(new=row.new, learning=row.learning, due=row.due) for row in rows
    }


def clamp_reviewed_at(reviewed_at: datetime | None, now: datetime) -> datetime:
    """SPEC §7: clamp the client's timestamp to `[now - 10min, now]`.

    A client clock can be wrong by accident or on purpose; either way a review dated
    next year would poison both the schedule and the optimizer's training data.
    """
    if reviewed_at is None:
        return now
    moment = reviewed_at if reviewed_at.tzinfo is not None else reviewed_at.replace(tzinfo=UTC)
    return max(min(moment, now), now - REVIEWED_AT_TOLERANCE)


async def answer_batch(
    session: AsyncSession,
    user: User,
    answers: list[Answer],
    *,
    now: datetime | None = None,
) -> list[AnswerResult]:
    """Apply a batch of answers in one transaction (SPEC §9).

    Either every `card_states` update and every `review_logs` insert lands, or none
    does. A partially applied batch would leave the log and the schedule disagreeing.
    """
    if not answers:
        return []

    moment = now or datetime.now(UTC)
    card_ids = [answer.card_id for answer in answers]

    states = {
        state.card_id: state
        for state in await session.scalars(
            select(CardState).where(CardState.card_id.in_(card_ids), CardState.user_id == user.id)
        )
    }

    missing = [card_id for card_id in card_ids if card_id not in states]
    if missing:
        raise NotFoundError(
            "Karta topilmadi.",
            code="card_not_found",
            details={"card_ids": [str(card_id) for card_id in missing]},
        )

    results: list[AnswerResult] = []

    # Answers are applied in the order the client sent them, so a card rated twice in
    # one batch (again, then good) schedules from the right intermediate state.
    for answer in answers:
        state = states[answer.card_id]
        reviewed_at = clamp_reviewed_at(answer.reviewed_at, moment)

        outcome = schedule(
            CardStateSnapshot(
                due=state.due,
                state=state.state,
                stability=state.stability,
                difficulty=state.difficulty,
                elapsed_days=state.elapsed_days,
                scheduled_days=state.scheduled_days,
                reps=state.reps,
                lapses=state.lapses,
                last_review=state.last_review,
            ),
            answer.rating,
            reviewed_at,
            fsrs_params=user.fsrs_params,
        )

        log = outcome.log
        session.add(
            ReviewLog(
                id=uuid7(),
                card_id=answer.card_id,
                user_id=user.id,
                rating=int(log.rating),
                state=log.state,
                due=log.due,
                stability=log.stability,
                difficulty=log.difficulty,
                elapsed_days=log.elapsed_days,
                last_elapsed_days=log.last_elapsed_days,
                scheduled_days=log.scheduled_days,
                reviewed_at=log.reviewed_at,
            )
        )

        nxt = outcome.next_state
        state.due = nxt.due
        state.state = nxt.state
        state.stability = nxt.stability
        state.difficulty = nxt.difficulty
        state.elapsed_days = nxt.elapsed_days
        state.scheduled_days = nxt.scheduled_days
        state.reps = nxt.reps
        state.lapses = nxt.lapses
        state.last_review = nxt.last_review

        results.append(
            AnswerResult(
                card_id=answer.card_id,
                due=nxt.due,
                state=nxt.state,
                scheduled_days=nxt.scheduled_days,
            )
        )

    await session.commit()
    return results


def parse_rating(value: int) -> Rating:
    try:
        return Rating(value)
    except ValueError as exc:
        raise ValidationError("Baho noto'g'ri.", code="rating_invalid") from exc
