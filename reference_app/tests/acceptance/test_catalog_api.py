from __future__ import annotations

import uuid
from sqlalchemy import select
from app.infrastructure.persistence.models.enums import UserRole
from app.infrastructure.persistence.models.user import User


def unique_email(prefix: str = "cat") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def create_admin_client_headers(client) -> dict[str, str]:
    email = unique_email("admin")
    client.post(
        "/api/v1/auth/register",
        json={"full_name": "Admin User", "email": email, "password": "adminpassword123"},
    )
    session = client.app.state.services.session_factory()
    try:
        user = session.execute(select(User).where(User.email == email)).scalar_one()
        user.role = UserRole.admin
        session.commit()
    finally:
        session.close()

    res = client.post("/api/v1/auth/login", json={"email": email, "password": "adminpassword123"})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_public_catalog_flow(client) -> None:
    admin_headers = create_admin_client_headers(client)

    # 1. Create a Domain via Admin
    dom_res = client.post(
        "/api/v1/admin/domains",
        json={"domain_name": f"Software Dev {uuid.uuid4().hex[:6]}", "description": "Tech domain"},
        headers=admin_headers,
    )
    assert dom_res.status_code == 201, dom_res.text
    domain_id = dom_res.json()["domain_id"]

    # 2. Create a Role via Admin
    role_res = client.post(
        "/api/v1/admin/roles",
        json={"domain_id": domain_id, "role_name": "Backend Engineer"},
        headers=admin_headers,
    )
    assert role_res.status_code == 201, role_res.text
    role_id = role_res.json()["role_id"]

    # 3. Create a STAR Template via Admin
    tmpl_res = client.post(
        "/api/v1/admin/star-templates",
        json={
            "title": "STAR Conflict",
            "situation_guide": "Describe a disagreement with coworker",
            "task_guide": "What was your responsibility",
            "action_guide": "What steps did you take",
            "result_guide": "What was the outcome",
            "language": "vi",
        },
        headers=admin_headers,
    )
    assert tmpl_res.status_code == 201, tmpl_res.text
    tmpl_id = tmpl_res.json()["star_template_id"]

    # 4. Create a Question via Admin
    q_res = client.post(
        "/api/v1/admin/questions",
        json={
            "domain_id": domain_id,
            "role_id": role_id,
            "experience_level": "junior",
            "language": "vi",
            "question_type": "behavioral",
            "question_text": "Tell me about a time you had a technical disagreement.",
            "star_template_id": tmpl_id,
        },
        headers=admin_headers,
    )
    assert q_res.status_code == 201, q_res.text
    q_id = q_res.json()["question_id"]

    # 5. Public: List domains
    domains = client.get("/api/v1/catalog/domains").json()
    assert any(d["domain_id"] == domain_id for d in domains)

    # 6. Public: List roles
    roles = client.get(f"/api/v1/catalog/roles?domain_id={domain_id}").json()
    assert len(roles) >= 1
    assert any(r["role_id"] == role_id for r in roles)

    # 7. Public: List questions with filters
    q_page = client.get(f"/api/v1/catalog/questions?domain_id={domain_id}&level=junior").json()
    assert q_page["total"] >= 1
    assert any(q["question_id"] == q_id for q in q_page["items"])

    # 8. Public: Get question detail (includes STAR template)
    detail = client.get(f"/api/v1/catalog/questions/{q_id}").json()
    assert detail["question_id"] == q_id
    assert detail["star_template"] is not None
    assert detail["star_template"]["title"] == "STAR Conflict"

    # 9. Public: Get random question
    rand = client.get(f"/api/v1/catalog/questions/random?domain_id={domain_id}&level=junior").json()
    assert rand["domain_id"] == domain_id
