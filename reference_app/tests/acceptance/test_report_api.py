from __future__ import annotations

from decimal import Decimal
import uuid


def unique_email(prefix: str = "report") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def auth_headers(client, email: str | None = None) -> tuple[dict[str, str], int]:
    email = email or unique_email()
    client.post(
        "/api/v1/auth/register",
        json={"full_name": "Report Tester", "email": email, "password": "password123"},
    )
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    token = login_resp.json()["access_token"]
    user_id = client.app.state.services.auth_service.tokens.parse(token)
    return {"Authorization": f"Bearer {token}"}, user_id


def test_download_pdf_report(client) -> None:
    headers, user_id = auth_headers(client)

    session_factory = client.app.state.services.session_factory
    db = session_factory()
    try:
        from app.infrastructure.persistence.models.session import (
            AnswerEvaluation,
            InterviewSession,
            InterviewTurn,
        )
        from app.infrastructure.persistence.models.enums import (
            Language,
            SessionMode,
            SessionStatus,
            TurnSpeaker,
        )

        sess = InterviewSession(
            candidate_id=user_id,
            language=Language.vi,
            mode=SessionMode.text,
            status=SessionStatus.completed,
            total_score=Decimal("8.5"),
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)
        session_id = sess.session_id

        turn = InterviewTurn(
            session_id=session_id,
            turn_number=1,
            speaker=TurnSpeaker.candidate,
            message_text="Tôi có 3 năm kinh nghiệm Python và FastAPI.",
        )
        db.add(turn)
        db.commit()
        db.refresh(turn)

        ev = AnswerEvaluation(
            turn_id=turn.turn_id,
            clarity_score=Decimal("8.5"),
            logic_score=Decimal("8.0"),
            example_score=Decimal("9.0"),
            overall_score=Decimal("8.5"),
            feedback_text="Trả lời súc tích, logic tốt.",
        )
        db.add(ev)
        db.commit()
    finally:
        db.close()

    resp = client.get(f"/api/v1/sessions/{session_id}/pdf/download", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert f"session_{session_id}_report.pdf" in resp.headers["content-disposition"]


def test_preview_pdf_report(client) -> None:
    headers, user_id = auth_headers(client)
    session_factory = client.app.state.services.session_factory
    db = session_factory()
    try:
        from app.infrastructure.persistence.models.session import InterviewSession
        from app.infrastructure.persistence.models.enums import Language, SessionMode, SessionStatus

        sess = InterviewSession(
            candidate_id=user_id,
            language=Language.vi,
            mode=SessionMode.text,
            status=SessionStatus.completed,
            total_score=Decimal("7.0"),
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)
        session_id = sess.session_id
    finally:
        db.close()

    resp = client.get(f"/api/v1/sessions/{session_id}/pdf/preview", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "inline" in resp.headers["content-disposition"]


def test_pdf_report_not_found(client) -> None:
    headers, _ = auth_headers(client)
    resp = client.get("/api/v1/sessions/999999/pdf/download", headers=headers)
    assert resp.status_code == 404
