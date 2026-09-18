from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StageConfigIn(BaseModel):
    stage_key: Literal["warmup", "technical", "closing"]
    source_mode: Literal["auto_random", "manual", "mixed"] = "auto_random"
    min_turns: int = Field(default=1, ge=1, le=3)
    max_turns: int = Field(default=2, ge=1, le=3)
    selected_question_ids: list[int] | None = None
    difficulty_filter: int | None = None


class StartSessionIn(BaseModel):
    domain_id: int | None = None
    role_id: int | None = None
    role_name: str = Field(default="Software Engineer", max_length=150)
    level: str = Field(default="fresher", max_length=50)
    language: Literal["vi", "en"] = "vi"
    mode: Literal["text", "voice"] = "text"
    barge_in_enabled: bool = False
    stage_configs: list[StageConfigIn] | None = None
    selected_question_ids: list[int] | None = None
    practice_id: int | None = None


class QuestionContextOut(BaseModel):
    question_id: int
    intent: str
    stage_key: str
    difficulty: int = 3
    topic_label: str = ""


class TurnSubmitIn(BaseModel):
    answer_text: str = Field(min_length=1)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    pause_duration_seconds: float = Field(default=0.0, ge=0.0)
    audio_url: str | None = None


class TurnOut(BaseModel):
    turn_id: int
    session_id: int
    turn_number: int
    question_text: str
    answer_text: str | None = None
    speaker: str = "ai"
    duration_seconds: float = 0.0


class SessionOut(BaseModel):
    session_id: int
    user_id: int
    level: str
    language: str
    mode: str
    barge_in_enabled: bool = False
    status: str
    total_score: float | None = None
    current_turn: TurnOut | None = None


class TurnSubmitResultOut(BaseModel):
    submitted_turn: TurnOut
    next_turn: TurnOut | None = None
    is_completed: bool = False
