from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.application.interview.intent_composer import QuestionIntentComposer, QuestionIntentContext
from app.application.interview.question_selection import QuestionSelectionService
from app.infrastructure.orm import Base
from app.infrastructure.persistence.models.catalog import JobDomain, JobRole, QuestionBank
from app.infrastructure.persistence.models.enums import ExperienceLevel, Language, QuestionModerationStatus, QuestionType, QuestionSource
from app.infrastructure.persistence.models.session import InterviewSession


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    from app.infrastructure.persistence.models.session_plan import InterviewSessionConfig, SessionQuestionSelection
    tables = [
        JobDomain.__table__,
        JobRole.__table__,
        QuestionBank.__table__,
        InterviewSessionConfig.__table__,
        SessionQuestionSelection.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    domain = JobDomain(domain_name="Backend", description="Backend domain")
    session.add(domain)
    session.flush()

    role = JobRole(domain_id=domain.domain_id, role_name="Backend Engineer")
    session.add(role)
    session.flush()

    # Add 3 approved questions
    q1 = QuestionBank(
        question_id=1,
        is_active=True,
        domain_id=domain.domain_id,
        role_id=role.role_id,
        experience_level=ExperienceLevel.senior,
        language=Language.vi,
        question_type=QuestionType.technical,
        question_text="Tell me how to scale a PostgreSQL database with high concurrency.",
        intent="Thiết kế kiến trúc Sharding và Read-Replica cho PostgreSQL khi chịu tải 50k RPS.",
        moderation_status=QuestionModerationStatus.approved,
        source=QuestionSource.admin_manual,
        difficulty=4,
    )
    q2 = QuestionBank(
        question_id=2,
        is_active=True,
        domain_id=domain.domain_id,
        role_id=role.role_id,
        experience_level=ExperienceLevel.senior,
        language=Language.vi,
        question_type=QuestionType.technical,
        question_text="Explain Kafka consumer rebalancing.",
        intent="Xử lý sự cố Consumer Rebalance Storm trong Apache Kafka.",
        moderation_status=QuestionModerationStatus.approved,
        source=QuestionSource.admin_manual,
        difficulty=5,
    )
    # Add 1 pending question (MUST NOT be sampled!)
    q_pending = QuestionBank(
        question_id=3,
        is_active=True,
        domain_id=domain.domain_id,
        role_id=role.role_id,
        experience_level=ExperienceLevel.senior,
        language=Language.vi,
        question_type=QuestionType.technical,
        question_text="Unapproved draft question.",
        intent="Draft pending intent.",
        moderation_status=QuestionModerationStatus.pending,
        source=QuestionSource.user_ai,
        difficulty=2,
    )
    session.add_all([q1, q2, q_pending])
    session.commit()

    yield session
    session.close()


def test_auto_random_samples_only_approved(db_session):
    intents = QuestionSelectionService.sample_questions_for_stage(
        session=db_session,
        session_id=999,
        stage_key="technical",
        source_mode="auto_random",
        target_count=2,
    )
    assert len(intents) == 2
    # Ensure pending question was NEVER selected
    sampled_ids = [ctx.question_id for ctx in intents]
    for ctx in intents:
        assert "Draft" not in ctx.intent
        assert ctx.difficulty in (4, 5)


def test_manual_mode_picks_exact_approved_questions(db_session):
    # Pick q1 by ID
    intents = QuestionSelectionService.sample_questions_for_stage(
        session=db_session,
        session_id=999,
        stage_key="technical",
        source_mode="manual",
        target_count=1,
        selected_question_ids=[1],
    )
    assert len(intents) == 1
    assert intents[0].question_id == 1
    assert "Sharding" in intents[0].intent


def test_reroll_question_replaces_with_new_approved_intent(db_session):
    new_intent = QuestionSelectionService.reroll_question(
        session=db_session,
        session_id=999,
        stage_key="technical",
        current_question_id=1,
    )
    assert new_intent is not None
    # Must pick the remaining approved question (ID 2), never the pending one
    assert new_intent.question_id == 2
    assert "Kafka" in new_intent.intent


def test_intent_composer_enforces_anti_verbatim_guardrail():
    ctx = QuestionIntentContext(
        question_id=10,
        intent="Xử lý dead-letter queue khi consumer xử lý thất bại.",
        stage_key="technical",
        difficulty=4,
        question_type="technical",
    )
    prompt = QuestionIntentComposer.build_situational_system_prompt(
        role="Backend Lead",
        level="Senior",
        stage_key="technical",
        intent_ctx=ctx,
        language="vi",
    )
    assert "TUYỆT ĐỐI KHÔNG ĐƯỢC đọc nguyên văn" in prompt
    assert "chuyển hóa ý định kiểm tra" in prompt
    assert "Xử lý dead-letter queue" in prompt
