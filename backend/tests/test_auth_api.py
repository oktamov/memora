"""M1 acceptance: a valid initData returns a token that opens deck endpoints;
a tampered one does not (SPEC §11 M1)."""

import json
import time
from urllib.parse import parse_qsl, urlencode

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from tests.factories import make_init_data


async def test_valid_init_data_returns_a_token_that_opens_deck_endpoints(
    client: AsyncClient,
) -> None:
    auth = await client.post(
        "/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id=1234)}
    )

    assert auth.status_code == 200
    body = auth.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 86_400

    decks = await client.get(
        "/api/v1/decks", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert decks.status_code == 200


async def test_tampered_init_data_is_rejected(client: AsyncClient) -> None:
    fields = dict(parse_qsl(make_init_data(telegram_id=1234), keep_blank_values=True))
    user = json.loads(fields["user"])
    user["id"] = 999
    fields["user"] = json.dumps(user, separators=(",", ":"))

    response = await client.post("/api/v1/auth/telegram", json={"init_data": urlencode(fields)})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "init_data_bad_hash"


async def test_stale_init_data_is_rejected(client: AsyncClient) -> None:
    stale = make_init_data(auth_date=int(time.time()) - 90_000)

    response = await client.post("/api/v1/auth/telegram", json={"init_data": stale})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "init_data_expired"


async def test_authentication_upserts_by_telegram_id_not_username(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """A renamed user must remain the same row (SPEC §13)."""
    await client.post(
        "/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id=55, username="old")}
    )
    await client.post(
        "/api/v1/auth/telegram", json={"init_data": make_init_data(telegram_id=55, username="new")}
    )

    users = (await db_session.scalars(select(User).where(User.telegram_id == 55))).all()
    assert len(users) == 1
    assert users[0].username == "new"


async def test_new_user_gets_the_spec_defaults(client: AsyncClient) -> None:
    auth = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": make_init_data(telegram_id=99, language_code="uz")},
    )
    headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}

    me = await client.get("/api/v1/auth/me", headers=headers)

    assert me.status_code == 200
    body = me.json()
    assert body["native_lang"] == "uz"
    assert body["ui_lang"] == "uz"
    assert body["daily_new_limit"] == 20
    assert body["daily_review_limit"] == 200
    assert body["lookup_quota_per_day"] == 100
    assert body["timezone"] == "Asia/Tashkent"
    assert body["reminder_hour"] == 20
    assert body["reminder_enabled"] is True
    assert body["is_active"] is True


async def test_native_lang_defaults_from_language_code(client: AsyncClient) -> None:
    auth = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": make_init_data(telegram_id=101, language_code="ru")},
    )
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {auth.json()['access_token']}"},
    )

    assert me.json()["native_lang"] == "ru"


async def test_unsupported_language_code_falls_back_to_uz(client: AsyncClient) -> None:
    auth = await client.post(
        "/api/v1/auth/telegram",
        json={"init_data": make_init_data(telegram_id=102, language_code="ja")},
    )
    me = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {auth.json()['access_token']}"},
    )

    assert me.json()["native_lang"] == "uz"


async def test_me_requires_a_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_a_garbage_token_is_rejected(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-jwt"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_invalid"


async def test_patch_me_updates_settings(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    response = await client.patch(
        "/api/v1/auth/me",
        headers=auth_headers,
        json={
            "native_lang": "ru",
            "daily_new_limit": 5,
            "timezone": "Europe/Moscow",
            "reminder_hour": 7,
            "reminder_enabled": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["native_lang"] == "ru"
    assert body["daily_new_limit"] == 5
    assert body["timezone"] == "Europe/Moscow"
    assert body["reminder_hour"] == 7
    assert body["reminder_enabled"] is False
    # Untouched fields stay put.
    assert body["daily_review_limit"] == 200


async def test_patch_me_rejects_an_unknown_timezone(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    response = await client.patch(
        "/api/v1/auth/me", headers=auth_headers, json={"timezone": "Mars/Olympus_Mons"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_a_client_sent_telegram_id_is_never_accepted(client: AsyncClient) -> None:
    """SPEC §13: anyone can post any user id. The body must not carry one."""
    response = await client.post(
        "/api/v1/auth/telegram", json={"init_data": make_init_data(), "telegram_id": 1}
    )

    assert response.status_code == 422
