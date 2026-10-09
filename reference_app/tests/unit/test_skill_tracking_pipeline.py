from datetime import datetime, timezone
from decimal import Decimal
import json
from unittest.mock import MagicMock
import pytest

from app.application.skills.service import UserSkillService
from app.infrastructure.persistence.models.catalog import PracticeHistoryRecord, QuestionBank
from app.infrastructure.persistence.models.user_skills import UserSkillEvidenceRecord, UserSkillLevelRecord


def test_sync_practice_history_record_untagged_no_guess():
    session = MagicMock()
    # Mock QuestionBank item with empty skill_ids
    qb_untagged = QuestionBank(
        question_id=101,
        domain_id=1,
        question_text="Phân biệt sự khác nhau giữa SQL và NoSQL database? Khi nào bạn nên chọn MongoDB thay vì PostgreSQL?",
        skill_ids=[],
    )
    session.get.return_value = qb_untagged

    history_record = PracticeHistoryRecord(
        history_id=1,
        user_id=27,
        session_title="Test Practice",
        source_type="set",
        source_id="1",
        total_questions=1,
        evaluated_count=1,
        average_score=Decimal("80.00"),
        duration_seconds=120,
        questions_summary=json.dumps([{"question_id": 101, "score": 80, "passed": True}]),
    )

    svc = UserSkillService(session=session)
    # Mock record_evidence
    svc.record_evidence = MagicMock()
    svc.recalculate_user_skills = MagicMock()

    recorded = svc.sync_from_practice_history_record(history_record)
    assert recorded == 0
    assert svc.record_evidence.call_count == 0


def test_sync_practice_history_record_tagged_records_evidence():
    session = MagicMock()
    # Mock QuestionBank item with tagged skill_ids
    qb_tagged = QuestionBank(
        question_id=20,
        domain_id=1,
        question_text="Bạn tiếp cận và tối ưu hóa một câu lệnh truy vấn cơ sở dữ liệu bị chậm (slow query) đang làm nghẽn API như thế nào?",
        difficulty=3,
        skill_ids=["sql", "postgresql"],
    )
    session.get.return_value = qb_tagged

    history_record = PracticeHistoryRecord(
        history_id=2,
        user_id=27,
        session_title="SQL Practice",
        source_type="set",
        source_id="1",
        total_questions=1,
        evaluated_count=1,
        average_score=Decimal("85.00"),
        duration_seconds=90,
        questions_summary=json.dumps([{"question_id": 20, "score": 85, "passed": True}]),
    )

    svc = UserSkillService(session=session)
    svc.record_evidence = MagicMock()
    svc.recalculate_user_skills = MagicMock()

    recorded = svc.sync_from_practice_history_record(history_record)
    assert recorded == 2
    assert svc.record_evidence.call_count == 2
    # Check that it called with normalized skill IDs
    calls = svc.record_evidence.call_args_list
    recorded_skills = {c.kwargs["skill_id"] for c in calls}
    assert "sql" in recorded_skills
    assert "postgresql" in recorded_skills
    svc.recalculate_user_skills.assert_called_once_with(27)
