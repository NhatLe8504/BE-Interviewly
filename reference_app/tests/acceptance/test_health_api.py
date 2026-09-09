from __future__ import annotations


def test_health_ok_with_database_field(client) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["database"] in ("up", "down")


def test_openapi_exposes_health(client) -> None:
    spec = client.get("/openapi.json").json()
    assert "/health" in spec["paths"]
