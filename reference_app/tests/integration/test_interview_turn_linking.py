"""Phase 2 (LOI #5): liên kết lượt phỏng vấn với ngân hàng câu hỏi.

- Luồng text: mỗi lượt phải được gắn question_id thật + used_at_turn.
- Luồng voice/JD: chỉ ghi evidence khi lượt có question_id + evaluation + câu trả lời.

Chạy trên PostgreSQL thật (cùng DB cấu hình cho app) và tự dọn dẹp.
Nếu DB không khả dụng thì skip để không làm đỏ CI.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.application.evaluation.ports import RubricEvaluationData
from app.application.evaluation.service import EvaluationService
from app.application.interview.commands import (
    StageConfigCommand,
    StartSessionCommand,
    SubmitTurnCommand,
)
from app.application.interview.intent_composer import QuestionIntentContext
from app.application.interview.service import InterviewService
from app.application.voice.orchestrator import VoiceInterviewOrchestrator
from app.application.skills.service import UserSkillService
from app.config import Settings
from app.infrastructure.database import create_engine_from_url
from app.infrastructure.orm import Base, create_session_factory
from app.infrastructure.persistence.models.catalog import QuestionBank
from app.infrastructure.persistence.models.enums import (
    ExperienceLevel,
    Language,
    SessionMode,
    SessionStatus,
    TurnSpeaker,
)
from app.infrastructure.persistence.models.session import (
    AnswerEvaluation,
    InterviewSession,
    InterviewTurn,
)
from app.infrastructure.persistence.models.session_plan import SessionQuestionSelection
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_skills import UserSkillEvidenceRecord
from app.infrastructure.persistence.catalog_repository import SqlAlchemyCatalogRepository
from app.infrastructure.persistence.evaluation_repository import SqlAlchemyEvaluationRepository
from app.infrastructure.persistence.session_repository import SqlAlchemySessionRepository


@pytest.fixture(scope="module")
def pg_session_factory():
    settings = Settings.from_env()
    try:
        engine = create_engine_from_url(settings.database_url)
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception as exc:  # pragma: no cover - phụ thuộc môi trường
        pytest.skip(f"PostgreSQL không khả dụng cho integration test: {exc}")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


class _StubLLM:
    def __init__(self) -> None:
        self.seed_intents: list[str | None] = []

    def generate_first_question(self, role: str, level: str, language: str = "vi") -> str:
        return f"Kể về kinh nghiệm {role} của bạn?"

    def generate_follow_up(
        self, history, last_question, last_answer, turn_number, role, level,
        language="vi", is_final_turn=False, seed_intent=None,
    ) -> str:
        self.seed_intents.append(seed_intent)
        if is_final_turn:
            return "Cảm ơn bạn đã hoàn thành buổi phỏng vấn."
        return f"Câu hỏi follow-up {turn_number}?"

    async def stream_question(self, prompt, system_prompt=None):
        yield prompt


class _Clock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def _create_user(session_factory) -> int:
    user_id = random.randint(9_000_000_000, 9_999_999_999)
    db = session_factory()
    try:
        db.add(User(
            user_id=user_id,
            full_name="Turn Linking Test",
            email=f"turn-linking-{user_id}@example.com",
            password_hash="not-used",
        ))
        db.commit()
    finally:
        db.close()
    return user_id


def _cleanup_user(session_factory, user_id: int) -> None:
    db = session_factory()
    try:
        db.execute(delete(User).where(User.user_id == user_id))
        db.commit()
    finally:
        db.close()


def _question_with_skills(session_factory):
    db = session_factory()
    try:
        for candidate in db.scalars(select(QuestionBank).limit(100)).all():
            if candidate.skill_ids and candidate.is_active:
                return int(candidate.question_id), list(candidate.skill_ids)
        return None
    finally:
        db.close()


def test_text_session_links_turns_to_bank_questions(pg_session_factory):
    """LOI #5: turn của luồng text phải có question_id thật, không chỉ selection_order."""
    if _question_with_skills(pg_session_factory) is None:
        pytest.skip("Ngân hàng câu hỏi trống để kiểm thử liên kết")

    user_id = _create_user(pg_session_factory)
    try:
        llm = _StubLLM()
        repo = SqlAlchemySessionRepository()
        service = InterviewService(sessions=repo, turns=repo, llm=llm, clock=_Clock())

        db = pg_session_factory()
        try:
            interview_session, first_turn = service.start_session(
                db,
                StartSessionCommand(user_id=user_id, role_name="Backend Developer", level="junior"),
            )
            assert first_turn.question_id is not None, "lượt đầu phải gắn câu hỏi ngân hàng"
            first_selection = db.execute(
                select(SessionQuestionSelection).where(
                    SessionQuestionSelection.session_id == interview_session.session_id,
                    SessionQuestionSelection.question_id == first_turn.question_id,
                )
            ).scalars().first()
            assert first_selection is not None
            assert first_selection.used_at_turn == 1

            _, next_turn, is_completed = service.submit_turn(
                db,
                SubmitTurnCommand(
                    session_id=interview_session.session_id,
                    turn_number=1,
                    answer_text="Tôi đã xây dựng REST API với Spring Boot và PostgreSQL.",
                    duration_seconds=25.0,
                ),
                role_name="Backend Developer",
                level="junior",
            )
            assert is_completed is False
            assert next_turn.question_id is not None, "lượt kế tiếp phải gắn câu hỏi ngân hàng"
            assert next_turn.question_id != first_turn.question_id, "không được lặp lại câu đã hỏi"
            assert llm.seed_intents[-1], "LLM phải nhận seed intent từ câu hỏi ngân hàng"

            next_selection = db.execute(
                select(SessionQuestionSelection).where(
                    SessionQuestionSelection.session_id == interview_session.session_id,
                    SessionQuestionSelection.question_id == next_turn.question_id,
                )
            ).scalars().first()
            assert next_selection is not None
            assert next_selection.used_at_turn == 2
        finally:
            db.close()
    finally:
        _cleanup_user(pg_session_factory, user_id)


