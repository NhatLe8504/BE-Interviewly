from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CandidateKpiStatsOut(BaseSchema):
    total_interviews: int = Field(..., description="Tổng số phiên phỏng vấn đã tham gia")
    completed_interviews: int = Field(..., description="Số phiên hoàn thành")
    avg_score: float = Field(..., description="Điểm trung bình (thang 100)")
    total_practice_minutes: int = Field(..., description="Tổng thời gian luyện tập tích lũy (phút)")
    streak_days: int = Field(..., description="Số ngày luyện tập liên tục (Streak)")


class SkillRadarOut(BaseSchema):
    clarity: float = Field(..., description="Độ rõ ràng & Mạch lạc (0-100)")
    logic: float = Field(..., description="Cấu trúc logic (0-100)")
    evidence: float = Field(..., description="Dẫn chứng thực tế (0-100)")
    delivery: float = Field(..., description="Phong thái & Giọng điệu (0-100)")
    star_method: float = Field(..., description="Phương pháp STAR (0-100)")


class RecentSessionOut(BaseSchema):
    session_id: int
    domain_name: str
    role_name: str
    mode: str
    score: float | None
    status: str
    started_at: datetime


class WeakPointRecommendationOut(BaseSchema):
    weak_area: str
    score: float
    recommendation: str
    suggested_question: str


class CandidateDashboardOut(BaseSchema):
    candidate_id: int
    kpi: CandidateKpiStatsOut
    skill_radar: SkillRadarOut
    recent_sessions: list[RecentSessionOut]
    recommendations: list[WeakPointRecommendationOut]


class ProgressTrendPointOut(BaseSchema):
    session_id: int
    date: str
    overall_score: float
    clarity_score: float
    logic_score: float
    example_score: float
    speaking_pace_wpm: float | None
    filler_words_count: int
    star_completion_rate: float


class ProgressTrendsOut(BaseSchema):
    candidate_id: int
    trends: list[ProgressTrendPointOut]
    avg_wpm: float
    avg_filler_count: float
    star_mastery_rate: float


class HistorySessionItemOut(BaseSchema):
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


class HistoryPageOut(BaseSchema):
    items: list[HistorySessionItemOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class TurnDetailOut(BaseSchema):
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


class SessionDetailOut(BaseSchema):
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
    turns: list[TurnDetailOut]
    avg_clarity: float | None
    avg_logic: float | None
    avg_example: float | None


class SessionResultOut(BaseSchema):
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
    turns: list[TurnDetailOut]
