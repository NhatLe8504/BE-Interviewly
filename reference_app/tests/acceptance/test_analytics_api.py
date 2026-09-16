from __future__ import annotations

import uuid
from decimal import Decimal

from app.infrastructure.persistence.models.enums import (
    Language,
    SessionMode,
    SessionStatus,
    TurnSpeaker,
)
from app.infrastructure.persistence.models.session import (
    AnswerEvaluation,
    InterviewSession,
    InterviewTurn,
    SpeechQualityAnalysis,
)


def unique_email(prefix: str = "analytics") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def _auth_headers(client, email: str, password: str = "password123") -> tuple[dict[str, str], int]:
    client.post(
        "/api/v1/auth/register",
        json={"full_name": "Analytics User", "email": email, "password": password},
    )
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    token = login_res.json()["access_token"]
    me_res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    user_id = me_res.json()["user_id"]
    return {"Authorization": f"Bearer {token}"}, user_id


def test_analytics_dashboard_unauthorized(client) -> None:
    res = client.get("/api/v1/analytics/dashboard")
    assert res.status_code in (401, 403)


def test_analytics_empty_dashboard(client) -> None:
    headers, _ = _auth_headers(client, unique_email())
    res = client.get("/api/v1/analytics/dashboard", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["kpi"]["total_interviews"] == 0
    assert data["kpi"]["completed_interviews"] == 0
    assert data["kpi"]["avg_score"] == 0.0
    assert data["skill_radar"]["clarity"] > 0
    assert isinstance(data["recent_sessions"], list)
    assert isinstance(data["recommendations"], list)


def test_analytics_progress_and_history_empty(client) -> None:
    headers, _ = _auth_headers(client, unique_email())

    res_prog = client.get("/api/v1/analytics/progress", headers=headers)
    assert res_prog.status_code == 200, res_prog.text
    data_prog = res_prog.json()
    assert data_prog["trends"] == []
    assert data_prog["avg_wpm"] > 0

    res_hist = client.get("/api/v1/analytics/history?page=1&page_size=10", headers=headers)
    assert res_hist.status_code == 200, res_hist.text
    data_hist = res_hist.json()
    assert data_hist["items"] == []
    assert data_hist["total"] == 0

    # Test alias
    res_alias = client.get("/api/v1/interviews/history", headers=headers)
    assert res_alias.status_code == 200


def test_analytics_session_not_found(client) -> None:
    headers, _ = _auth_headers(client, unique_email())
    res = client.get("/api/v1/analytics/sessions/99999", headers=headers)
    assert res.status_code == 404

    res_result = client.get("/api/v1/interviews/sessions/99999/result", headers=headers)
    assert res_result.status_code == 404


def test_analytics_with_actual_session_data(client) -> None:
    headers, user_id = _auth_headers(client, unique_email())
    session_factory = client.app.state.services.session_factory

    with session_factory() as db:
        session_obj = InterviewSession(
            candidate_id=user_id,
            language=Language.vi,
            mode=SessionMode.voice,
            status=SessionStatus.completed,
            total_score=Decimal("8.50"),
        )
        db.add(session_obj)
        db.commit()
        db.refresh(session_obj)
        session_id = session_obj.session_id

        turn = InterviewTurn(
            session_id=session_id,
            turn_number=1,
            speaker=TurnSpeaker.candidate,
            message_text="Em đã từng tối ưu hóa query SQL giúp giảm tải 40% cho server.",
            transcribed_text="Em đã từng tối ưu hóa query SQL...",
        )
        db.add(turn)
        db.commit()
        db.refresh(turn)

        evaluation = AnswerEvaluation(
            turn_id=turn.turn_id,
            clarity_score=Decimal("8.50"),
            logic_score=Decimal("8.00"),
            example_score=Decimal("9.00"),
            overall_score=Decimal("8.50"),
            feedback_text="Câu trả lời có dẫn chứng số liệu tốt.",
        )
        db.add(evaluation)

        speech = SpeechQualityAnalysis(
            turn_id=turn.turn_id,
            speaking_pace=Decimal("130.00"),
            hesitation_count=1,
            filler_word_count=1,
            tips_text="Giữ nhịp điệu rất tốt.",
        )
        db.add(speech)
        db.commit()

    # 1. Check dashboard
    res_dash = client.get("/api/v1/analytics/dashboard", headers=headers)
    assert res_dash.status_code == 200, res_dash.text
    dash = res_dash.json()
    assert dash["kpi"]["total_interviews"] == 1
    assert dash["kpi"]["completed_interviews"] == 1
    assert dash["kpi"]["avg_score"] == 85.0
    assert len(dash["recent_sessions"]) == 1
    assert dash["recent_sessions"][0]["session_id"] == session_id

    # 2. Check progress trends
    res_prog = client.get("/api/v1/analytics/progress", headers=headers)
    assert res_prog.status_code == 200
    prog = res_prog.json()
    assert len(prog["trends"]) == 1
    assert prog["trends"][0]["session_id"] == session_id
    assert prog["trends"][0]["overall_score"] == 85.0

    # 3. Check history
    res_hist = client.get("/api/v1/analytics/history", headers=headers)
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert hist["total"] == 1
    assert hist["items"][0]["session_id"] == session_id

    # 4. Check session detail
    res_detail = client.get(f"/api/v1/analytics/sessions/{session_id}", headers=headers)
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["session_id"] == session_id
    assert len(detail["turns"]) == 1
    assert detail["turns"][0]["clarity_score"] == 85.0

    # 5. Check session result report
    res_result = client.get(f"/api/v1/interviews/sessions/{session_id}/result", headers=headers)
    assert res_result.status_code == 200
    result = res_result.json()
    assert result["session_id"] == session_id
    assert result["total_score"] == 85.0
    assert result["readiness_badge"] == "Sẵn sàng ứng tuyển (Interview Ready)"
    assert result["pace_rating"] == "Lý tưởng (Ideal)"
    assert result["star_analysis"]["action"] is True
