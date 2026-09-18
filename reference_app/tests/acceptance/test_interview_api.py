from __future__ import annotations

import uuid


def unique_email(prefix: str = "interview") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def get_authenticated_headers(client) -> dict[str, str]:
    email = unique_email()
    client.post(
        "/api/v1/auth/register",
        json={"full_name": "Interview Candidate", "email": email, "password": "password123"},
    )
    login_resp = client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_interview_session_and_turn_flow(client) -> None:
    headers = get_authenticated_headers(client)

    # 1. Start interview session
    start_resp = client.post(
        "/api/v1/interviews/sessions",
        json={
            "role_name": "Fullstack Engineer",
            "level": "junior",
            "language": "vi",
            "mode": "text",
            "barge_in_enabled": True,
        },
        headers=headers,
    )
    assert start_resp.status_code == 201, start_resp.text
    session_data = start_resp.json()
    session_id = session_data["session_id"]
    assert session_data["status"] == "in_progress"
    assert session_data["barge_in_enabled"] is True
    assert session_data["current_turn"] is not None
    assert session_data["current_turn"]["turn_number"] == 1
    assert len(session_data["current_turn"]["question_text"]) > 0

    first_turn_id = session_data["current_turn"]["turn_id"]

    # 2. Submit candidate answer for turn 1
    submit_resp = client.post(
        f"/api/v1/interviews/sessions/{session_id}/turns?turn_number=1",
        json={
            "answer_text": "Dạ ừm em từng xây dựng REST API bằng FastAPI và tối ưu database PostgreSQL với index.",
            "duration_seconds": 25.0,
        },
        headers=headers,
    )
    assert submit_resp.status_code == 200, submit_resp.text
    turn_result = submit_resp.json()
    assert turn_result["submitted_turn"]["answer_text"] is not None
    assert turn_result["next_turn"] is not None
    assert turn_result["next_turn"]["turn_number"] == 2

    # 3. Get evaluation for turn 1
    eval_resp = client.get(
        f"/api/v1/interviews/sessions/{session_id}/turns/{first_turn_id}/evaluation",
        headers=headers,
    )
    assert eval_resp.status_code == 200, eval_resp.text
    eval_data = eval_resp.json()
    assert eval_data["clarity_score"] > 0
    assert eval_data["star_analysis"] is not None
    assert eval_data["speech_metrics"] is not None
    assert eval_data["speech_metrics"]["filler_count"] >= 1

    # 4. Get overall session result
    result_resp = client.get(
        f"/api/v1/interviews/sessions/{session_id}/result",
        headers=headers,
    )
    assert result_resp.status_code == 200, result_resp.text
    summary = result_resp.json()
    assert summary["session_id"] == session_id
    assert summary["total_turns"] >= 1
    assert summary["performance_rating"] != ""

    # 5. Test SSE question streaming
    stream_resp = client.get(
        f"/api/v1/interviews/sessions/{session_id}/stream",
        headers=headers,
    )
    assert stream_resp.status_code == 200
    assert "text/event-stream" in stream_resp.headers["content-type"]
    assert "data: " in stream_resp.text


def test_start_session_rejects_invalid_manual_stage_plan(client) -> None:
    headers = get_authenticated_headers(client)
    response = client.post(
        "/api/v1/interviews/sessions",
        json={
            "role_name": "Frontend Engineer",
            "level": "senior",
            "language": "vi",
            "mode": "text",
            "stage_configs": [
                {
                    "stage_key": "technical",
                    "source_mode": "manual",
                    "min_turns": 1,
                    "max_turns": 2,
                    "selected_question_ids": [1],
                },
            ],
        },
        headers=headers,
    )

    assert response.status_code == 422
    assert "manual stage requires" in response.json()["detail"]


def test_start_session_requires_authentication(client) -> None:
    response = client.post(
        "/api/v1/interviews/sessions",
        json={"role_name": "Frontend Engineer"},
    )

    assert response.status_code == 401
