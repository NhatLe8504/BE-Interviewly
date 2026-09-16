from __future__ import annotations

from pydantic import BaseModel, Field


class StartSessionIn(BaseModel):
    domain_id: int | None = None
    role_id: int | None = None
    role_name: str = Field(default="Software Engineer", max_length=150)
    level: str = Field(default="fresher", max_length=50)
    language: str = Field(default="vi", max_length=10)
    mode: str = Field(default="text", max_length=20)


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
    status: str
    total_score: float | None = None
    current_turn: TurnOut | None = None


class TurnSubmitResultOut(BaseModel):
    submitted_turn: TurnOut
    next_turn: TurnOut | None = None
    is_completed: bool = False