def test_sync_interview_turn_writes_evidence_only_when_linked(pg_session_factory):
    """LOI #5: lượt speaker=ai có answer + evaluation + question_id mới sinh evidence."""
    found = _question_with_skills(pg_session_factory)
    if found is None:
        pytest.skip("Ngân hàng câu hỏi trống để kiểm thử liên kết")
    question_id, skill_ids = found

    answer = "Tôi dùng EXPLAIN ANALYZE để tìm nguyên nhân và thêm composite index cho bảng đơn hàng."
    user_id = _create_user(pg_session_factory)
    try:
        setup = pg_session_factory()
        try:
            orm_session = InterviewSession(
                candidate_id=user_id,
                experience_level=ExperienceLevel.fresher,
                language=Language.vi,
                mode=SessionMode.voice,
                barge_in_enabled=True,
                status=SessionStatus.in_progress,
            )
            setup.add(orm_session)
            setup.flush()

            linked_turn = InterviewTurn(
                session_id=orm_session.session_id,
                turn_number=1,
                speaker=TurnSpeaker.ai,
                message_text="Bạn tối ưu slow query như thế nào?",
                transcribed_text=answer,
                audio_url="voice_streamed",
                question_id=question_id,
            )
            unlinked_turn = InterviewTurn(
                session_id=orm_session.session_id,
                turn_number=2,
                speaker=TurnSpeaker.ai,
                message_text="Câu hỏi sinh từ kịch bản JD?",
                transcribed_text=answer,
                audio_url="voice_streamed",
                question_id=None,
            )
            setup.add_all([linked_turn, unlinked_turn])
            setup.flush()
            setup.add(AnswerEvaluation(turn_id=linked_turn.turn_id, overall_score=Decimal("8.0")))
            setup.add(AnswerEvaluation(turn_id=unlinked_turn.turn_id, overall_score=Decimal("9.0")))
            setup.commit()
            session_id = int(orm_session.session_id)
            linked_turn_id = int(linked_turn.turn_id)
        finally:
            setup.close()

        verify = pg_session_factory()
        try:
            svc = UserSkillService(session=verify)
            expected_skills = {
                normalized for normalized in (
                    svc.taxonomy.normalize_skill_id(sid) for sid in set(skill_ids)
                ) if normalized
            }
            assert expected_skills, "câu hỏi kiểm thử phải map được ít nhất một skill"

            recorded = svc.sync_interview_turn(session_id, 1)
            assert recorded == len(expected_skills)

            evidence = verify.scalars(
                select(UserSkillEvidenceRecord).where(UserSkillEvidenceRecord.user_id == user_id)
            ).all()
            assert {row.skill_id for row in evidence} == expected_skills
            assert all(row.source_type == "interview_session" for row in evidence)
            assert all(row.source_id == f"session_{session_id}_turn_{linked_turn_id}" for row in evidence)
            assert all(row.input_mode == "voice" for row in evidence)
            assert float(evidence[0].score) == pytest.approx(0.8)
            assert evidence[0].evidence_quote == answer

            # Lượt 2 không có question_id -> không ghi thêm evidence
            assert svc.sync_interview_turn(session_id, 2) == 0
            verify.expire_all()
            assert len(verify.scalars(
                select(UserSkillEvidenceRecord).where(UserSkillEvidenceRecord.user_id == user_id)
            ).all()) == len(evidence)

            # Gọi lại lượt 1 -> idempotent, không nhân đôi bằng chứng
            assert svc.sync_interview_turn(session_id, 1) == len(expected_skills)
            verify.expire_all()
            assert len(verify.scalars(
                select(UserSkillEvidenceRecord).where(UserSkillEvidenceRecord.user_id == user_id)
            ).all()) == len(evidence)
        finally:
            verify.close()
    finally:
        _cleanup_user(pg_session_factory, user_id)


