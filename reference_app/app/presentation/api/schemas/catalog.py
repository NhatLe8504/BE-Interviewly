from __future__ import annotations
from typing import Any

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class DomainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    domain_id: int
    domain_name: str
    description: str | None = None
    created_at: datetime | None = None


class DomainCreateIn(BaseModel):
    domain_name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None


class DomainUpdateIn(BaseModel):
    domain_name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    role_id: int
    domain_id: int
    role_name: str
    description: str | None = None
    created_at: datetime | None = None


class RoleCreateIn(BaseModel):
    domain_id: int
    role_name: str = Field(..., min_length=1, max_length=150)
    description: str | None = None


class RoleUpdateIn(BaseModel):
    role_name: str | None = Field(None, min_length=1, max_length=150)
    description: str | None = None
    domain_id: int | None = None


class StarTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    star_template_id: int
    title: str
    situation_guide: str | None = None
    task_guide: str | None = None
    action_guide: str | None = None
    result_guide: str | None = None
    language: str = "vi"
    created_at: datetime | None = None


class StarTemplateCreateIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=150)
    situation_guide: str | None = None
    task_guide: str | None = None
    action_guide: str | None = None
    result_guide: str | None = None
    language: str = Field("vi", pattern="^(vi|en)$")


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: int
    domain_id: int
    domain_name: str | None = None
    role_id: int | None = None
    role_name: str | None = None
    experience_level: str | None = None
    language: str = "vi"
    question_type: str
    question_text: str
    star_template_id: int | None = None
    is_active: bool = True
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class QuestionDetailOut(QuestionOut):
    star_template: StarTemplateOut | None = None
    quiz_data: dict[str, Any] | None = None
    sample_answer: str | None = None
    follow_up_questions: list[str] | None = None
    tips: list[str] | None = None


class QuestionCreateIn(BaseModel):
    domain_id: int
    question_text: str = Field(..., min_length=1)
    question_type: str = Field(..., pattern="^(behavioral|technical|situational)$")
    language: str = Field("vi", pattern="^(vi|en)$")
    role_id: int | None = None
    experience_level: str | None = Field(
        None, pattern="^(intern|fresher|junior|mid|middle|senior)$",
    )
    star_template_id: int | None = None


class QuestionUpdateIn(BaseModel):
    question_text: str | None = Field(None, min_length=1)
    question_type: str | None = Field(
        None, pattern="^(behavioral|technical|situational)$",
    )
    language: str | None = Field(None, pattern="^(vi|en)$")
    role_id: int | None = None
    experience_level: str | None = Field(
        None, pattern="^(intern|fresher|junior|mid|middle|senior)$",
    )
    star_template_id: int | None = None
    is_active: bool | None = None


class QuestionPageOut(BaseModel):
    items: list[QuestionOut]
    total: int
    limit: int
    offset: int




class QuestionSetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    set_id: int
    title: str
    description: str
    domain_id: int
    domain_name: str | None = None
    role_id: int | None = None
    role_name: str | None = None
    experience_level: str = "junior"
    tech_stack: list[str] = []
    language: str = "vi"
    target_difficulty: int = 3
    estimated_duration_minutes: int = 20
    is_curated: bool = True
    is_active: bool = True
    question_count: int = 0
    practice_count: int = 0
    avg_score: float = 0.0
    pass_rate: float = 0.0
    created_at: datetime | str | None = None


class QuestionSetDetailOut(QuestionSetOut):
    questions: list[QuestionDetailOut] = []


class QuestionSetPageOut(BaseModel):
    items: list[QuestionSetOut]
    total: int
    limit: int
    offset: int

class QuestionBatchIn(BaseModel):
    ids: list[int]


class QuestionEvaluateIn(BaseModel):
    mode: str = Field("all", pattern="^(quiz|text|voice|all)$")
    answer_text: str | None = None
    selected_option_id: str | None = None
    is_quiz_correct: bool | None = None
    language: str = Field("vi", pattern="^(vi|en)$")
    audio_duration_seconds: float | None = None


