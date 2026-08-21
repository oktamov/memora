"""The FSRS wrapper (SPEC §9). Pure functions — no database, no clock."""

from datetime import UTC, datetime, timedelta

import pytest

from app.srs.scheduler import schedule
from app.srs.types import (
    STATE_LEARNING,
    STATE_NEW,
    STATE_RELEARNING,
    STATE_REVIEW,
    CardStateSnapshot,
    Rating,
)

NOW = datetime(2026, 5, 10, 9, 0, tzinfo=UTC)


def new_card() -> CardStateSnapshot:
    return CardStateSnapshot(due=NOW, state=STATE_NEW)


def review_card(days_since: int = 10) -> CardStateSnapshot:
    """A mature card, last seen `days_since` days ago and due now."""
    return CardStateSnapshot(
        due=NOW,
        state=STATE_REVIEW,
        stability=12.0,
        difficulty=5.0,
        elapsed_days=days_since,
        scheduled_days=days_since,
        reps=4,
        lapses=0,
        last_review=NOW - timedelta(days=days_since),
    )


def test_a_new_card_rated_good_leaves_the_new_state() -> None:
    result = schedule(new_card(), Rating.good, NOW)

    assert result.next_state.state in {STATE_LEARNING, STATE_REVIEW}
    assert result.next_state.state != STATE_NEW
    assert result.next_state.reps == 1
    assert result.next_state.stability is not None
    assert result.next_state.last_review == NOW


def test_a_card_rated_again_comes_back_within_the_session() -> None:
    """M4 acceptance: `again` must reappear in the same session."""
    result = schedule(new_card(), Rating.again, NOW)

    assert result.next_state.due - NOW < timedelta(minutes=30)
    assert result.next_state.state in {STATE_LEARNING, STATE_RELEARNING}


def test_a_mature_card_rated_again_also_comes_back_within_the_session() -> None:
    result = schedule(review_card(), Rating.again, NOW)

    assert result.next_state.due - NOW < timedelta(minutes=30)
    assert result.next_state.state == STATE_RELEARNING


def test_a_mature_card_rated_easy_schedules_days_out() -> None:
    """M4 acceptance."""
    result = schedule(review_card(), Rating.easy, NOW)

    assert result.next_state.due - NOW > timedelta(days=1)
    assert result.next_state.scheduled_days >= 1
    assert result.next_state.state == STATE_REVIEW


def test_easy_schedules_further_out_than_good() -> None:
    easy = schedule(review_card(), Rating.easy, NOW)
    good = schedule(review_card(), Rating.good, NOW)

    assert easy.next_state.due > good.next_state.due


def test_good_schedules_further_out_than_hard() -> None:
    good = schedule(review_card(), Rating.good, NOW)
    hard = schedule(review_card(), Rating.hard, NOW)

    assert good.next_state.due > hard.next_state.due


def test_a_lapse_is_counted_only_when_a_review_card_fails() -> None:
    """SPEC §5: `lapses` tracks forgetting a card that had graduated."""
    lapsed = schedule(review_card(), Rating.again, NOW)
    assert lapsed.next_state.lapses == 1

    kept = schedule(review_card(), Rating.good, NOW)
    assert kept.next_state.lapses == 0

    # A card still in learning has nothing to lapse from.
    learning = CardStateSnapshot(
        due=NOW, state=STATE_LEARNING, stability=1.0, difficulty=5.0, reps=1, last_review=NOW
    )
    assert schedule(learning, Rating.again, NOW).next_state.lapses == 0


def test_reps_increments_on_every_answer() -> None:
    first = schedule(new_card(), Rating.good, NOW)
    second = schedule(first.next_state, Rating.good, NOW + timedelta(minutes=10))

    assert (first.next_state.reps, second.next_state.reps) == (1, 2)


def test_the_log_records_the_state_before_the_review() -> None:
    """SPEC §5: this is what the optimizer needs, and it cannot be reconstructed."""
    before = review_card(days_since=10)

    result = schedule(before, Rating.hard, NOW)

    assert result.log.rating is Rating.hard
    assert result.log.state == before.state == STATE_REVIEW
    assert result.log.due == before.due
    assert result.log.stability == before.stability
    assert result.log.difficulty == before.difficulty
    assert result.log.elapsed_days == 10
    assert result.log.last_elapsed_days == before.elapsed_days
    assert result.log.scheduled_days == before.scheduled_days
    assert result.log.reviewed_at == NOW
    # ...and the state after it is different.
    assert result.next_state.stability != before.stability


def test_elapsed_days_is_zero_for_a_card_never_reviewed() -> None:
    assert schedule(new_card(), Rating.good, NOW).log.elapsed_days == 0


@pytest.mark.parametrize("rating", list(Rating))
def test_every_rating_produces_a_due_date_in_the_future(rating: Rating) -> None:
    result = schedule(review_card(), rating, NOW)

    assert result.next_state.due > NOW


def test_custom_fsrs_params_are_honoured() -> None:
    """SPEC §9: `users.fsrs_params` null means library defaults."""
    impatient = {"desired_retention": 0.97}

    default = schedule(review_card(), Rating.good, NOW)
    tuned = schedule(review_card(), Rating.good, NOW, fsrs_params=impatient)

    # Wanting to remember more means seeing the card sooner.
    assert tuned.next_state.due < default.next_state.due


def test_a_naive_datetime_is_treated_as_utc_rather_than_crashing() -> None:
    naive = CardStateSnapshot(due=datetime(2026, 5, 10, 9, 0), state=STATE_NEW)

    result = schedule(naive, Rating.good, NOW)

    assert result.next_state.due.tzinfo is not None