class _FakeConnection:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def is_open(self) -> bool:
        return True

    async def send_event(self, event: dict) -> None:
        self.events.append(event)


class _FakeTTS:
    async def synthesize_stream(self, text: str, voice: str = "vi-VN-HoaiMyNeural"):
        yield b""


class _FakeVoiceLLM:
    async def stream_ai_tokens(self, messages):
        yield "OK"


class _StubEvaluator:
    def evaluate(
        self, question: str, answer: str, role: str = "Software Engineer",
        level: str = "fresher", language: str = "vi",
    ) -> RubricEvaluationData:
        return RubricEvaluationData(
            clarity_score=80.0,
            structure_score=80.0,
            evidence_score=80.0,
            star_analysis={"situation": True, "task": True, "action": True, "result": True},
            feedback="Câu trả lời ổn.",
            sample_better_answer="Câu trả lời mẫu.",
        )


def test_voice_orchestrator_chain_links_evaluates_and_tracks(pg_session_factory):
    """Chuỗi voice: persist lượt có question_id -> chấm điểm -> ghi evidence."""
    found = _question_with_skills(pg_session_factory)
    if found is None:
        pytest.skip("Ngân hàng câu hỏi trống để kiểm thử liên kết")
    question_id, skill_ids = found

    user_id = _create_user(pg_session_factory)
    try:
        setup = pg_session_factory()
        try:
            orm_session = InterviewSession(
                candidate_id=user_id,
                experience_level=ExperienceLevel.junior,
                language=Language.vi,
                mode=SessionMode.voice,
                barge_in_enabled=True,
                status=SessionStatus.in_progress,
            )
            setup.add(orm_session)
            setup.flush()
            setup.add(SessionQuestionSelection(
                session_id=orm_session.session_id,
                stage_key="warmup",
                question_id=question_id,
                selection_order=1,
                was_rerolled=False,
            ))
            setup.commit()
            session_id = int(orm_session.session_id)
        finally:
            setup.close()

        orchestrator = VoiceInterviewOrchestrator(
            session_id=session_id,
            connection=_FakeConnection(),
            tts=_FakeTTS(),
            llm=_FakeVoiceLLM(),
            role_name="Backend Developer",
            level="junior",
            language="vi",
            session_factory=pg_session_factory,
            evaluation_service=EvaluationService(
                evaluations=SqlAlchemyEvaluationRepository(),
                evaluator=_StubEvaluator(),
                clock=_Clock(),
            ),
        )

        intent = QuestionIntentContext(
            question_id=question_id,
            intent="Tối ưu truy vấn chậm trong PostgreSQL.",
            stage_key="warmup",
            difficulty=3,
        )
        orchestrator._persist_ai_turn(1, "Bạn tối ưu slow query như thế nào?", intent)
        answer = "Tôi dùng EXPLAIN ANALYZE để tìm nguyên nhân và thêm composite index."
        orchestrator._persist_user_transcript(1, answer)
        orchestrator._evaluate_and_track_answer_sync(1, answer)

        verify = pg_session_factory()
        try:
            turn = verify.execute(
                select(InterviewTurn).where(
                    InterviewTurn.session_id == session_id,
                    InterviewTurn.turn_number == 1,
                )
            ).scalars().first()
            assert turn is not None
            assert turn.question_id == question_id

            selection = verify.execute(
                select(SessionQuestionSelection).where(
                    SessionQuestionSelection.session_id == session_id,
                )
            ).scalars().first()
            assert selection is not None
            assert selection.used_at_turn == 1

            evaluation = verify.execute(
                select(AnswerEvaluation).where(AnswerEvaluation.turn_id == turn.turn_id)
            ).scalars().first()
            assert evaluation is not None
            assert float(evaluation.overall_score) == pytest.approx(8.0)

            svc = UserSkillService(session=verify)
            expected_skills = {
                normalized for normalized in (
                    svc.taxonomy.normalize_skill_id(sid) for sid in set(skill_ids)
                ) if normalized
            }
            evidence = verify.scalars(
                select(UserSkillEvidenceRecord).where(UserSkillEvidenceRecord.user_id == user_id)
            ).all()
            assert {row.skill_id for row in evidence} == expected_skills
            assert all(row.source_type == "interview_session" for row in evidence)
            assert all(row.input_mode == "voice" for row in evidence)
            assert all(float(row.score) == pytest.approx(0.8) for row in evidence)
        finally:
            verify.close()
    finally:
        _cleanup_user(pg_session_factory, user_id)


