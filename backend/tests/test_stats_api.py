"""Stats (SPEC §7).

Streaks and activity are measured in the *user's* local days; a UTC streak would break
for every user east of Greenwich reviewing after their own midnight.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID as Uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.models.card import STATE_NEW, STATE_REVIEW
from app.models.review import ReviewLog
from app.models.user import User
from app.services import stats_service


async def _log(
    db_session: AsyncSession,
    user: User,
    card_id: Uuid,
    *,
    reviewed_at: datetime,
    rating: int = 3,
    state: int = STATE_REVIEW,
) -> None:
    db_session.add(
        ReviewLog(
            id=uuid7(),
            card_id=card_id,
            user_id=user.id,
            rating=rating,
            state=state,
            due=reviewed_at,
            stability=5.0,
            difficulty=5.0,
            elapsed_days=1,
            last_elapsed_days=1,
            scheduled_days=1,
            reviewed_at=reviewed_at,
        )
    )
    await db_session.commit()


async def _card(client: AsyncClient, headers: dict[str, str], term: str) -> Uuid:
    created = await client.post(
        "/api/v1/cards",
        headers=headers,
        json={"term": term, "meanings": [{"definition": "ma'no"}]},
    )
    assert created.status_code == 201, created.text
    return Uuid(created.json()["id"])


async def test_a_new_user_gets_an_honest_empty_overview(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/stats/overview", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["streak_days"] == 0
    assert body["longest_streak_days"] == 0
    assert body["total_cards"] == 0
    assert body["reviews_today"] == 0
    # Null, not 0.0 — nobody has answered anything yet.
    assert body["retention_rate"] is None
    assert len(body["reviews_per_day"]) == stats_service.ACTIVITY_DAYS


async def test_totals_and_due_counts_reflect_saved_cards(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await _card(client, auth_headers, "alpha")
    await _card(client, auth_headers, "beta")

    body = (await client.get("/api/v1/stats/overview", headers=auth_headers)).json()

    assert body["total_cards"] == 2
    assert body["cards_due_today"] == 2  # new cards are due immediately


async def test_reviews_today_counts_todays_answers(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, user: User
) -> None:
    card_id = await _card(client, auth_headers, "alpha")
    await _log(db_session, user, card_id, reviewed_at=datetime.now(UTC))

    body = (await client.get("/api/v1/stats/overview", headers=auth_headers)).json()

    assert body["reviews_today"] == 1
    assert body["streak_days"] == 1


async def test_activity_covers_ninety_days_including_the_empty_ones(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, user: User
) -> None:
    """Gaps matter: closing them up would read as a longer streak than there is."""
    card_id = await _card(client, auth_headers, "alpha")
    await _log(db_session, user, card_id, reviewed_at=datetime.now(UTC) - timedelta(days=3))

    body = (await client.get("/api/v1/stats/overview", headers=auth_headers)).json()
    activity = body["reviews_per_day"]

    assert len(activity) == 90
    assert sum(entry["reviews"] for entry in activity) == 1
    assert activity[-1]["reviews"] == 0  # today is empty
    assert activity[-4]["reviews"] == 1


async def test_a_streak_counts_consecutive_local_days(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, user: User
) -> None:
    card_id = await _card(client, auth_headers, "alpha")
    now = datetime.now(UTC)
    for days_ago in (0, 1, 2):
        await _log(db_session, user, card_id, reviewed_at=now - timedelta(days=days_ago))

    body = (await client.get("/api/v1/stats/overview", headers=auth_headers)).json()

    assert body["streak_days"] == 3
    assert body["longest_streak_days"] == 3


async def test_a_gap_breaks_the_streak_but_not_the_record(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, user: User
) -> None:
    card_id = await _card(client, auth_headers, "alpha")
    now = datetime.now(UTC)
    for days_ago in (10, 11, 12, 13, 0):
        await _log(db_session, user, card_id, reviewed_at=now - timedelta(days=days_ago))

    body = (await client.get("/api/v1/stats/overview", headers=auth_headers)).json()

    assert body["streak_days"] == 1
    assert body["longest_streak_days"] == 4


def test_today_being_unreviewed_does_not_break_a_streak() -> None:
    """At 9am the streak is still yesterday's — that is what users expect."""
    from datetime import date

    today = date(2026, 5, 10)
    by_day = {today - timedelta(days=offset): 1 for offset in (1, 2, 3)}

    current, longest = stats_service._streaks(by_day, today)

    assert current == 3
    assert longest == 3


def test_a_two_day_gap_ends_the_streak() -> None:
    from datetime import date

    today = date(2026, 5, 10)
    by_day = {today - timedelta(days=offset): 1 for offset in (2, 3, 4)}

    current, longest = stats_service._streaks(by_day, today)

    assert current == 0
    assert longest == 3


async def test_the_streak_follows_the_users_timezone(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, user: User
) -> None:
    """20:00 UTC is already the next day in Tashkent — two local days, not one."""
    card_id = await _card(client, auth_headers, "alpha")
    user.timezone = "Asia/Tashkent"
    await db_session.commit()

    # 1 March 17:00 UTC → 22:00 local on the 1st.
    await _log(db_session, user, card_id, reviewed_at=datetime(2026, 3, 1, 17, 0, tzinfo=UTC))
    # 1 March 20:00 UTC → 01:00 local on the 2nd.
    await _log(db_session, user, card_id, reviewed_at=datetime(2026, 3, 1, 20, 0, tzinfo=UTC))

    overview = await stats_service.overview(
        db_session, user, now=datetime(2026, 3, 2, 6, 0, tzinfo=UTC)
    )
    active = {entry.day for entry in overview.reviews_per_day if entry.reviews}

    assert len(active) == 2
    assert overview.streak_days == 2


async def test_retention_ignores_new_and_learning_answers(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, user: User
) -> None:
    """Failing a card you are still learning is the process working, not a lapse."""
    card_id = await _card(client, auth_headers, "alpha")
    now = datetime.now(UTC)

    # Three review-state answers: two passed, one failed.
    await _log(db_session, user, card_id, reviewed_at=now, rating=3, state=STATE_REVIEW)
    await _log(db_session, user, card_id, reviewed_at=now, rating=4, state=STATE_REVIEW)
    await _log(db_session, user, card_id, reviewed_at=now, rating=1, state=STATE_REVIEW)
    # ...plus a failed new card, which must not count against retention.
    await _log(db_session, user, card_id, reviewed_at=now, rating=1, state=STATE_NEW)

    body = (await client.get("/api/v1/stats/overview", headers=auth_headers)).json()

    assert body["retention_rate"] == round(2 / 3, 4)


async def test_hard_counts_as_remembered(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, user: User
) -> None:
    card_id = await _card(client, auth_headers, "alpha")
    await _log(db_session, user, card_id, reviewed_at=datetime.now(UTC), rating=2)

    body = (await client.get("/api/v1/stats/overview", headers=auth_headers)).json()

    assert body["retention_rate"] == 1.0


async def test_stats_are_scoped_to_the_current_user(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    db_session: AsyncSession,
    user: User,
) -> None:
    card_id = await _card(client, auth_headers, "alpha")
    await _log(db_session, user, card_id, reviewed_at=datetime.now(UTC))

    body = (await client.get("/api/v1/stats/overview", headers=other_auth_headers)).json()

    assert body["total_cards"] == 0
    assert body["reviews_today"] == 0
    assert body["retention_rate"] is None


async def test_stats_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/stats/overview")).status_code == 401
