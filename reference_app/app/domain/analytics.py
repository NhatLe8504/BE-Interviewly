from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CandidateKpiStats:
    total_interviews: int
    completed_interviews: int
    avg_score: float
    total_practice_minutes: int
    streak_days: int

    def __post_init__(self) -> None:
        if self.total_interviews < 0:
            raise ValueError("total_interviews cannot be negative")
        if self.completed_interviews < 0:
            raise ValueError("completed_interviews cannot be negative")
        if self.avg_score < 0 or self.avg_score > 100:
            raise ValueError("avg_score must be between 0 and 100")
        if self.total_practice_minutes < 0:
            raise ValueError("total_practice_minutes cannot be negative")
        if self.streak_days < 0:
            raise ValueError("streak_days cannot be negative")


@dataclass(frozen=True)
class SkillRadarScore:
    clarity: float
    logic: float
    evidence: float
    delivery: float
    star_method: float

    def __post_init__(self) -> None:
        for name, val in (
            ("clarity", self.clarity),
            ("logic", self.logic),
            ("evidence", self.evidence),
            ("delivery", self.delivery),
            ("star_method", self.star_method),
        ):
            if val < 0 or val > 100:
                raise ValueError(f"{name} must be between 0 and 100")


@dataclass(frozen=True)
class RecentSessionSummary:
    session_id: int
    domain_name: str
    role_name: str
    mode: str
    score: float | None
    status: str
    started_at: datetime


@dataclass(frozen=True)
class WeakPointRecommendation:
    weak_area: str
    score: float
    recommendation: str
    suggested_question: str


@dataclass(frozen=True)
class CandidateDashboard:
    candidate_id: int
    kpi: CandidateKpiStats
    skill_radar: SkillRadarScore
    recent_sessions: list[RecentSessionSummary]
    recommendations: list[WeakPointRecommendation]


@dataclass(frozen=True)
class ProgressTrendPoint:
    session_id: int
    date: str
    overall_score: float
    clarity_score: float
    logic_score: float
    example_score: float
    speaking_pace_wpm: float | None
    filler_words_count: int
    star_completion_rate: float


@dataclass(frozen=True)
class ProgressTrends:
    candidate_id: int
    trends: list[ProgressTrendPoint]
    avg_wpm: float
    avg_filler_count: float
    star_mastery_rate: float


@dataclass(frozen=True)
class HistorySessionItem:
    session_id: int
    candidate_id: int
    domain_id: int | None
    domain_name: str | None
    role_id: int | None
    role_name: str | None
    experience_level: str | None
    language: str
    mode: str
    status: str
    total_score: float | None
    started_at: datetime
    completed_at: datetime | None
    total_turns: int


@dataclass(frozen=True)
class TurnDetailItem:
    turn_id: int
    turn_number: int
    speaker: str
    question_id: int | None
    message_text: str | None
    audio_url: str | None
    transcribed_text: str | None
    clarity_score: float | None
    logic_score: float | None
    example_score: float | None
    overall_score: float | None
    feedback_text: str | None
    speaking_pace: float | None
    hesitation_count: int
    filler_word_count: int
    tips_text: str | None
    created_at: datetime


@dataclass(frozen=True)
class SessionDetail:
    session_id: int
    candidate_id: int
    domain_name: str | None
    role_name: str | None
    experience_level: str | None
    language: str
    mode: str
    status: str
    total_score: float | None
    started_at: datetime
    completed_at: datetime | None
    turns: list[TurnDetailItem]
    avg_clarity: float | None
    avg_logic: float | None
    avg_example: float | None


@dataclass(frozen=True)
class SessionResultReport:
    session_id: int
    candidate_id: int
    status: str
    total_score: float
    readiness_badge: str
    clarity_score: float
    structure_score: float
    evidence_score: float
    speaking_pace_wpm: float
    pace_rating: str
    filler_count: int
    filler_words: list[str]
    pause_duration: float
    star_analysis: dict[str, bool]
    turns: list[TurnDetailItem]
    total_turns: int = 0
    performance_rating: str = ""