def test_manual_stage_config_links_selected_questions(pg_session_factory):
    """Stage chọn tay: lượt phải gắn đúng question_id đã chọn, không random."""
    db = pg_session_factory()
    try:
        rows = db.execute(
            select(QuestionBank).where(
                QuestionBank.is_active == True,  # noqa: E712
                QuestionBank.language == Language.vi,
            ).limit(5)
        ).scalars().all()
    finally:
        db.close()
    if len(rows) < 2:
        pytest.skip("Cần ít nhất 2 câu hỏi tiếng Việt đã duyệt để kiểm thử manual mode")
    question_a = int(rows[0].question_id)
    question_b = int(rows[1].question_id)

    user_id = _create_user(pg_session_factory)
    try:
        llm = _StubLLM()
        repo = SqlAlchemySessionRepository()
        service = InterviewService(
            sessions=repo,
            turns=repo,
            llm=llm,
            clock=_Clock(),
            questions=SqlAlchemyCatalogRepository(),
        )
        db = pg_session_factory()
        try:
            interview_session, first_turn = service.start_session(
                db,
                StartSessionCommand(
                    user_id=user_id,
                    role_name="Backend Developer",
                    level="junior",
                    stage_configs=[
                        StageConfigCommand(
                            stage_key="warmup",
                            source_mode="manual",
                            min_turns=1,
                            max_turns=1,
                            selected_question_ids=[question_a],
                        ),
                        StageConfigCommand(
                            stage_key="technical",
                            source_mode="manual",
                            min_turns=1,
                            max_turns=1,
                            selected_question_ids=[question_b],
                        ),
                    ],
                ),
            )
            assert first_turn.question_id == question_a

            _, next_turn, is_completed = service.submit_turn(
                db,
                SubmitTurnCommand(
                    session_id=interview_session.session_id,
                    turn_number=1,
                    answer_text="Tôi đã triển khai hệ thống với các công nghệ được hỏi.",
                    duration_seconds=20.0,
                ),
                role_name="Backend Developer",
                level="junior",
            )
            assert is_completed is False
            assert next_turn.question_id == question_b
        finally:
            db.close()
    finally:
        _cleanup_user(pg_session_factory, user_id)
