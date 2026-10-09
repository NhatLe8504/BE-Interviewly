from datetime import datetime, timezone, timedelta
from app.application.skills.estimator import (
    EvidenceInput,
    SkillLevelEstimator,
)


def test_estimator_no_evidence():
    result = SkillLevelEstimator.estimate_skill("java", [])
    assert result.level == "none"
    assert result.confidence == 0.0
    assert result.evidence_count == 0


def test_estimator_single_evidence():
    now = datetime.now(timezone.utc)
    ev = EvidenceInput(
        skill_id="java",
        score=0.9,
        difficulty=3,
        grader_confidence=0.85,
        source_type="interview_turn",
        created_at=now,
    )
    result = SkillLevelEstimator.estimate_skill("java", [ev], now=now)
    # With only 1 evidence, confidence is low and level should remain "none" to prevent premature guessing
    assert result.level == "none"
    assert result.evidence_count == 1


def test_estimator_consistent_performance():
    now = datetime.now(timezone.utc)
    evidences = [
        EvidenceInput(
            skill_id="java",
            score=0.85,
            difficulty=3,
            grader_confidence=0.9,
            source_type="interview_turn",
            created_at=now - timedelta(days=i * 2),
        )
        for i in range(5)
    ]
    result = SkillLevelEstimator.estimate_skill("java", evidences, now=now)
    assert result.level in ("middle", "senior")
    assert result.confidence >= 0.60
    assert result.max_difficulty_passed == 3


def test_estimator_difficulty_ceiling():
    now = datetime.now(timezone.utc)
    # High scores but only on difficulty 1 (basic)
    evidences = [
        EvidenceInput(
            skill_id="python",
            score=1.0,
            difficulty=1,
            grader_confidence=0.95,
            source_type="interview_turn",
            created_at=now - timedelta(days=i),
        )
        for i in range(8)
    ]
    result = SkillLevelEstimator.estimate_skill("python", evidences, now=now)
    # Should NOT be allowed to be Senior or Middle without passing difficulty 2 or 3
    assert result.level in ("junior", "beginner")
    assert result.ability_score < 2.0


def test_career_profile_detection():
    now = datetime.now(timezone.utc)
    java_evs = [
        EvidenceInput("java", 0.85, 3, 0.9, "interview_turn", now - timedelta(days=1)),
        EvidenceInput("java", 0.80, 3, 0.9, "interview_turn", now - timedelta(days=2)),
    ]
    spring_evs = [
        EvidenceInput("spring-boot", 0.90, 3, 0.9, "interview_turn", now - timedelta(days=1)),
        EvidenceInput("spring-boot", 0.85, 3, 0.9, "interview_turn", now - timedelta(days=2)),
    ]
    res_java = SkillLevelEstimator.estimate_skill("java", java_evs, now=now)
    res_spring = SkillLevelEstimator.estimate_skill("spring-boot", spring_evs, now=now)

    profile = SkillLevelEstimator.estimate_career_profile([res_java, res_spring])
    assert profile.primary_role_track == "backend"
    assert profile.overall_level in ("middle", "senior", "junior")
    assert len(profile.top_skills) >= 2

def test_zero_confidence_evidence_cannot_build_confidence():
    """LOI #7: 100 bằng chứng cũ với grader_confidence=0 không được cho ra confidence 0.76."""
    now = datetime.now(timezone.utc)
    evidences = [
        EvidenceInput(
            skill_id="java",
            score=0.9,
            difficulty=3,
            grader_confidence=0.0,
            source_type="practice_history",
            created_at=now - timedelta(days=3650),
        )
        for _ in range(100)
    ]
    result = SkillLevelEstimator.estimate_skill("java", evidences, now=now)
    assert result.confidence == 0.0
    assert result.level == "none"


def test_generic_skill_does_not_decide_role_track():
    """LOI #7: chỉ có Communication thì không được suy ra Backend/Senior."""
    now = datetime.now(timezone.utc)
    evidences = [
        EvidenceInput("communication", 0.9, 3, 0.9, "interview_turn", now - timedelta(days=1)),
        EvidenceInput("communication", 0.85, 3, 0.9, "interview_turn", now - timedelta(days=2)),
    ]
    estimate = SkillLevelEstimator.estimate_skill("communication", evidences, now=now)
    assert estimate.level != "none"

    profile = SkillLevelEstimator.estimate_career_profile([estimate])
    assert profile.primary_role_track is None
    assert profile.secondary_role_track is None
    assert profile.role_confidence == 0.0
    assert profile.overall_level == "none"


def test_specific_skill_still_decides_role_track():
    """Positive control: kỹ năng chuyên biệt vẫn phải xác định đúng track."""
    now = datetime.now(timezone.utc)
    java_evs = [
        EvidenceInput("java", 0.85, 3, 0.9, "interview_turn", now - timedelta(days=1)),
        EvidenceInput("java", 0.80, 3, 0.9, "interview_turn", now - timedelta(days=2)),
    ]
    comm_evs = [
        EvidenceInput("communication", 0.9, 3, 0.9, "interview_turn", now - timedelta(days=1)),
    ]
    estimates = [
        SkillLevelEstimator.estimate_skill("java", java_evs, now=now),
        SkillLevelEstimator.estimate_skill("communication", comm_evs, now=now),
    ]
    profile = SkillLevelEstimator.estimate_career_profile(estimates)
    assert profile.primary_role_track == "backend"