class StarBreakdownOut(BaseModel):
    situation_score: int = 8
    situation_feedback: str = ""
    task_score: int = 8
    task_feedback: str = ""
    action_score: int = 8
    action_feedback: str = ""
    result_score: int = 8
    result_feedback: str = ""


class RubricScoreItemOut(BaseModel):
    criterion_id: str
    criterion_name: str
    score: int
    max_score: int = 10
    level_label: str
    feedback: str



class MultiModalBreakdownOut(BaseModel):
    quiz_score: float = 0.0
    quiz_max: float = 15.0
    text_score: float = 0.0
    text_max: float = 35.0
    voice_score: float = 0.0
    voice_max: float = 50.0
    total_score: float = 0.0

class QuestionEvaluationResultOut(BaseModel):
    score: int
    passed: bool
    general_feedback: str
    star_breakdown: StarBreakdownOut
    rubric_scores: list[RubricScoreItemOut]
    strengths: list[str]
    improvements: list[str]
    modal_breakdown: MultiModalBreakdownOut | None = None



class PracticeHistoryCreateIn(BaseModel):
    session_title: str
    source_type: str = "basket"  # "set" | "basket" | "single"
    source_id: str | None = None
    domain_id: int | None = None
    domain_name: str | None = None
    role_name: str | None = None
    total_questions: int = 1
    evaluated_count: int = 0
    average_score: float = 0.0
    quiz_score_avg: float | None = None
    text_score_avg: float | None = None
    voice_score_avg: float | None = None
    duration_seconds: int = 0
    questions_summary: list[dict[str, Any]] = []


class PracticeHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    history_id: int | str
    user_id: int | None = None
    session_title: str
    source_type: str
    source_id: str | None = None
    domain_id: int | None = None
    domain_name: str | None = None
    role_name: str | None = None
    total_questions: int
    evaluated_count: int
    average_score: float
    quiz_score_avg: float | None = None
    text_score_avg: float | None = None
    voice_score_avg: float | None = None
    duration_seconds: int
    questions_summary: list[dict[str, Any]] = []
    created_at: datetime | str | None = None


class LeaderboardItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rank: int
    user_id: int | str
    user_name: str
    avatar_url: str | None = None
    is_pro: bool = False
    score: float
    duration_seconds: int
    completed_at: str | None = None


class QuestionSetReviewIn(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=2)


class QuestionSetReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: int | str
    set_id: int | str
    user_id: int | None = None
    user_name: str
    avatar_url: str | None = None
    is_pro: bool = False
    rating: int
    comment: str
    created_at: datetime | str | None = None


class QuestionSetReviewsPageOut(BaseModel):
    set_id: int | str
    average_rating: float
    total_reviews: int
    reviews: list[QuestionSetReviewOut]

class EvaluationQueueIn(BaseModel):
    question_id: int
    question_text: str | None = None
    sample_answer: str | None = None
    quiz_answer: str | None = None
    text_answer: str | None = None
    transcript: str | None = None
    delivery_metrics: dict[str, Any] | None = None
    language: str = "vi"
    is_quiz_correct: bool | None = None
    audio_duration_seconds: float | None = None
    role_name: str | None = None


class EvaluationQueueOut(BaseModel):
    task_id: str
    status: str
    quiz_score: float
    created_at: float | None = None


class EvaluationPullOut(BaseModel):
    task_id: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None


class TextEvaluationQueueIn(BaseModel):
    question_id: int
    question_text: str | None = None
    answer_text: str = Field(..., min_length=1)
    role_name: str = "Software Engineer"
    language: str = "vi"


class VoiceEvaluationQueueIn(BaseModel):
    question_id: int
    question_text: str | None = None
    transcript: str = ""
    delivery_metrics: dict[str, Any]
    language: str = "vi"


class OverallSynthesisIn(BaseModel):
    session_title: str
    total_questions: int
    evaluated_questions: list[dict[str, Any]] = []
    language: str = "vi"


class OverallSynthesisOut(BaseModel):
    session_title: str
    average_score: float
    overall_feedback: str
    strengths: list[str]
    improvements: list[str]
    career_readiness_verdict: str
