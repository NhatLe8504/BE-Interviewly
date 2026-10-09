"""Hồi quy lỗi P1-1: dữ liệu tracking phải sống sót sau khi session đóng.

Test này chạy trên PostgreSQL thật (cùng DB cấu hình cho app) và tự dọn dẹp.
Nếu DB không khả dụng thì skip để không làm đỏ CI.
"""
from __future__ import annotations

import random

import pytest
from sqlalchemy import delete, select

from app.application.skills.service import UserSkillService
from app.config import Settings
from app.infrastructure.database import create_engine_from_url
from app.infrastructure.orm import Base, create_session_factory
from app.infrastructure.persistence.models.user import User
from app.infrastructure.persistence.models.user_skills import (
    UserCareerProfileRecord,
    UserSkillEvidenceRecord,
    UserSkillLevelRecord,
)


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


def test_skill_writes_survive_session_close(pg_session_factory):
    user_id = random.randint(8_000_000_000, 8_999_999_999)
    source_id = f"it-commit-{user_id}"

    setup = pg_session_factory()
    try:
        setup.add(User(
            user_id=user_id,
            full_name="Skill Persistence Test",
            email=f"skill-persistence-{user_id}@example.com",
            password_hash="not-used",
        ))
        setup.commit()
    finally:
        setup.close()

    try:
        session = pg_session_factory()
        try:
            svc = UserSkillService(session=session)
            svc.record_evidence(
                user_id=user_id,
                skill_id="sql",
                source_type="practice_history",
                source_id=source_id,
                score=0.8,
                question_difficulty=3,
                grader_confidence=0.8,
                evidence_quote="Câu trả lời kiểm thử",
            )
            svc.recalculate_user_skills(user_id)
        finally:
            session.close()

        verify = pg_session_factory()
        try:
            evidence = verify.scalars(
                select(UserSkillEvidenceRecord).where(UserSkillEvidenceRecord.user_id == user_id),
            ).all()
            levels = verify.scalars(
                select(UserSkillLevelRecord).where(UserSkillLevelRecord.user_id == user_id),
            ).all()
            profile = verify.get(UserCareerProfileRecord, user_id)

            assert len(evidence) == 1, "evidence bị rollback khi session đóng"
            assert len(levels) == 1, "skill level bị rollback khi session đóng"
            assert profile is not None, "career profile bị rollback khi session đóng"
            assert float(evidence[0].score) == pytest.approx(0.8)
        finally:
            verify.close()
    finally:
        cleanup = pg_session_factory()
        try:
            cleanup.execute(delete(User).where(User.user_id == user_id))
            cleanup.commit()
        finally:
            cleanup.close()


def test_positive_control_flush_only_is_rolled_back(pg_session_factory):
    """Chứng minh test harness phát hiện được đúng lớp lỗi P1-1.

    Ghi evidence rồi chỉ flush/close (không commit) -> phải KHÔNG còn dữ liệu.
    Nếu test này fail nghĩa là cách kiểm chứng đang sai, không phải code đúng.
    """
    user_id = random.randint(8_000_000_000, 8_999_999_999)

    setup = pg_session_factory()
    try:
        setup.add(User(
            user_id=user_id,
            full_name="Skill Persistence Control",
            email=f"skill-control-{user_id}@example.com",
            password_hash="not-used",
        ))
        setup.commit()
    finally:
        setup.close()

    try:
        session = pg_session_factory()
        try:
            session.add(UserSkillEvidenceRecord(
                user_id=user_id,
                skill_id="sql",
                source_type="practice_history",
                source_id=f"it-control-{user_id}",
                question_difficulty=3,
                score=0.8,
                grader_confidence=0.8,
                evidence_quote="flush only",
            ))
            session.flush()
        finally:
            session.close()

        verify = pg_session_factory()
        try:
            rows = verify.scalars(
                select(UserSkillEvidenceRecord).where(UserSkillEvidenceRecord.user_id == user_id),
            ).all()
            assert rows == []
        finally:
            verify.close()
    finally:
        cleanup = pg_session_factory()
        try:
            cleanup.execute(delete(User).where(User.user_id == user_id))
            cleanup.commit()
        finally:
            cleanup.close()


def test_practice_evidence_comes_from_server_evaluation_not_client_score(pg_session_factory):
    """P1-3 + P1-4: client gửi score=100 nhưng evidence phải lấy điểm server đã chấm."""
    import json

    from app.infrastructure.persistence.models.catalog import PracticeHistoryRecord, QuestionBank
    from app.infrastructure.persistence.practice_evaluation_repository import save_practice_evaluation

    lookup = pg_session_factory()
    try:
        question = None
        for candidate in lookup.scalars(select(QuestionBank).limit(100)).all():
            if candidate.skill_ids:
                question = candidate
                break
        if question is None:
            pytest.skip("Không có câu hỏi nào được gắn skill_ids trong DB để kiểm thử")
        question_id = int(question.question_id)
        skill_ids = list(question.skill_ids)
    finally:
        lookup.close()

    user_id = random.randint(8_000_000_000, 8_999_999_999)
    answer = "Tôi dùng EXPLAIN ANALYZE, thêm composite index và cache kết quả truy vấn nặng."

    setup = pg_session_factory()
    try:
        setup.add(User(
            user_id=user_id,
            full_name="Skill Evidence Test",
            email=f"skill-evidence-{user_id}@example.com",
            password_hash="not-used",
        ))
        setup.commit()
    finally:
        setup.close()

    try:
        session = pg_session_factory()
        try:
            content = save_practice_evaluation(
                session,
                user_id=user_id,
                question_id=question_id,
                part="content",
                part_score=28.0,
                part_max=35.0,
                answer_text=answer,
            )
            voice = save_practice_evaluation(
                session,
                user_id=user_id,
                question_id=question_id,
                part="voice",
                part_score=40.0,
                part_max=50.0,
                answer_text=answer,
            )
            history = PracticeHistoryRecord(
                user_id=user_id,
                session_title="Integration evidence test",
                source_type="set",
                total_questions=2,
                evaluated_count=2,
                average_score=100.0,
                duration_seconds=60,
                questions_summary=json.dumps([
                    {
                        "question_id": question_id,
                        "score": 100,  # client tự khai, phải bị bỏ qua
                        "evaluation_ids": [int(content.id), int(voice.id)],
                    },
                    {
                        "question_id": question_id,
                        "score": 100,  # không có evaluation_ids -> không được ghi evidence
                    },
                ]),
            )
            session.add(history)
            session.commit()

            svc = UserSkillService(session=session)
            recorded = svc.sync_from_practice_history_record(history)
        finally:
            session.close()

        # Chỉ item có evaluation_ids được ghi, nhân với số skill của câu hỏi.
        assert recorded == len(skill_ids)

        verify = pg_session_factory()
        try:
            evidence = verify.scalars(
                select(UserSkillEvidenceRecord).where(UserSkillEvidenceRecord.user_id == user_id),
            ).all()
            assert len(evidence) == len(skill_ids)
            assert {row.skill_id for row in evidence} == set(skill_ids)
            for row in evidence:
                # (28 + 40) / (35 + 50) = 0.8, KHÔNG phải 100/100 = 1.0
                assert float(row.score) == pytest.approx(0.8)
                assert row.evidence_quote == answer
                assert row.source_type == "practice_history"
        finally:
            verify.close()
    finally:
        cleanup = pg_session_factory()
        try:
            cleanup.execute(delete(User).where(User.user_id == user_id))
            cleanup.commit()
        finally:
            cleanup.close()
