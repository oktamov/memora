"""A thin FSRS wrapper (SPEC §9).

Pure: current state + rating + timestamp in, next state and a log record out. No
database, no HTTP, no clock of its own.

Two mapping problems that `py-fsrs` 4.x creates, both settled in DECISIONS.md:

  D1 — the library has no `State.New`. A brand-new card is
       `Card(state=Learning, step=None, stability=None, difficulty=None)`. The spec's
       four-value column (0 new, 1 learning, 2 review, 3 relearning) is what the
       database and the future optimizer see, so it wins; the translation lives here.
  D2 — `reps`, `lapses`, `elapsed_days` and `scheduled_days` were dropped from the
       library's `Card`. SPEC §5 requires all four, so this module derives them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fsrs import Card as FsrsCard
from fsrs import Rating as FsrsRating
from fsrs import Scheduler
from fsrs import State as FsrsState

from app.srs.types import (
    STATE_LEARNING,
    STATE_NEW,
    STATE_RELEARNING,
    STATE_REVIEW,
    CardStateSnapshot,
    Rating,
    ReviewLogRecord,
    SchedulingResult,
)

_FROM_FSRS_STATE = {
    FsrsState.Learning: STATE_LEARNING,
    FsrsState.Review: STATE_REVIEW,
    FsrsState.Relearning: STATE_RELEARNING,
}

_TO_FSRS_STATE = {
    STATE_NEW: FsrsState.Learning,
    STATE_LEARNING: FsrsState.Learning,
    STATE_REVIEW: FsrsState.Review,
    STATE_RELEARNING: FsrsState.Relearning,
}


def build_scheduler(fsrs_params: dict[str, Any] | None = None) -> Scheduler:
    """A scheduler for one user. `None` means library defaults (SPEC §9).

    `users.fsrs_params` exists so review logs stay useful; nothing writes it in v1.
    """
    if not fsrs_params:
        return Scheduler()

    parameters = fsrs_params.get("parameters")
    desired_retention = fsrs_params.get("desired_retention")

    kwargs: dict[str, Any] = {}
    if isinstance(parameters, list) and parameters:
        kwargs["parameters"] = [float(value) for value in parameters]
    if isinstance(desired_retention, int | float):
        kwargs["desired_retention"] = float(desired_retention)

    return Scheduler(**kwargs)


def _to_fsrs_card(snapshot: CardStateSnapshot) -> FsrsCard:
    if snapshot.is_new:
        # `step=None` with null stability is how py-fsrs 4.x spells "never reviewed".
        return FsrsCard(state=FsrsState.Learning, step=None)

    return FsrsCard(
        state=_TO_FSRS_STATE.get(snapshot.state, FsrsState.Review),
        step=0 if snapshot.state in (STATE_LEARNING, STATE_RELEARNING) else None,
        stability=snapshot.stability,
        difficulty=snapshot.difficulty,
        due=_aware(snapshot.due),
        last_review=_aware(snapshot.last_review) if snapshot.last_review else None,
    )


def _aware(moment: datetime) -> datetime:
    """Postgres hands back tz-aware values; be defensive about naive ones anyway."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _days_between(start: datetime | None, end: datetime) -> int:
    if start is None:
        return 0
    return max(int((_aware(end) - _aware(start)).total_seconds() // 86_400), 0)


def schedule(
    state: CardStateSnapshot,
    rating: Rating,
    now: datetime,
    *,
    fsrs_params: dict[str, Any] | None = None,
) -> SchedulingResult:
    """Apply one answer. Returns the next state and the log row for it."""
    moment = _aware(now)
    scheduler = build_scheduler(fsrs_params)

    # Everything the log records describes the state *before* the review.
    elapsed_days = _days_between(state.last_review, moment)
    log = ReviewLogRecord(
        rating=rating,
        state=state.state,
        due=_aware(state.due),
        stability=state.stability,
        difficulty=state.difficulty,
        elapsed_days=elapsed_days,
        last_elapsed_days=state.elapsed_days,
        scheduled_days=state.scheduled_days,
        reviewed_at=moment,
    )

    updated, _ = scheduler.review_card(
        _to_fsrs_card(state), FsrsRating(int(rating)), review_datetime=moment
    )

    due = _aware(updated.due)
    was_review = state.state == STATE_REVIEW
    lapses = state.lapses + (1 if was_review and rating is Rating.again else 0)

    next_state = CardStateSnapshot(
        due=due,
        state=_FROM_FSRS_STATE.get(updated.state, STATE_REVIEW),
        stability=updated.stability,
        difficulty=updated.difficulty,
        elapsed_days=elapsed_days,
        scheduled_days=_days_between(moment, due),
        reps=state.reps + 1,
        lapses=lapses,
        last_review=moment,
    )

    return SchedulingResult(next_state=next_state, log=log)
