"""Deck endpoints (SPEC §7) plus the lazy daily-deck rule (SPEC §1, §5)."""

import asyncio
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services import deck_service


async def test_a_new_user_starts_with_no_decks(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/decks", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == []


async def test_create_and_read_a_deck(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Dune", "source_lang": "en", "target_lang": "uz"},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["name"] == "Dune"
    assert body["kind"] == "normal"
    assert body["daily_date"] is None
    assert body["card_count"] == 0
    assert body["due_count"] == 0

    read = await client.get(f"/api/v1/decks/{body['id']}", headers=auth_headers)
    assert read.status_code == 200
    assert read.json()["name"] == "Dune"


async def test_daily_deck_is_created_lazily_and_reused(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    first = await client.get("/api/v1/decks/daily", headers=auth_headers)
    second = await client.get("/api/v1/decks/daily", headers=auth_headers)

    assert first.status_code == 200
    assert first.json()["kind"] == "daily"
    assert first.json()["daily_date"] is not None
    # Same calendar day, same deck — never a second one.
    assert first.json()["id"] == second.json()["id"]


async def test_daily_deck_is_pinned_to_the_top_of_the_list(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Business English", "source_lang": "en", "target_lang": "uz"},
    )
    await client.get("/api/v1/decks/daily", headers=auth_headers)

    listed = await client.get("/api/v1/decks", headers=auth_headers)

    assert [deck["kind"] for deck in listed.json()] == ["daily", "normal"]


async def test_concurrent_first_saves_of_the_day_produce_one_daily_deck(
    db_session: AsyncSession, user: User
) -> None:
    """The partial unique index is what makes this safe, not application logic."""
    from app.db.session import async_session_factory

    async def create_one() -> str:
        async with async_session_factory() as session:
            fresh = await session.get(User, user.id)
            assert fresh is not None
            deck = await deck_service.get_or_create_daily_deck(session, fresh)
            return str(deck.id)

    ids = await asyncio.gather(*(create_one() for _ in range(5)))

    assert len(set(ids)) == 1


async def test_daily_deck_follows_the_users_timezone_not_utc(
    db_session: AsyncSession, user: User
) -> None:
    """22:00 in Tashkent on the 1st is 17:00 UTC on the same day; at 20:00 UTC it is
    already the 2nd locally, and that must be a different deck."""
    user.timezone = "Asia/Tashkent"

    late_evening = datetime(2026, 3, 1, 17, 0, tzinfo=UTC)
    after_local_midnight = datetime(2026, 3, 1, 20, 0, tzinfo=UTC)

    first = await deck_service.get_or_create_daily_deck(db_session, user, now=late_evening)
    second = await deck_service.get_or_create_daily_deck(db_session, user, now=after_local_midnight)

    assert first.id != second.id
    assert str(first.daily_date) == "2026-03-01"
    assert str(second.daily_date) == "2026-03-02"


async def test_rename_a_deck(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Dune", "source_lang": "en", "target_lang": "uz"},
    )

    renamed = await client.patch(
        f"/api/v1/decks/{created.json()['id']}", headers=auth_headers, json={"name": "Dune II"}
    )

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Dune II"


async def test_a_daily_deck_cannot_be_renamed(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    daily = await client.get("/api/v1/decks/daily", headers=auth_headers)

    response = await client.patch(
        f"/api/v1/decks/{daily.json()['id']}", headers=auth_headers, json={"name": "Nope"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "daily_deck_immutable"


async def test_archive_hides_a_deck_from_the_default_list(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Dune", "source_lang": "en", "target_lang": "uz"},
    )
    deck_id = created.json()["id"]

    archived = await client.patch(
        f"/api/v1/decks/{deck_id}", headers=auth_headers, json={"archived": True}
    )
    assert archived.json()["archived_at"] is not None

    default_list = await client.get("/api/v1/decks", headers=auth_headers)
    assert default_list.json() == []

    with_archived = await client.get(
        "/api/v1/decks", headers=auth_headers, params={"include_archived": True}
    )
    assert len(with_archived.json()) == 1

    restored = await client.patch(
        f"/api/v1/decks/{deck_id}", headers=auth_headers, json={"archived": False}
    )
    assert restored.json()["archived_at"] is None


async def test_delete_a_deck(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    created = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Dune", "source_lang": "en", "target_lang": "uz"},
    )
    deck_id = created.json()["id"]

    deleted = await client.delete(f"/api/v1/decks/{deck_id}", headers=auth_headers)
    assert deleted.status_code == 204

    gone = await client.get(f"/api/v1/decks/{deck_id}", headers=auth_headers)
    assert gone.status_code == 404
    assert gone.json()["error"]["code"] == "deck_not_found"


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
async def test_a_deck_is_invisible_to_another_user(
    client: AsyncClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    method: str,
) -> None:
    created = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "Private", "source_lang": "en", "target_lang": "uz"},
    )
    url = f"/api/v1/decks/{created.json()['id']}"

    kwargs = {"headers": other_auth_headers}
    if method == "patch":
        kwargs["json"] = {"name": "stolen"}  # type: ignore[assignment]
    response = await getattr(client, method)(url, **kwargs)

    assert response.status_code == 404


async def test_deck_endpoints_require_authentication(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/decks")).status_code == 401
    assert (await client.get("/api/v1/decks/daily")).status_code == 401


async def test_deck_name_cannot_be_empty(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.post(
        "/api/v1/decks",
        headers=auth_headers,
        json={"name": "   ", "source_lang": "en", "target_lang": "uz"},
    )

    assert response.status_code in {201, 422}
    if response.status_code == 201:
        assert response.json()["name"] != "   "
