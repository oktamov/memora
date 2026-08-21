"""SRS value types (SPEC §9).

Pure data. This module and `scheduler.py` import nothing from `app/` except
`core/config`, per the layering rule in SPEC §4.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

# `card_states.state`, per SPEC §5. py-fsrs 4.x has no `New`; see DECISIONS.md D1.
STATE_NEW = 0
STATE_LEARNING = 1
STATE_REVIEW = 2
STATE_RELEARNING = 3


class Rating(IntEnum):
    """SPEC §5: 1 again, 2 hard, 3 good, 4 easy."""

    again = 1
    hard = 2
    good = 3
    easy = 4


@dataclass(frozen=True, slots=True)
class CardStateSnapshot:
    """A card's scheduling state as it is *before* a review."""

    due: datetime
    state: int = STATE_NEW
    stability: float | None = None
    difficulty: float | None = None
    elapsed_days: int = 0
    scheduled_days: int = 0
    reps: int = 0
    lapses: int = 0
    last_review: datetime | None = None

    @property
    def is_new(self) -> bool:
        return self.state == STATE_NEW or self.stability is None


@dataclass(frozen=True, slots=True)
class ReviewLogRecord:
    """The append-only log row for one answer (SPEC §5).

    Every field describes the state *before* the review, which is exactly what FSRS's
    optimizer needs later and what cannot be reconstructed after the fact.
    """

    rating: Rating
    state: int
    due: datetime
    stability: float | None
    difficulty: float | None
    elapsed_days: int
    last_elapsed_days: int
    scheduled_days: int
    reviewed_at: datetime


@dataclass(frozen=True, slots=True)
class SchedulingResult:
    """The next state, plus the log row that records how we got there."""

    next_state: CardStateSnapshot
    log: ReviewLogRecord
