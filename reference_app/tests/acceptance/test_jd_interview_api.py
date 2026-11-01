from __future__ import annotations

import uuid
from unittest.mock import patch


def unique_email(prefix: str = "jd") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def auth_headers(client, email: str | None = None) -> tuple[dict[str, str], int]:
    email = email or unique_email()
    client.post(
        "/api/v1/auth/register",
        json={"full_name": "JD Candidate", "email": email, "password": "password123"},
    )
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    token = login_resp.json()["access_token"]
    user_id = client.app.state.services.auth_service.tokens.parse(token)
    return {"Authorization": f"Bearer {token}"}, user_id


def test_submit_jd_text_requires_authentication(client) -> None:
    # 1. Anonymous submission -> 401
    anon_resp = client.post(
        "/api/v1/interviews/from-jd/text",
        json={"text": "Software Engineer JD description", "is_public": False},
    )
    assert anon_resp.status_code == 401

    # 2. Authenticated submission -> 202
    headers, user_id = auth_headers(client)
    with patch("app.application.jd_interview.orchestrator.JDWorkflowOrchestrator.execute_pipeline"):
        auth_resp = client.post(
            "/api/v1/interviews/from-jd/text",
            json={"text": "Software Engineer JD description with details", "is_public": False},
            headers=headers,
        )
        assert auth_resp.status_code == 202
        data = auth_resp.json()
        assert data["job_id"].startswith("jd_")


def test_private_and_public_jd_job_boundaries(client) -> None:
    headers_a, user_a_id = auth_headers(client)
    headers_b, user_b_id = auth_headers(client)

    session_factory = client.app.state.services.session_factory
    db = session_factory()
    try:
        from app.infrastructure.persistence.models.jd_interview import JDGenerationJob
        from app.domain.jd_interview import JDJobStatus

        # Private job owned by user A
        private_job = JDGenerationJob(
            job_id=f"jd_{uuid.uuid4().hex[:12]}",
            user_id=user_a_id,
            source_type="text",
            checksum="chk1",
            status=JDJobStatus.COMPLETED.value,
            stage="COMPLETED",
            progress_pct=100,
            is_public=False,
        )
        # Public job owned by user A
        public_job = JDGenerationJob(
            job_id=f"jd_{uuid.uuid4().hex[:12]}",
            user_id=user_a_id,
            source_type="text",
            checksum="chk2",
            status=JDJobStatus.COMPLETED.value,
            stage="COMPLETED",
            progress_pct=100,
            is_public=True,
        )
        db.add_all([private_job, public_job])
        db.commit()
        db.refresh(private_job)
        db.refresh(public_job)
        private_job_id = private_job.job_id
        public_job_id = public_job.job_id
    finally:
        db.close()

    # 1. Private job:
    # Anonymous -> 401
    assert client.get(f"/api/v1/interviews/from-jd/jobs/{private_job_id}/status").status_code == 401
    # Other user B -> 403
    assert client.get(f"/api/v1/interviews/from-jd/jobs/{private_job_id}/status", headers=headers_b).status_code == 403
    # Owner user A -> 200
    assert client.get(f"/api/v1/interviews/from-jd/jobs/{private_job_id}/status", headers=headers_a).status_code == 200

    # 2. Public job:
    # Anonymous -> 200
    assert client.get(f"/api/v1/interviews/from-jd/jobs/{public_job_id}/status").status_code == 200
    # Other user B -> 200
    assert client.get(f"/api/v1/interviews/from-jd/jobs/{public_job_id}/status", headers=headers_b).status_code == 200

    # 3. Community jobs endpoint (public) -> 200
    comm_resp = client.get("/api/v1/interviews/from-jd/community-jobs")
    assert comm_resp.status_code == 200

    # 4. My jobs endpoint (authenticated):
    # Anonymous -> 401
    assert client.get("/api/v1/interviews/from-jd/my-jobs").status_code == 401
    # User B does not see User A's private job
    my_b_resp = client.get("/api/v1/interviews/from-jd/my-jobs", headers=headers_b)
    assert my_b_resp.status_code == 200
    b_job_ids = [j["job_id"] for j in my_b_resp.json()]
    assert private_job_id not in b_job_ids

    # User A sees their job
    my_a_resp = client.get("/api/v1/interviews/from-jd/my-jobs", headers=headers_a)
    assert my_a_resp.status_code == 200
    a_job_ids = [j["job_id"] for j in my_a_resp.json()]
    assert private_job_id in a_job_ids


