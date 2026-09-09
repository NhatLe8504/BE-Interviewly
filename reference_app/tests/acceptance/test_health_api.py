from __future__ import annotations


def test_health_ok(client) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_openapi_exposes_health(client) -> None:
    spec = client.get("/openapi.json").json()
    assert "/health" in spec["paths"]
