from decimal import Decimal
import json
from unittest.mock import MagicMock

import pytest

from app.application.skills.service import UserSkillService
from app.infrastructure.persistence.models.catalog import PracticeHistoryRecord, QuestionBank
from app.infrastructure.persistence.models.user_skills import PracticeEvaluationRecord
from app.presentation.api.routers.catalog import verified_quiz_score

ANSWER = "Tôi dùng EXPLAIN ANALYZE để tìm nguyên nhân và thêm composite index cho bảng đơn hàng."


def _history_record(**overrides):
    defaults = dict(
        history_id=1,
        user_id=27,
        session_title="Test Practice",
        source_type="set",
        source_id="1",
        total_questions=1,
        evaluated_count=1,
        average_score=Decimal("80.00"),
        duration_seconds=120,
    )
    defaults.update(overrides)
    return PracticeHistoryRecord(**defaults)


def _evaluation(rec_id, user_id, question_id, part, score, max_score, answer=ANSWER):
    return PracticeEvaluationRecord(
        id=rec_id,
        user_id=user_id,
        question_id=question_id,
        part=part,
        part_score=Decimal(str(score)),
        part_max=Decimal(str(max_score)),
        answer_text=answer,
        method="llm",
    )


def _service(session):
    svc = UserSkillService(session=session)
    svc.record_evidence = MagicMock()
    svc.recalculate_user_skills = MagicMock()
    return svc


def _question(skill_ids):
    return QuestionBank(
        question_id=20,
        domain_id=1,
        question_text="Bạn tối ưu slow query như thế nào?",
        difficulty=3,
        skill_ids=skill_ids,
    )


# ---------------------------------------------------------------------------
# Practice evidence: chỉ tin đánh giá do server lưu
# ---------------------------------------------------------------------------

def test_client_score_is_never_used_without_server_evaluation():
    session = MagicMock()
    session.get.return_value = _question(["sql"])

    record = _history_record(
        questions_summary=json.dumps([{"question_id": 20, "score": 100, "passed": True}]),
    )
    svc = _service(session)

    assert svc.sync_from_practice_history_record(record) == 0
    svc.record_evidence.assert_not_called()


def test_client_score_is_ignored_even_when_evaluation_ids_exist():
    session = MagicMock()
    session.get.return_value = _question(["sql", "postgresql"])
    session.scalars.return_value.all.return_value = [
        _evaluation(501, 27, 20, "content", 28.0, 35.0),
        _evaluation(502, 27, 20, "voice", 40.0, 50.0),
    ]
    record = _history_record(
        history_id=2,
        questions_summary=json.dumps([
            {"question_id": 20, "score": 1, "passed": True, "evaluation_ids": [501, 502]},
        ]),
    )
    svc = _service(session)

    recorded = svc.sync_from_practice_history_record(record)

    assert recorded == 2
    kwargs = svc.record_evidence.call_args_list[0].kwargs
    # (28 + 40) / (35 + 50) = 0.8, không phải score=1 của client (trước đây thành 100%)
    assert kwargs["score"] == pytest.approx(0.8)
    assert kwargs["evidence_quote"] == ANSWER
    assert kwargs["input_mode"] == "mixed"
    assert kwargs["source_id"] == "hist_2_q_20"
    assert kwargs["grader_confidence"] == pytest.approx(0.9)
    recorded_skills = {call.kwargs["skill_id"] for call in svc.record_evidence.call_args_list}
    assert recorded_skills == {"sql", "postgresql"}


def test_evaluation_of_another_user_is_rejected():
    session = MagicMock()
    session.get.return_value = _question(["sql"])
    session.scalars.return_value.all.return_value = [
        _evaluation(501, 999, 20, "content", 35.0, 35.0),
    ]
    record = _history_record(
        questions_summary=json.dumps([{"question_id": 20, "evaluation_ids": [501]}]),
    )
    svc = _service(session)

    assert svc.sync_from_practice_history_record(record) == 0
    svc.record_evidence.assert_not_called()


def test_evaluation_of_another_question_is_rejected():
    session = MagicMock()
    session.get.return_value = _question(["sql"])
    session.scalars.return_value.all.return_value = [
        _evaluation(501, 27, 99, "content", 35.0, 35.0),
    ]
    record = _history_record(
        questions_summary=json.dumps([{"question_id": 20, "evaluation_ids": [501]}]),
    )
    svc = _service(session)

    assert svc.sync_from_practice_history_record(record) == 0
    svc.record_evidence.assert_not_called()


