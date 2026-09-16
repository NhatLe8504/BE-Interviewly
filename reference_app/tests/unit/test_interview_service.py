from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import pytest

from app.application.interview.commands import (
    CompleteSessionCommand,
    StartSessionCommand,
    SubmitTurnCommand,
)
from app.application.interview.service import InterviewService
from app.domain.errors import DomainValidationError, NotFoundError
from app.domain.interview import InterviewSession, InterviewTurn, SessionStatus


class FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)


class FakeSessionRepo:
    def __init__(self) -> None:
        self.sessions: dict[int, InterviewSession] = {}
        self.next_id = 1

    def create(self, session, data: InterviewSession) -> InterviewSession:
        sid = self.next_id
        self.next_id += 1
        created = InterviewSession(
            session_id=sid,
            user_id=data.user_id,
            domain_id=data.domain_id,
            role_id=data.role_id,
            level=data.level,
            language=data.language,
            mode=data.mode,
            status=data.status,
            started_at=data.started_at,
        )
        self.sessions[sid] = created
        return created

    def find_by_id(self, session, session_id: int) -> InterviewSession | None:
        return self.sessions.get(session_id)

    def update(self, session, data: InterviewSession) -> InterviewSession:
        self.sessions[data.session_id] = data
        return data

    def list_by_user(self, session, user_id: int) -> list[InterviewSession]:
        return [s for s in self.sessions.values() if s.user_id == user_id]


class FakeTurnRepo:
    def __init__(self) -> None:
        self.turns: list[InterviewTurn] = []
        self.next_id = 1

    def add_turn(self, session, turn: InterviewTurn) -> InterviewTurn:
        tid = self.next_id
        self.next_id += 1
        saved = InterviewTurn(
            turn_id=tid,
            session_id=turn.session_id,
            turn_number=turn.turn_number,
            question_text=turn.question_text,
            answer_text=turn.answer_text,
            duration_seconds=turn.duration_seconds,
            speaker=turn.speaker,
        )
        self.turns.append(saved)
        return saved

    def find_by_session_id(self, session, session_id: int) -> list[InterviewTurn]:
        return [t for t in self.turns if t.session_id == session_id]

    def find_turn(self, session, session_id: int, turn_number: int) -> InterviewTurn | None:
        for t in self.turns:
            if t.session_id == session_id and t.turn_number == turn_number:
                return t
        return None

    def update_turn(self, session, turn: InterviewTurn) -> InterviewTurn:
        for i, t in enumerate(self.turns):
            if t.session_id == turn.session_id and t.turn_number == turn.turn_number:
                self.turns[i] = turn
                return turn
        return turn


class FakeLLMInterviewer:
    def generate_first_question(self, role: str, level: str, language: str = "vi") -> str:
        return f"Tell me about your experience as a {role}."

    def generate_follow_up(
        self, history, last_question, last_answer, turn_number, role, level, language="vi", is_final_turn=False,
    ) -> str:
        if is_final_turn:
            return "Thank you, this concludes our interview."
        return f"Follow up question {turn_number} based on: {last_answer[:20]}"

    async def stream_question(self, prompt, system_prompt=None):
        yield prompt


def make_interview_service() -> InterviewService:
    return InterviewService(
        sessions=FakeSessionRepo(),
        turns=FakeTurnRepo(),
        llm=FakeLLMInterviewer(),
        clock=FakeClock(),
    )


def test_start_session_creates_first_turn() -> None:
    service = make_interview_service()
    session, turn = service.start_session(
        None, StartSessionCommand(user_id=1, role_name="Backend Dev", level="junior"),
    )
    assert session.session_id > 0
    assert session.is_active is True
    assert turn.turn_number == 1
    assert "Backend Dev" in turn.question_text


def test_submit_turn_flow() -> None:
    service = make_interview_service()
    session, first_turn = service.start_session(
        None, StartSessionCommand(user_id=2, role_name="DevOps"),
    )

    saved_turn, next_turn, is_completed = service.submit_turn(
        session=None,
        command=SubmitTurnCommand(
            session_id=session.session_id,
            turn_number=1,
            answer_text="I set up CI/CD pipelines with GitHub Actions.",
            duration_seconds=30.0,
        ),
    )
    assert saved_turn.answer_text == "I set up CI/CD pipelines with GitHub Actions."
    assert next_turn is not None
    assert next_turn.turn_number == 2
    assert is_completed is False


def test_complete_session() -> None:
    service = make_interview_service()
    session, _ = service.start_session(
        None, StartSessionCommand(user_id=3),
    )
    completed = service.complete_session(
        None, CompleteSessionCommand(session_id=session.session_id, user_id=3), total_score=Decimal("82.0"),
    )
    assert completed.status == SessionStatus.completed.value
    assert completed.total_score == Decimal("82.0")
