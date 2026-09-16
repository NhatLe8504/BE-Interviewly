from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import pytest

from app.domain.errors import DomainValidationError
from app.domain.evaluation import (
    ActionableFeedback,
    RubricScores,
    SessionSummary,
    StarAnalysis,
    TurnEvaluation,
    determine_performance_rating,
)
from app.domain.interview import (
    InterviewSession,
    InterviewTurn,
    SessionStatus,
)
from app.domain.speech import (
    FillerWordRecord,
    SpeechQualityMetrics,
    WpmCalculation,
    WpmMetrics,
    assess_speaking_pace,
)


def test_interview_session_invariants() -> None:
    now = datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)
    session = InterviewSession(
        session_id=1,
        user_id=10,
        domain_id=1,
        role_id=2,
        level="junior",
        language="vi",
        mode="text",
        started_at=now,
    )
    assert session.is_active is True
    assert session.candidate_id == 10

    # Negative user_id
    with pytest.raises(DomainValidationError):
        InterviewSession(session_id=1, user_id=-1)

    # Invalid level
    with pytest.raises(DomainValidationError):
        InterviewSession(session_id=1, user_id=1, level="legendary")

    # Invalid status
    with pytest.raises(DomainValidationError):
        InterviewSession(session_id=1, user_id=1, status="unknown_status")

    # Complete session
    completed_at = datetime(2026, 9, 16, 12, 30, 0, tzinfo=timezone.utc)
    completed = session.mark_completed(total_score=Decimal("85.5"), completed_at=completed_at)
    assert completed.status == SessionStatus.completed.value
    assert completed.total_score == Decimal("85.5")
    assert completed.is_active is False

    # Cannot complete already completed session
    with pytest.raises(DomainValidationError):
        completed.mark_completed(total_score=Decimal("90"), completed_at=completed_at)

    # Abandon session
    abandoned = session.mark_abandoned()
    assert abandoned.status == SessionStatus.abandoned.value


def test_interview_turn_invariants() -> None:
    turn = InterviewTurn(
        turn_id=1,
        session_id=10,
        turn_number=1,
        question_text="Tell me about a challenging bug you fixed.",
    )
    assert turn.turn_number == 1
    assert turn.answer_text is None

    # Blank question
    with pytest.raises(DomainValidationError):
        InterviewTurn(turn_id=2, session_id=10, turn_number=2, question_text="   ")

    # Turn with answer
    answered = turn.with_answer("I investigated memory leaks using profiler.", duration_seconds=45.0)
    assert answered.answer_text == "I investigated memory leaks using profiler."
    assert answered.duration_seconds == 45.0

    # Blank answer rejected
    with pytest.raises(DomainValidationError):
        turn.with_answer("   ")


def test_rubric_scores_invariants_and_average() -> None:
    scores = RubricScores(clarity=80, structure=70, evidence=90)
    assert scores.clarity == 80.0
    assert scores.overall == 80.0

    # Score out of bounds (< 0 or > 100)
    with pytest.raises(DomainValidationError):
        RubricScores(clarity=105, structure=80, evidence=70)

    with pytest.raises(DomainValidationError):
        RubricScores(clarity=-5, structure=80, evidence=70)


def test_star_analysis_and_session_summary() -> None:
    star = StarAnalysis(situation=True, task=True, action=True, result=False)
    assert star.completeness_percentage == 75.0

    summary = SessionSummary(
        session_id=1,
        candidate_id=10,
        avg_clarity=85.0,
        avg_structure=80.0,
        avg_evidence=90.0,
        avg_overall=85.0,
        total_turns=3,
    )
    assert summary.performance_rating == "Excellent"


def test_wpm_calculation_and_speech_quality() -> None:
    calc = WpmCalculation(total_words=120, duration_seconds=60.0, pause_duration_seconds=10.0)
    # effective_time = 50s -> wpm = (120 / 50) * 60 = 144.0
    assert calc.calculate_effective_wpm() == 144.0

    # Pause exceeds duration
    with pytest.raises(DomainValidationError):
        WpmCalculation(total_words=50, duration_seconds=30.0, pause_duration_seconds=40.0)

    # Filler record
    filler = FillerWordRecord(word="ừm", count=5)
    assert filler.count == 5
    with pytest.raises(DomainValidationError):
        FillerWordRecord(word="   ", count=1)

    # Speech quality pace assessment
    assert assess_speaking_pace(140.0) == "Optimal"
    assert assess_speaking_pace(90.0) == "Too slow"
    assert assess_speaking_pace(180.0) == "Too fast"

    metrics = SpeechQualityMetrics(
        wpm_metrics=WpmMetrics(wpm=144.0, pause_duration=10.0, filler_count=2, filler_words=("ừm", "à")),
    )
    assert metrics.pace_assessment == "Optimal"