def test_compose_normalizes_one_out_of_hundred_as_one_percent():
    rows = [_evaluation(1, 27, 20, "content", 1.0, 100.0)]
    composed = UserSkillService._compose_verified_practice_evidence(rows)
    assert composed is not None
    assert composed[0] == pytest.approx(0.01)


def test_compose_requires_real_answer_text():
    rows = [_evaluation(1, 27, 20, "content", 30.0, 35.0, answer="   ")]
    assert UserSkillService._compose_verified_practice_evidence(rows) is None


def test_record_evidence_commits_instead_of_only_flushing():
    session = MagicMock()
    session.scalars.return_value.first.return_value = None
    svc = UserSkillService(session=session)

    svc.record_evidence(
        user_id=27,
        skill_id="sql",
        source_type="practice_history",
        source_id="commit-check",
        score=0.8,
    )

    assert session.flush.called
    session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# Interview evidence: turn 'ai' có câu trả lời + evaluation + question_id
# ---------------------------------------------------------------------------

def _interview_session_with_turn(*, answer, question_id, overall_score, audio_url=None):
    turn = MagicMock()
    turn.turn_id = 5
    turn.transcribed_text = answer
    turn.question_id = question_id
    turn.audio_url = audio_url
    turn.evaluation.overall_score = overall_score

    session_rec = MagicMock()
    session_rec.candidate_id = 27
    session_rec.turns = [turn]
    return session_rec


def test_interview_sync_accepts_answered_ai_turn():
    session = MagicMock()
    session_rec = _interview_session_with_turn(answer=ANSWER, question_id=20, overall_score=Decimal("8.0"))
    session.get.side_effect = lambda model, key: session_rec if key == 99 else _question(["sql"])
    svc = _service(session)

    recorded = svc.sync_from_interview_session(99)

    assert recorded == 1
    kwargs = svc.record_evidence.call_args_list[0].kwargs
    assert kwargs["score"] == pytest.approx(0.8)
    assert kwargs["evidence_quote"] == ANSWER
    assert kwargs["input_mode"] == "text"


def test_interview_sync_skips_turn_without_evaluation():
    session = MagicMock()
    session_rec = _interview_session_with_turn(answer=ANSWER, question_id=20, overall_score=None)
    session.get.side_effect = lambda model, key: session_rec if key == 99 else _question(["sql"])
    svc = _service(session)

    assert svc.sync_from_interview_session(99) == 0
    svc.record_evidence.assert_not_called()


def test_interview_sync_skips_empty_answer():
    session = MagicMock()
    session_rec = _interview_session_with_turn(answer="   ", question_id=20, overall_score=Decimal("8.0"))
    session.get.side_effect = lambda model, key: session_rec if key == 99 else _question(["sql"])
    svc = _service(session)

    assert svc.sync_from_interview_session(99) == 0
    svc.record_evidence.assert_not_called()


def test_interview_sync_skips_unlinked_question():
    session = MagicMock()
    session_rec = _interview_session_with_turn(answer=ANSWER, question_id=None, overall_score=Decimal("8.0"))
    session.get.side_effect = lambda model, key: session_rec if key == 99 else _question(["sql"])
    svc = _service(session)

    assert svc.sync_from_interview_session(99) == 0
    svc.record_evidence.assert_not_called()


def test_interview_sync_voice_mode_when_audio_present():
    session = MagicMock()
    session_rec = _interview_session_with_turn(
        answer=ANSWER, question_id=20, overall_score=Decimal("8.0"), audio_url="https://cdn/x.webm",
    )
    session.get.side_effect = lambda model, key: session_rec if key == 99 else _question(["sql"])
    svc = _service(session)

    assert svc.sync_from_interview_session(99) == 1
    assert svc.record_evidence.call_args_list[0].kwargs["input_mode"] == "voice"


# ---------------------------------------------------------------------------
# Quiz: điểm trắc nghiệm phải xác minh từ quiz_data, không tin client
# ---------------------------------------------------------------------------

def test_quiz_score_only_accepts_server_verified_answer():
    quiz = {"options": [{"id": "A", "is_correct": False}, {"id": "B", "is_correct": True}]}
    assert verified_quiz_score(quiz, "B") == 15.0
    assert verified_quiz_score(quiz, "A") == 0.0
    assert verified_quiz_score(quiz, "C") == 0.0
    assert verified_quiz_score(quiz, None) == 0.0
    assert verified_quiz_score(None, "B") == 0.0
    assert verified_quiz_score({"options": []}, "B") == 0.0
