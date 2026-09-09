from __future__ import annotations

import uuid


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def test_register_login_me_flow(client) -> None:
    email = unique_email()
    created = client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Test User",
            "email": email,
            "password": "password123",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == email
    assert "password" not in body

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    assert login.json()["token_type"] == "bearer"

    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == email


def test_register_duplicate_returns_409(client) -> None:
    email = unique_email("dup")
    payload = {
        "full_name": "Dup User",
        "email": email,
        "password": "password123",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    again = client.post("/api/v1/auth/register", json=payload)
    assert again.status_code == 409


def test_login_wrong_password_returns_401(client) -> None:
    email = unique_email("login")
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Login User",
            "email": email,
            "password": "password123",
        },
    )
    bad = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "wrong-password"},
    )
    assert bad.status_code == 401


def test_me_without_token_returns_401(client) -> None:
    assert client.get("/api/v1/auth/me").status_code == 401


def test_openapi_exposes_auth_paths(client) -> None:
    spec = client.get("/openapi.json").json()
    assert "/api/v1/auth/register" in spec["paths"]
    assert "/api/v1/auth/login" in spec["paths"]
    assert "/api/v1/auth/me" in spec["paths"]
