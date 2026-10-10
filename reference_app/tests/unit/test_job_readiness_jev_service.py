"""Test luồng Jev trong UserSkillService: override, fallback, cache và nhãn engine."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from app.application.skills.estimator import SkillEstimateResult
from app.application.skills.service import UserSkillService
from app.infrastructure.llm.jev_adapter import JevReadinessResult, JevSkillRating
from app.infrastructure.persistence.models.user_skills import JobReadinessRecord


class _FakeJob:
    job_id = "job-1"
    title = "Backend Engineer"
    seniority = "middle"
    skills_required = ["python", "sql"]
    technologies = ["docker"]
    cleaned_jd_text = "Backend engineer with Python and SQL."


class _FakeJevAdapter:
    def __init__(self, result=None):
        self.result = result
        self.calls = 0
        self.last_args = None

    def is_available(self):
        return True

    def evaluate_readiness(self, **kwargs):
        self.calls += 1
        self.last_args = kwargs
        return self.result


def _estimate(skill_id: str, level: str, confidence: float, ability: float) -> SkillEstimateResult:
    return SkillEstimateResult(
        skill_id=skill_id,
        ability_score=ability,
        level=level,
        confidence=confidence,
        evidence_count=3,
        max_difficulty_passed=3,
        last_evidence_at=None,
    )


USER_SKILLS = {
    "python": _estimate("python", "junior", 0.7, 2.2),
    "sql": _estimate("sql", "senior", 0.9, 4.0),
}


def _service(result, user_skills=None, cached=None):
    session = MagicMock()
    session.get.return_value = _FakeJob()
    session.scalars.return_value.first.return_value = cached
    adapter = _FakeJevAdapter(result)
    svc = UserSkillService(session=session, jev_adapter=adapter)
    svc.get_user_skills_dict = MagicMock(return_value=user_skills if user_skills is not None else USER_SKILLS)
    return svc, session, adapter


def _jev_result() -> JevReadinessResult:
    return JevReadinessResult(
        match_percent=61,
        verdict="almost",
        confidence=0.77,
        recommended_skills=["python"],
        skill_ratings={
            "python": JevSkillRating("python", 1.4, 0.8, "gap", 1),
            "sql": JevSkillRating("sql", 4.0, 0.9, "met", 4),
        },
        explanation="Interviewly AI đánh giá 61%.",
        model="jev-latest",
    )


def test_jev_result_overrides_assessment_and_is_persisted():
    svc, session, adapter = _service(_jev_result())

    assessment = svc.evaluate_job_readiness(user_id=27, job_id="job-1")

    assert adapter.calls == 1
    # Adapter phải nhận tên kỹ năng (không chỉ id) để soạn giải thích/instructions.
    assert adapter.last_args["requirements"][0]["name"] == "Python"
    assert adapter.last_args["candidate_skills"]["python"]["level"] == "junior"

    assert assessment.analysis_engine == "jev"
    assert assessment.match_percent == 61
    assert assessment.verdict == "almost"
    assert assessment.explanation == "Interviewly AI đánh giá 61%."

    python_item = next(item for item in assessment.requirements if item.skill_id == "python")
    sql_item = next(item for item in assessment.requirements if item.skill_id == "sql")
    # Heuristic: python junior < middle -> partial; Jev hạ tiếp xuống gap.
    assert python_item.status == "gap"
    # Heuristic: sql senior >= middle -> met; Jev met, không thay đổi.
    assert sql_item.status == "met"

    # Jev đề xuất python; heuristic bổ sung docker (chưa có bằng chứng).
    assert assessment.recommended_skills == ["python", "docker"]

    record = session.add.call_args[0][0]
    assert isinstance(record, JobReadinessRecord)
    assert record.analysis_engine == "jev"
    assert record.match_percent == 61
    session.commit.assert_called_once()


def test_jev_failure_falls_back_to_heuristic():
    svc, session, adapter = _service(None)

    assessment = svc.evaluate_job_readiness(user_id=27, job_id="job-1")

    assert adapter.calls == 1
    assert assessment.analysis_engine == "heuristic"
    record = session.add.call_args[0][0]
    assert record.analysis_engine == "heuristic"


def test_fresh_cache_returns_without_calling_jev():
    cached = JobReadinessRecord(
        user_id=27,
        job_id="job-1",
        match_percent=80,
        verdict="ready",
        data_coverage=Decimal("0.8"),
        requirements_breakdown=[
            {
                "skill_id": "python",
                "name": "Python",
                "importance": "must",
                "required_level": "middle",
                "required_level_num": 3,
                "user_level": "middle",
                "user_level_num": 3,
                "status": "met",
                "confidence": 0.9,
                "level_assumed": False,
            }
        ],
        explanation="Kết quả đã lưu.",
        recommended_skills=[],
        analysis_engine="jev",
        computed_at=datetime.now(timezone.utc),
    )
    svc, session, adapter = _service(_jev_result(), cached=cached)

    assessment = svc.evaluate_job_readiness(user_id=27, job_id="job-1")

    assert adapter.calls == 0
    assert assessment.analysis_engine == "jev"
    assert assessment.match_percent == 80
    session.add.assert_not_called()


def test_cached_record_without_engine_label_is_heuristic():
    cached = JobReadinessRecord(
        user_id=27,
        job_id="job-1",
        match_percent=55,
        verdict="almost",
        data_coverage=Decimal("0.5"),
        requirements_breakdown=[],
        explanation="Kết quả cũ.",
        recommended_skills=[],
        analysis_engine=None,
        computed_at=datetime.now(timezone.utc),
    )
    svc, session, adapter = _service(_jev_result(), cached=cached)

    assessment = svc.evaluate_job_readiness(user_id=27, job_id="job-1")

    assert adapter.calls == 0
    assert assessment.analysis_engine == "heuristic"
