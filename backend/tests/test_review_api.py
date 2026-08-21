"""M4 acceptance (SPEC §11): a card rated `again` reappears in the same session, a card
rated `easy` schedules days out, and `review_logs` has one row per answer."""

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.card import STATE_NEW, STATE_REVIEW, CardState
from app.models.review import ReviewLog
from app.models.user import User
from app.services import review_service
from app.srs.types import Rating


def card_payload(term: str) -> dict[str, Any]:
    return {
        "term": term,
        "meanings": [{"pos": "noun", "definition": f"{term} ma'nosi", "gloss_en": term}],
    }


async def save_cards(client: AsyncClient, headers: dict[str, str], *terms: str) -> list[str]:
    ids = []
    for term in terms:
        response = await client.post("/api/v1/cards", headers=headers, json=card_payload(term))
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    return ids


# --- Queue ---------------------------------------------------------------------


async def test_an_empty_queue_is_an_empty_list(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/review/queue", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["counts"]["total"] == 0


async def test_the_queue_returns_content_and_state_up_front(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """SPEC §7: the full session arrives in one request."""
    await save_cards(client, auth_headers, "run", "book")

    response = await client.get("/api/v1/review/queue", headers=auth_headers)

    body = response.json()
    assert len(body["items"]) == 2
    first = body["items"][0]
    assert first["card"]["meanings"]  # content
    assert first["state"]["state"] == STATE_NEW  # and state
    assert body["counts"]["new"] == 2


async def test_new_cards_are_capped_by_the_daily_new_limit(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """SPEC §9: new cards enter subject to `users.daily_new_limit`."""
    await client.patch("/api/v1/auth/me", headers=auth_headers, json={"daily_new_limit": 2})
    await save_cards(client, auth_headers, "one", "two", "three", "four")

    response = await client.get("/api/v1/review/queue", headers=auth_headers)

    assert len(response.json()["items"]) == 2
    assert response.json()["new_remaining"] == 2


async def test_the_queue_can_be_scoped_to_one_deck(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    deck = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Dune", "source_lang": "en", "target_lang": "uz"},
    )
    await client.post(
        "/api/v1/cards",
        headers=auth_headers,
        json={**card_payload("spice"), "deck_id": deck.json()["id"]},
    )
    await save_cards(client, auth_headers, "elsewhere")

    scoped = await client.get(
        "/api/v1/review/queue", headers=auth_headers, params={"deck_id": deck.json()["id"]}
    )

    assert [item["card"]["term"] for item in scoped.json()["items"]] == ["spice"]


async def test_a_suspended_card_never_enters_the_queue(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    [card_id] = await save_cards(client, auth_headers, "hidden")
    await client.post(
        f"/api/v1/cards/{card_id}/suspend", headers=auth_headers, json={"suspended": True}
    )

    response = await client.get("/api/v1/review/queue", headers=auth_headers)

    assert response.json()["items"] == []


async def test_learning_cards_come_before_due_reviews_and_new_ones(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession, user: User
) -> None:
    """SPEC §9: learning and relearning first — they are due in minutes."""
    ids = await save_cards(client, auth_headers, "learningcard", "reviewcard", "newcard")
    now = datetime.now(UTC)

    learning = await db_session.get(CardState, __import__("uuid").UUID(ids[0]))
    assert learning is not None
    learning.state = 1  # learning
    learning.due = now - timedelta(minutes=1)
    learning.stability, learning.difficulty, learning.reps = 0.5, 5.0, 1

    review = await db_session.get(CardState, __import__("uuid").UUID(ids[1]))
    assert review is not None
    review.state = STATE_REVIEW
    review.due = now - timedelta(days=3)
    review.stability, review.difficulty, review.reps = 10.0, 5.0, 3
    await db_session.commit()

    response = await client.get("/api/v1/review/queue", headers=auth_headers)

    assert [item["card"]["term"] for item in response.json()["items"]] == [
        "learningcard",
        "reviewcard",
        "newcard",
    ]


async def test_due_reviews_are_ordered_oldest_first(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    from uuid import UUID as Uuid

    ids = await save_cards(client, auth_headers, "recent", "ancient")
    now = datetime.now(UTC)

    for card_id, days in zip(ids, (2, 30), strict=True):
        state = await db_session.get(CardState, Uuid(card_id))
        assert state is not None
        state.state = STATE_REVIEW
        state.due = now - timedelta(days=days)
        state.stability, state.difficulty, state.reps = 9.0, 5.0, 2
    await db_session.commit()

    response = await client.get("/api/v1/review/queue", headers=auth_headers)

    assert [item["card"]["term"] for item in response.json()["items"]] == ["ancient", "recent"]


async def test_a_card_not_yet_due_stays_out_of_the_queue(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    from uuid import UUID as Uuid

    [card_id] = await save_cards(client, auth_headers, "future")
    state = await db_session.get(CardState, Uuid(card_id))
    assert state is not None
    state.state = STATE_REVIEW
    state.due = datetime.now(UTC) + timedelta(days=5)
    state.stability, state.difficulty, state.reps = 20.0, 5.0, 3
    await db_session.commit()

    response = await client.get("/api/v1/review/queue", headers=auth_headers)

    assert response.json()["items"] == []


# --- Answering -----------------------------------------------------------------


async def test_a_card_rated_again_reappears_in_the_same_session(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """M4 acceptance."""
    [card_id] = await save_cards(client, auth_headers, "again-card")

    answered = await client.post(
        "/api/v1/review/answer",
        headers=auth_headers,
        json={"answers": [{"card_id": card_id, "rating": Rating.again}]},
    )

    assert answered.status_code == 200
    result = answered.json()["results"][0]
    due = datetime.fromisoformat(result["due"])
    assert due - datetime.now(UTC) < timedelta(minutes=30)

    # ...and it is back in the queue.
    queue = await client.get("/api/v1/review/queue", headers=auth_headers)
    assert [item["card"]["id"] for item in queue.json()["items"]] == [card_id]


async def test_a_card_rated_easy_schedules_days_out(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """M4 acceptance."""
    from uuid import UUID as Uuid

    [card_id] = await save_cards(client, auth_headers, "easy-card")
    state = await db_session.get(CardState, Uuid(card_id))
    assert state is not None
    state.state = STATE_REVIEW
    state.stability, state.difficulty, state.reps = 12.0, 5.0, 4
    state.last_review = datetime.now(UTC) - timedelta(days=10)
    await db_session.commit()

    answered = await client.post(
        "/api/v1/review/answer",
        headers=auth_headers,
        json={"answers": [{"card_id": card_id, "rating": Rating.easy}]},
    )

    result = answered.json()["results"][0]
    assert result["scheduled_days"] >= 1
    assert datetime.fromisoformat(result["due"]) - datetime.now(UTC) > timedelta(days=1)

    queue = await client.get("/api/v1/review/queue", headers=auth_headers)
    assert queue.json()["items"] == []


async def test_review_logs_get_one_row_per_answer(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """M4 acceptance, and SPEC §13: this data cannot be reconstructed later."""
    ids = await save_cards(client, auth_headers, "alpha", "beta", "gamma")

    await client.post(
        "/api/v1/review/answer",
        headers=auth_headers,
        json={
            "answers": [
                {"card_id": ids[0], "rating": Rating.good},
                {"card_id": ids[1], "rating": Rating.again},
                {"card_id": ids[2], "rating": Rating.easy},
            ]
        },
    )

    logs = (await db_session.scalars(select(ReviewLog))).all()
    assert len(logs) == 3
    assert sorted(log.rating for log in logs) == [1, 3, 4]
    # Each row describes the state before the review.
    assert all(log.state == STATE_NEW for log in logs)
    assert all(log.reviewed_at is not None for log in logs)


async def test_answering_the_same_card_twice_writes_two_logs(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    [card_id] = await save_cards(client, auth_headers, "twice")

    await client.post(
        "/api/v1/review/answer",
        headers=auth_headers,
        json={
            "answers": [
                {"card_id": card_id, "rating": Rating.again},
                {"card_id": card_id, "rating": Rating.good},
            ]
        },
    )

    logs = (await db_session.scalars(select(ReviewLog))).all()
    assert len(logs) == 2
    # The second answer scheduled from the state the first one produced.
    assert [log.rating for log in sorted(logs, key=lambda row: row.id)] == [1, 3]


async def test_a_batch_updates_state_and_logs_together(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """SPEC §9: one transaction per batch."""
    from uuid import UUID as Uuid

    [card_id] = await save_cards(client, auth_headers, "atomic")

    await client.post(
        "/api/v1/review/answer",
        headers=auth_headers,
        json={"answers": [{"card_id": card_id, "rating": Rating.good}]},
    )

    state = await db_session.get(CardState, Uuid(card_id))
    assert state is not None
    await db_session.refresh(state)
    assert state.reps == 1
    assert state.state != STATE_NEW
    assert state.last_review is not None
    assert len((await db_session.scalars(select(ReviewLog))).all()) == 1


async def test_a_batch_with_an_unknown_card_writes_nothing(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    [card_id] = await save_cards(client, auth_headers, "real")

    response = await client.post(
        "/api/v1/review/answer",
        headers=auth_headers,
        json={
            "answers": [
                {"card_id": card_id, "rating": Rating.good},
                {"card_id": "00000000-0000-0000-0000-000000000000", "rating": Rating.good},
            ]
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "card_not_found"
    # The valid answer in the same batch must not have been applied.
    assert (await db_session.scalars(select(ReviewLog))).all() == []


async def test_another_users_card_cannot_be_answered(
    client: AsyncClient, auth_headers: dict[str, str], other_auth_headers: dict[str, str]
) -> None:
    [card_id] = await save_cards(client, auth_headers, "private")

    response = await client.post(
        "/api/v1/review/answer",
        headers=other_auth_headers,
        json={"answers": [{"card_id": card_id, "rating": Rating.good}]},
    )

    assert response.status_code == 404


async def test_a_rating_outside_one_to_four_is_rejected(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    [card_id] = await save_cards(client, auth_headers, "bad-rating")

    response = await client.post(
        "/api/v1/review/answer",
        headers=auth_headers,
        json={"answers": [{"card_id": card_id, "rating": 7}]},
    )

    assert response.status_code == 422


async def test_an_empty_batch_is_rejected(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/review/answer", headers=auth_headers, json={"answers": []}
    )

    assert response.status_code == 422


# --- reviewed_at clamping ------------------------------------------------------


def test_a_future_timestamp_is_clamped_to_now() -> None:
    """SPEC §7: prevents clock abuse."""
    now = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)

    clamped = review_service.clamp_reviewed_at(now + timedelta(days=365), now)

    assert clamped == now


def test_a_very_old_timestamp_is_clamped_to_ten_minutes_ago() -> None:
    now = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)

    clamped = review_service.clamp_reviewed_at(now - timedelta(days=30), now)

    assert clamped == now - timedelta(minutes=10)


def test_a_plausible_timestamp_is_kept() -> None:
    now = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
    two_minutes_ago = now - timedelta(minutes=2)

    assert review_service.clamp_reviewed_at(two_minutes_ago, now) == two_minutes_ago


def test_a_missing_timestamp_becomes_now() -> None:
    now = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)

    assert review_service.clamp_reviewed_at(None, now) == now


async def test_a_client_supplied_future_timestamp_does_not_reach_the_log(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    [card_id] = await save_cards(client, auth_headers, "clockabuse")
    far_future = (datetime.now(UTC) + timedelta(days=400)).isoformat()

    await client.post(
        "/api/v1/review/answer",
        headers=auth_headers,
        json={"answers": [{"card_id": card_id, "rating": Rating.good, "reviewed_at": far_future}]},
    )

    log = (await db_session.scalars(select(ReviewLog))).one()
    assert log.reviewed_at <= datetime.now(UTC) + timedelta(seconds=5)


# --- Counts --------------------------------------------------------------------


async def test_counts_split_new_learning_and_due(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    from uuid import UUID as Uuid

    ids = await save_cards(client, auth_headers, "newone", "learningone", "dueone")
    now = datetime.now(UTC)

    learning = await db_session.get(CardState, Uuid(ids[1]))
    assert learning is not None
    learning.state, learning.due = 1, now - timedelta(minutes=1)
    learning.stability, learning.difficulty, learning.reps = 0.5, 5.0, 1

    due = await db_session.get(CardState, Uuid(ids[2]))
    assert due is not None
    due.state, due.due = STATE_REVIEW, now - timedelta(days=1)
    due.stability, due.difficulty, due.reps = 10.0, 5.0, 3
    await db_session.commit()

    response = await client.get("/api/v1/review/counts", headers=auth_headers)

    body = response.json()
    assert body["total"] == {"new": 1, "learning": 1, "due": 1, "total": 3}
    assert len(body["decks"]) == 1
    assert body["decks"][0]["total"] == 3


async def test_counts_are_scoped_to_the_current_user(
    client: AsyncClient, auth_headers: dict[str, str], other_auth_headers: dict[str, str]
) -> None:
    await save_cards(client, auth_headers, "mine")

    response = await client.get("/api/v1/review/counts", headers=other_auth_headers)

    assert response.json()["total"]["total"] == 0


async def test_review_endpoints_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/review/queue")).status_code == 401
    assert (await client.get("/api/v1/review/counts")).status_code == 401
    assert (await client.post("/api/v1/review/answer", json={"answers": []})).status_code == 401


async def test_the_learn_ahead_window_does_not_pull_review_cards_forward(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    """The window is for learning steps only; review cards stay days apart."""
    from uuid import UUID as Uuid

    [card_id] = await save_cards(client, auth_headers, "tomorrow")
    state = await db_session.get(CardState, Uuid(card_id))
    assert state is not None
    state.state = STATE_REVIEW
    state.due = datetime.now(UTC) + timedelta(minutes=5)  # inside the learn-ahead window
    state.stability, state.difficulty, state.reps = 15.0, 5.0, 3
    await db_session.commit()

    queue = await client.get("/api/v1/review/queue", headers=auth_headers)

    assert queue.json()["items"] == []
    assert queue.json()["counts"]["due"] == 0


async def test_a_learning_card_far_out_still_waits(
    client: AsyncClient, auth_headers: dict[str, str], db_session: AsyncSession
) -> None:
    from uuid import UUID as Uuid

    [card_id] = await save_cards(client, auth_headers, "laterlearning")
    state = await db_session.get(CardState, Uuid(card_id))
    assert state is not None
    state.state = 1
    state.due = datetime.now(UTC) + timedelta(hours=2)
    state.stability, state.difficulty, state.reps = 0.6, 5.0, 1
    await db_session.commit()

    queue = await client.get("/api/v1/review/queue", headers=auth_headers)

    assert queue.json()["items"] == []