def test_start_session_from_jd_job_ownership(client) -> None:
    headers_a, user_a_id = auth_headers(client)
    headers_b, user_b_id = auth_headers(client)

    session_factory = client.app.state.services.session_factory
    db = session_factory()
    try:
        from app.infrastructure.persistence.models.jd_interview import JDGenerationJob
        from app.domain.jd_interview import JDJobStatus

        private_job = JDGenerationJob(
            job_id=f"jd_{uuid.uuid4().hex[:12]}",
            user_id=user_a_id,
            source_type="text",
            checksum="chk3",
            status=JDJobStatus.COMPLETED.value,
            stage="COMPLETED",
            progress_pct=100,
            is_public=False,
        )
        db.add(private_job)
        db.commit()
        db.refresh(private_job)
        job_id = private_job.job_id
    finally:
        db.close()

    # Anonymous -> 401
    assert client.post(f"/api/v1/interviews/from-jd/jobs/{job_id}/start-session", json={"mode": "text"}).status_code == 401

    # User B -> 403 Forbidden (does not own private job)
    assert client.post(
        f"/api/v1/interviews/from-jd/jobs/{job_id}/start-session",
        json={"mode": "text"},
        headers=headers_b,
    ).status_code == 403


def test_jd_pipeline_rolls_back_incomplete_job(client) -> None:
    import asyncio
    from app.domain.jd_interview import JDJobStatus
    from app.infrastructure.persistence.models.jd_interview import JDGenerationJob
    from app.presentation.api.routers.jd_interview import _get_or_create_orchestrator

    headers, user_id = auth_headers(client)
    job_id = f"jd_{uuid.uuid4().hex[:12]}"
    session_factory = client.app.state.services.session_factory
    with session_factory() as session:
        session.add(JDGenerationJob(
            job_id=job_id, user_id=user_id, source_type="text", checksum="invalid",
            status=JDJobStatus.PENDING.value, stage="INITIALIZED", progress_pct=5,
            request_payload={"input_data": {"text": "too short"}, "options": {}},
        ))
        session.commit()

    orchestrator = _get_or_create_orchestrator(client.app.state.services)
    result = asyncio.run(orchestrator.execute_pipeline(job_id, user_id, "text", {"text": "too short"}))
    assert result == {}
    with session_factory() as session:
        assert session.get(JDGenerationJob, job_id) is None
    assert orchestrator.queue_manager.get_job_state(job_id) is None
    assert client.get(f"/api/v1/interviews/from-jd/jobs/{job_id}/status", headers=headers).status_code == 404


def test_jd_completion_notification_is_owned_and_acknowledged(client) -> None:
    from app.domain.jd_interview import JDJobStatus
    from app.infrastructure.persistence.models.jd_interview import JDGenerationJob

    owner_headers, owner_id = auth_headers(client)
    other_headers, _ = auth_headers(client)
    job_id = f"jd_{uuid.uuid4().hex[:12]}"
    with client.app.state.services.session_factory() as session:
        session.add(JDGenerationJob(
            job_id=job_id, user_id=owner_id, source_type="text", checksum="ready",
            status=JDJobStatus.COMPLETED.value, stage="COMPLETED", progress_pct=100,
            notification_pending=True,
        ))
        session.commit()

    notifications_url = "/api/v1/interviews/from-jd/notifications"
    acknowledge_url = f"/api/v1/interviews/from-jd/jobs/{job_id}/notification-read"
    assert client.get(notifications_url).status_code == 401
    assert job_id not in [item["job_id"] for item in client.get(notifications_url, headers=other_headers).json()]
    assert client.post(acknowledge_url, headers=other_headers).status_code == 404
    assert job_id in [item["job_id"] for item in client.get(notifications_url, headers=owner_headers).json()]
    assert client.post(acknowledge_url, headers=owner_headers).status_code == 204
    assert job_id not in [item["job_id"] for item in client.get(notifications_url, headers=owner_headers).json()]
