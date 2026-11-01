from __future__ import annotations

import uuid

from app.application.evaluation.ports import RubricEvaluationData


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
    class RubricEvaluator:
        def evaluate(self, **kwargs) -> RubricEvaluationData:
            return RubricEvaluationData(
                clarity_score=80, structure_score=75, evidence_score=70,
                star_analysis={"situation": False, "task": False, "action": False, "result": False},
                feedback="Nêu rõ hơn lý do lựa chọn giải pháp.", sample_better_answer="",
            )

    client.app.state.services.evaluation_service.evaluator = RubricEvaluator()
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
    assert "star_analysis" in eval_data
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
    assert summary["evaluation_status"] == "pending"
    assert summary["total_score"] is None

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



from unittest.mock import patch

def test_interview_read_ownership_and_boundaries(client) -> None:
    async def mock_stream(self, text):
        yield "Xin"
        yield " chào"

    with patch(
        "app.infrastructure.llm.openai_adapter.OpenAILLMAdapter.generate_first_question",
        return_value="Xin chào, hãy giới thiệu bản thân.",
    ), patch(
        "app.infrastructure.llm.openai_adapter.OpenAILLMAdapter.stream_question",
        mock_stream,
    ):
        # 1. User A creates a session
        headers_a = get_authenticated_headers(client)
        start_resp = client.post(
            "/api/v1/interviews/sessions",
            json={
                "role_name": "Fullstack Engineer",
                "level": "junior",
                "language": "vi",
                "mode": "text",
            },
            headers=headers_a,
        )
        assert start_resp.status_code == 201
        session_data = start_resp.json()
        session_id = session_data["session_id"]
        first_turn_id = session_data["current_turn"]["turn_id"]

        # 2. User B
        headers_b = get_authenticated_headers(client)

        # 3. GET session details boundaries
        # Anonymous -> 401
        assert client.get(f"/api/v1/interviews/sessions/{session_id}").status_code == 401
        # Other user -> 403
        assert client.get(f"/api/v1/interviews/sessions/{session_id}", headers=headers_b).status_code == 403
        # Nonexistent session -> 404
        assert client.get("/api/v1/interviews/sessions/999999", headers=headers_a).status_code == 404
        # Owner -> 200
        owner_resp = client.get(f"/api/v1/interviews/sessions/{session_id}", headers=headers_a)
        assert owner_resp.status_code == 200
        assert owner_resp.json()["session_id"] == session_id

        # 4. SSE Stream boundaries
        # Anonymous -> 401
        assert client.get(f"/api/v1/interviews/sessions/{session_id}/stream").status_code == 401
        # Other user -> 403
        assert client.get(f"/api/v1/interviews/sessions/{session_id}/stream", headers=headers_b).status_code == 403
        # Owner via Bearer header -> 200
        assert client.get(f"/api/v1/interviews/sessions/{session_id}/stream", headers=headers_a).status_code == 200
        # Owner via query token -> 200
        token_a = headers_a["Authorization"].split("Bearer ", 1)[1]
        query_stream_resp = client.get(f"/api/v1/interviews/sessions/{session_id}/stream?token={token_a}")
        assert query_stream_resp.status_code == 200
        assert "text/event-stream" in query_stream_resp.headers["content-type"]

        # 5. Evaluation boundaries
        # Anonymous -> 401
        assert client.get(f"/api/v1/interviews/sessions/{session_id}/turns/{first_turn_id}/evaluation").status_code == 401
        # Other user -> 403
        assert client.get(f"/api/v1/interviews/sessions/{session_id}/turns/{first_turn_id}/evaluation", headers=headers_b).status_code == 403
        # Mismatched turn ID that does not belong to session -> 404
        assert client.get(f"/api/v1/interviews/sessions/{session_id}/turns/999999/evaluation", headers=headers_a).status_code == 404

        # 6. Session Result boundaries
        # Anonymous -> 401
        assert client.get(f"/api/v1/interviews/sessions/{session_id}/result").status_code == 401
        # Other user -> 403
        assert client.get(f"/api/v1/interviews/sessions/{session_id}/result", headers=headers_b).status_code == 403
        # Owner -> 200
        assert client.get(f"/api/v1/interviews/sessions/{session_id}/result", headers=headers_a).status_code == 200
