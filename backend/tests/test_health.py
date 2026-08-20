"""M0 gate: the app boots and `/health` answers with the expected shape."""

from httpx import AsyncClient


async def test_health_returns_expected_shape(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["db"] in {"up", "down"}
    assert body["redis"] in {"up", "down"}
    assert body["version"] == "0.1.0"


async def test_unknown_route_uses_the_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/no-such-route")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not Found", "details": {}}
    }
