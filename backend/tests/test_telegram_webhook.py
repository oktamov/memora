"""The webhook gate (SPEC §7).

Both secrets are checked before the body is parsed; anything else is 403.
"""

from fastapi import FastAPI
from httpx import AsyncClient

from app.core.config import settings

UPDATE = {
    "update_id": 1,
    "message": {"message_id": 1, "date": 0, "chat": {"id": 1, "type": "private"}},
}


async def test_a_wrong_path_secret_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/telegram/webhook/not-the-secret", json=UPDATE)

    assert response.status_code == 403


async def test_a_missing_header_secret_is_rejected(
    client: AsyncClient, monkeypatch: object
) -> None:
    from pytest import MonkeyPatch

    assert isinstance(monkeypatch, MonkeyPatch)
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "header-secret")

    response = await client.post(
        f"/telegram/webhook/{settings.TELEGRAM_WEBHOOK_PATH_SECRET}", json=UPDATE
    )

    assert response.status_code == 403


async def test_a_wrong_header_secret_is_rejected(client: AsyncClient, monkeypatch: object) -> None:
    from pytest import MonkeyPatch

    assert isinstance(monkeypatch, MonkeyPatch)
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "header-secret")

    response = await client.post(
        f"/telegram/webhook/{settings.TELEGRAM_WEBHOOK_PATH_SECRET}",
        json=UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
    )

    assert response.status_code == 403


async def test_a_bad_secret_is_rejected_before_the_body_is_parsed(client: AsyncClient) -> None:
    """A 403 must not depend on the payload being valid JSON."""
    response = await client.post(
        "/telegram/webhook/wrong",
        content=b"{not json at all",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 403


async def test_correct_secrets_reach_the_dispatcher(
    client: AsyncClient, app: FastAPI, monkeypatch: object
) -> None:
    from pytest import MonkeyPatch

    assert isinstance(monkeypatch, MonkeyPatch)
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "header-secret")

    fed: list[object] = []

    class FakeDispatcher:
        async def feed_update(self, bot: object, update: object) -> None:
            fed.append(update)

    app.state.bot = object()
    app.state.dispatcher = FakeDispatcher()

    response = await client.post(
        f"/telegram/webhook/{settings.TELEGRAM_WEBHOOK_PATH_SECRET}",
        json=UPDATE,
        headers={"X-Telegram-Bot-Api-Secret-Token": "header-secret"},
    )

    assert response.status_code == 200
    assert len(fed) == 1


async def test_the_webhook_reports_unavailable_when_no_bot_is_configured(
    client: AsyncClient, app: FastAPI
) -> None:
    app.state.bot = None
    app.state.dispatcher = None

    response = await client.post(
        f"/telegram/webhook/{settings.TELEGRAM_WEBHOOK_PATH_SECRET}", json=UPDATE
    )

    assert response.status_code == 503


async def test_the_webhook_is_not_under_api_v1(client: AsyncClient) -> None:
    """SPEC §7 puts it outside the versioned API."""
    response = await client.post(
        f"/api/v1/telegram/webhook/{settings.TELEGRAM_WEBHOOK_PATH_SECRET}", json=UPDATE
    )

    assert response.status_code == 404
