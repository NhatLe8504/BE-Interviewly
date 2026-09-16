from __future__ import annotations

import uuid


def unique_email(prefix: str = "profile") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def register_and_get_token(client, email: str | None = None, password: str = "password123") -> tuple[str, str]:
    email = email or unique_email()
    client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Profile Tester",
            "email": email,
            "password": password,
        },
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    token = login_res.json()["access_token"]
    return email, token


def test_profile_endpoints_require_auth(client) -> None:
    assert client.get("/api/v1/profile").status_code == 401
    assert client.get("/api/v1/profile/me").status_code == 401
    assert client.put("/api/v1/profile", json={"bio": "test"}).status_code == 401
    assert client.patch("/api/v1/profile", json={"bio": "test"}).status_code == 401
    assert client.post(
        "/api/v1/profile/change-password",
        json={"current_password": "p", "new_password": "newpassword123"},
    ).status_code == 401


def test_get_and_update_profile_flow(client) -> None:
    email, token = register_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Get initial profile
    res = client.get("/api/v1/profile", headers=headers)
    assert res.status_code == 200, res.text
    profile = res.json()
    assert profile["email"] == email
    assert profile["full_name"] == "Profile Tester"
    assert profile["role"] == "candidate"
    assert profile["preferred_language"] == "vi"
    assert profile["experience_level"] is None
    assert profile["bio"] is None
    assert profile["avatar_url"] is None

    # 2. Check /profile/me alias
    me_res = client.get("/api/v1/profile/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == email

    # 3. Update profile via PUT
    update_payload = {
        "full_name": "Profile Tester Renamed",
        "phone": "0987654321",
        "preferred_language": "en",
        "experience_level": "junior",
        "bio": "Aspiring Python backend engineer.",
        "avatar_url": "https://example.com/photo.png",
    }
    put_res = client.put("/api/v1/profile", json=update_payload, headers=headers)
    assert put_res.status_code == 200, put_res.text
    updated = put_res.json()
    assert updated["full_name"] == "Profile Tester Renamed"
    assert updated["phone"] == "0987654321"
    assert updated["preferred_language"] == "en"
    assert updated["experience_level"] == "junior"
    assert updated["bio"] == "Aspiring Python backend engineer."
    assert updated["avatar_url"] == "https://example.com/photo.png"

    # 4. Partial update via PATCH (only update bio)
    patch_res = client.patch(
        "/api/v1/profile",
        json={"bio": "Updated bio only."},
        headers=headers,
    )
    assert patch_res.status_code == 200, patch_res.text
    patched = patch_res.json()
    assert patched["bio"] == "Updated bio only."
    # Preserved previous fields
    assert patched["full_name"] == "Profile Tester Renamed"
    assert patched["phone"] == "0987654321"
    assert patched["experience_level"] == "junior"


def test_profile_validation_errors(client) -> None:
    _, token = register_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Invalid experience level
    res = client.put(
        "/api/v1/profile",
        json={"experience_level": "grandmaster"},
        headers=headers,
    )
    assert res.status_code == 422

    # Invalid language
    res = client.put(
        "/api/v1/profile",
        json={"preferred_language": "japanese"},
        headers=headers,
    )
    assert res.status_code == 422


def test_change_password_flow(client) -> None:
    email, token = register_and_get_token(client, password="initial_password123")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Wrong current password -> 401
    bad_current = client.post(
        "/api/v1/profile/change-password",
        json={
            "current_password": "wrong_password123",
            "new_password": "updated_password123",
        },
        headers=headers,
    )
    assert bad_current.status_code == 401

    # 2. Too short new password -> 422
    short_pw = client.post(
        "/api/v1/profile/change-password",
        json={
            "current_password": "initial_password123",
            "new_password": "short",
        },
        headers=headers,
    )
    assert short_pw.status_code == 422

    # 3. Successful password change
    change_res = client.post(
        "/api/v1/profile/change-password",
        json={
            "current_password": "initial_password123",
            "new_password": "updated_password123",
        },
        headers=headers,
    )
    assert change_res.status_code == 200
    assert change_res.json()["message"] == "Password changed successfully"

    # 4. Old password fails login
    old_login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "initial_password123"},
    )
    assert old_login.status_code == 401

    # 5. New password succeeds login
    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "updated_password123"},
    )
    assert new_login.status_code == 200
    assert "access_token" in new_login.json()
