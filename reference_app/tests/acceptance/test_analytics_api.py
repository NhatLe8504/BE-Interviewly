from __future__ import annotations

import uuid
from decimal import Decimal

from app.infrastructure.persistence.models.enums import (
    Language,
    SessionMode,
    SessionStatus,
    TurnSpeaker,
)
from app.infrastructure.persistence.models.catalog import JobDomain, JobRole
from app.infrastructure.persistence.models.session import (
    AnswerEvaluation,
    InterviewSession,
    InterviewTurn,
    SpeechQualityAnalysis,
)
from app.infrastructure.persistence.models.session_plan import InterviewFlowState
from app.infrastructure.persistence.evaluation_repository import SqlAlchemyEvaluationRepository


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
    assert data["kpi"]["avg_score"] is None
    assert data["skill_radar"]["clarity"] is None
    assert data["skill_radar"]["delivery"] is None
    assert isinstance(data["recent_sessions"], list)
    assert isinstance(data["recommendations"], list)


def test_analytics_progress_and_history_empty(client) -> None:
    headers, _ = _auth_headers(client, unique_email())

    res_prog = client.get("/api/v1/analytics/progress", headers=headers)
    assert res_prog.status_code == 200, res_prog.text
    data_prog = res_prog.json()
    assert data_prog["trends"] == []
    assert data_prog["avg_wpm"] is None
    assert data_prog["star_mastery_rate"] is None

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
    domain_name = f"Engineering {uuid.uuid4().hex[:8]}"

    with session_factory() as db:
        domain = JobDomain(domain_name=domain_name)
        role = JobRole(domain=domain, role_name="Backend Engineer")
        db.add(role)
        db.flush()
        session_obj = InterviewSession(
            candidate_id=user_id,
            domain_id=domain.domain_id,
            role_id=role.role_id,
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
    assert dash["recent_sessions"][0]["domain_name"] == domain_name
    assert dash["recent_sessions"][0]["role_name"] == "Backend Engineer"

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
    assert hist["items"][0]["role_name"] == "Backend Engineer"

    # 4. Check session detail
    res_detail = client.get(f"/api/v1/analytics/sessions/{session_id}", headers=headers)
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["session_id"] == session_id
    assert detail["domain_name"] == domain_name
    assert len(detail["turns"]) == 1
    assert detail["turns"][0]["clarity_score"] == 85.0

    # 5. Check session result report
    res_result = client.get(f"/api/v1/analytics/sessions/{session_id}/result", headers=headers)
    assert res_result.status_code == 200
    result = res_result.json()
    assert result["session_id"] == session_id
    assert result["total_score"] == 85.0
    assert result["readiness_badge"] == "Kết quả luyện tập nổi bật"
    assert result["pace_rating"] == "Lý tưởng (Ideal)"
    assert result["star_analysis"] is None
    assert result["evaluation_status"] == "ready"
    assert result["pause_duration"] is None
    assert result["filler_words"] == []


def test_voice_result_requires_all_technical_evaluations_and_keeps_zero_score(client) -> None:
    headers, user_id = _auth_headers(client, unique_email())
    session_factory = client.app.state.services.session_factory
    with session_factory() as db:
        interview = InterviewSession(
            candidate_id=user_id, language=Language.vi, mode=SessionMode.voice,
            status=SessionStatus.completed, total_score=Decimal("9.00"),
        )
        db.add(interview)
        db.flush()
        turns = [
            InterviewTurn(session_id=interview.session_id, turn_number=number,
                          speaker=TurnSpeaker.ai, message_text=question,
                          transcribed_text=answer)
            for number, question, answer in (
                (1, "Giới thiệu ngắn về bạn.", "Em là Huy."),
                (2, "Bạn đã tối ưu truy vấn thế nào?", "Em chưa biết."),
                (3, "Bạn dùng cache ở đâu?", "Em chưa dùng."),
            )
        ]
        db.add_all(turns)
        db.flush()
        db.add(InterviewFlowState(session_id=interview.session_id, snapshot={
            "items": [
                {"stage": "warmup", "answers": [{"turn_id": 1}]},
                {"stage": "technical", "answers": [{"turn_id": 2}, {"turn_id": 3}]},
            ],
        }))
        db.add(AnswerEvaluation(
            turn_id=turns[1].turn_id, clarity_score=Decimal("0"),
            logic_score=Decimal("0"), example_score=Decimal("0"),
            overall_score=Decimal("0"), feedback_text="Chưa giải thích được cách tối ưu.",
            question_type="technical",
        ))
        third_turn_id = turns[2].turn_id
        db.commit()
        session_id = interview.session_id

    endpoint = f"/api/v1/analytics/sessions/{session_id}/result"
    partial = client.get(endpoint, headers=headers)
    assert partial.status_code == 200, partial.text
    assert partial.json()["evaluation_status"] == "partial"
    assert partial.json()["total_score"] is None
    assert partial.json()["evaluated_turns"] == 1
    assert partial.json()["eligible_turns"] == 2
    assert partial.json()["turns"][1]["transcribed_text"] == "Em chưa biết."
    assert partial.json()["turns"][1]["feedback_text"] == "Chưa giải thích được cách tối ưu."

    with session_factory() as db:
        db.add(AnswerEvaluation(
            turn_id=third_turn_id, clarity_score=Decimal("0"),
            logic_score=Decimal("0"), example_score=Decimal("0"),
            overall_score=Decimal("0"), feedback_text="Chưa có bằng chứng về cache.",
            question_type="technical",
        ))
        db.flush()
        SqlAlchemyEvaluationRepository().refresh_session_score(db, session_id)
        assert db.get(InterviewSession, session_id).total_score == 0
        db.commit()

    ready = client.get(endpoint, headers=headers)
    assert ready.status_code == 200, ready.text
    assert ready.json()["evaluation_status"] == "ready"
    assert ready.json()["total_score"] == 0
    assert ready.json()["clarity_score"] == 0
    assert ready.json()["readiness_badge"] == "Cần luyện tập nền tảng"
    assert ready.json()["speaking_pace_wpm"] is None


def test_voice_result_weights_jd_items_not_followup_count(client) -> None:
    headers, user_id = _auth_headers(client, unique_email())
    session_factory = client.app.state.services.session_factory
    with session_factory() as db:
        interview = InterviewSession(
            candidate_id=user_id, language=Language.vi, mode=SessionMode.voice,
            status=SessionStatus.completed,
        )
        db.add(interview)
        db.flush()
        turns = [
            InterviewTurn(
                session_id=interview.session_id, turn_number=number,
                speaker=TurnSpeaker.ai, message_text=f"Câu hỏi {number}",
                transcribed_text=f"Câu trả lời {number}",
            ) for number in (1, 2, 3)
        ]
        db.add_all(turns)
        db.flush()
        db.add(InterviewFlowState(session_id=interview.session_id, snapshot={
            "items": [
                {"stage": "technical", "answers": [{"turn_id": 1}, {"turn_id": 2}]},
                {"stage": "technical", "answers": [{"turn_id": 3}]},
            ],
        }))
        for turn, score in zip(turns, (Decimal("10"), Decimal("0"), Decimal("10"))):
            db.add(AnswerEvaluation(
                turn_id=turn.turn_id, clarity_score=score, logic_score=score,
                example_score=score, overall_score=score, question_type="technical",
            ))
        db.flush()
        SqlAlchemyEvaluationRepository().refresh_session_score(db, interview.session_id)
        session_id = interview.session_id
        assert interview.total_score == Decimal("7.50")
        db.commit()

    response = client.get(f"/api/v1/analytics/sessions/{session_id}/result", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["evaluation_status"] == "ready"
    assert response.json()["evaluated_turns"] == 3
    assert response.json()["total_score"] == 75
    assert response.json()["clarity_score"] == 75

    summary = client.get(f"/api/v1/interviews/sessions/{session_id}/result", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["total_score"] == response.json()["total_score"]
    assert summary.json()["avg_clarity"] == response.json()["clarity_score"]
