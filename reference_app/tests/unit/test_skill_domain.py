from datetime import datetime, timezone
import pytest

from app.domain.errors import DomainValidationError
from app.domain.skills import CareerProfile, SkillEstimate, SkillEvidenceEvent


def test_skill_evidence_event_valid():
    event = SkillEvidenceEvent(
        user_id=1,
        skill_id="postgresql",
        source_type="interview_session",
        source_id="session_42_turn_3",
        score=0.85,
        question_difficulty=3,
        grader_confidence=0.9,
        evidence_quote="I indexed foreign keys and analyzed query plans with EXPLAIN ANALYZE.",
        input_mode="voice",
        rubric_scores={"clarity": 8.5, "logic": 8.0, "example": 9.0},
    )
    assert event.user_id == 1
    assert event.skill_id == "postgresql"
    assert event.score == 0.85
    assert event.question_difficulty == 3
    assert event.input_mode == "voice"


def test_skill_evidence_event_invalid_score():
    with pytest.raises(DomainValidationError):
        SkillEvidenceEvent(
            user_id=1,
            skill_id="postgresql",
            source_type="interview_session",
            source_id="s1",
            score=1.5,
        )


def test_skill_evidence_event_invalid_source():
    with pytest.raises(DomainValidationError):
        SkillEvidenceEvent(
            user_id=1,
            skill_id="postgresql",
            source_type="unknown_source",
            source_id="s1",
            score=0.5,
        )


def test_career_profile_nullable_track():
    profile = CareerProfile(
        user_id=27,
        primary_role_track=None,
        secondary_role_track=None,
        role_confidence=0.0,
        overall_level="none",
        top_skills=[],
        weak_skills=[],
    )
    assert profile.primary_role_track is None
    assert profile.overall_level == "none"
