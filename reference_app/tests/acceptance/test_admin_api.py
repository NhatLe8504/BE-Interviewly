from __future__ import annotations

import uuid
from sqlalchemy import select
from app.infrastructure.persistence.models.enums import UserRole
from app.infrastructure.persistence.models.user import User


def unique_email(prefix: str = "adm") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def create_candidate_and_token(client) -> tuple[int, dict[str, str]]:
    email = unique_email("candidate")
    reg = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Candidate One", "email": email, "password": "password123"},
    )
    user_id = reg.json()["user_id"]
    res = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    token = res.json()["access_token"]
    return user_id, {"Authorization": f"Bearer {token}"}


def create_admin_and_token(client) -> tuple[int, dict[str, str]]:
    email = unique_email("admin")
    reg = client.post(
        "/api/v1/auth/register",
        json={"full_name": "Admin Boss", "email": email, "password": "password123"},
    )
    user_id = reg.json()["user_id"]

    session = client.app.state.services.session_factory()
    try:
        user = session.execute(select(User).where(User.email == email)).scalar_one()
        user.role = UserRole.admin
        session.commit()
    finally:
        session.close()

    res = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    token = res.json()["access_token"]
    return user_id, {"Authorization": f"Bearer {token}"}


def test_candidate_forbidden_from_admin_endpoints(client) -> None:
    _, candidate_headers = create_candidate_and_token(client)
    assert client.get("/api/v1/admin/users", headers=candidate_headers).status_code == 403
    assert client.get("/api/v1/admin/stats", headers=candidate_headers).status_code == 403
    assert client.get("/api/v1/admin/audit-logs", headers=candidate_headers).status_code == 403
    assert client.post("/api/v1/admin/domains", json={"domain_name": "Forbidden"}, headers=candidate_headers).status_code == 403


def test_admin_user_management_and_stats(client) -> None:
    cand_id, _ = create_candidate_and_token(client)
    _, admin_headers = create_admin_and_token(client)

    # 1. List users
    users_res = client.get("/api/v1/admin/users", headers=admin_headers)
    assert users_res.status_code == 200
    body = users_res.json()
    assert body["total"] >= 2
    assert any(u["user_id"] == cand_id for u in body["items"])

    # 2. Suspend candidate
    status_res = client.patch(
        f"/api/v1/admin/users/{cand_id}/status",
        json={"status": "suspended"},
        headers=admin_headers,
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "suspended"

    # 3. Promote candidate to admin
    role_res = client.patch(
        f"/api/v1/admin/users/{cand_id}/role",
        json={"role": "admin"},
        headers=admin_headers,
    )
    assert role_res.status_code == 200
    assert role_res.json()["role"] == "admin"

    # 4. Get stats
    stats_res = client.get("/api/v1/admin/stats", headers=admin_headers)
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_users"] >= 2

    # 5. Check audit logs
    audit_res = client.get("/api/v1/admin/audit-logs", headers=admin_headers)
    assert audit_res.status_code == 200
    audits = audit_res.json()["items"]
    assert any(a["table_name"] == "users" and a["record_id"] == cand_id for a in audits)
