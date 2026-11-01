from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CandidateKpiStatsOut(BaseSchema):
    total_interviews: int = Field(..., description="Tổng số phiên phỏng vấn đã tham gia")
    completed_interviews: int = Field(..., description="Số phiên hoàn thành")
    avg_score: float | None = Field(..., description="Điểm trung bình (thang 100), nếu đã chấm")
    total_practice_minutes: int = Field(..., description="Tổng thời gian luyện tập tích lũy (phút)")
    streak_days: int = Field(..., description="Số ngày luyện tập liên tục (Streak)")


class SkillRadarOut(BaseSchema):
    clarity: float | None = Field(..., description="Độ rõ ràng & Mạch lạc (0-100)")
    logic: float | None = Field(..., description="Cấu trúc logic (0-100)")
    evidence: float | None = Field(..., description="Dẫn chứng thực tế (0-100)")
    delivery: float | None = Field(..., description="Phong thái & Giọng điệu (0-100)")
    star_method: float | None = Field(..., description="Phương pháp STAR (0-100)")


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
    overall_score: float | None
    clarity_score: float | None
    logic_score: float | None
    example_score: float | None
    speaking_pace_wpm: float | None
    filler_words_count: int | None
    star_completion_rate: float | None


class ProgressTrendsOut(BaseSchema):
    candidate_id: int
    trends: list[ProgressTrendPointOut]
    avg_wpm: float | None
    avg_filler_count: float | None
    star_mastery_rate: float | None


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
    user_audio_url: str | None
    transcribed_text: str | None
    clarity_score: float | None
    logic_score: float | None
    example_score: float | None
    overall_score: float | None
    feedback_text: str | None
    ideal_answer: str | None
    question_type: str | None
    star_analysis: dict[str, bool] | None
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
    total_turns: int = 0
    performance_rating: str = ""
    avg_clarity: float | None
    avg_logic: float | None
    avg_example: float | None


class SessionResultOut(BaseSchema):
    session_id: int
    candidate_id: int
    status: str
    total_score: float | None
    readiness_badge: str
    clarity_score: float | None
    structure_score: float | None
    evidence_score: float | None
    speaking_pace_wpm: float | None
    pace_rating: str | None
    filler_count: int | None
    filler_words: list[str]
    pause_duration: float | None
    star_analysis: dict[str, bool] | None
    evaluation_status: str
    evaluated_turns: int
    eligible_turns: int
    turns: list[TurnDetailOut]
    total_turns: int = 0
    performance_rating: str = ""
