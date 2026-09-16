from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StartSessionCommand:
    user_id: int
    domain_id: int | None = None
    role_id: int | None = None
    role_name: str = "Software Engineer"
    level: str = "fresher"
    language: str = "vi"
    mode: str = "text"


@dataclass(frozen=True)
class SubmitTurnCommand:
    session_id: int
    turn_number: int
    answer_text: str
    duration_seconds: float = 0.0
    pause_duration_seconds: float = 0.0
    audio_url: str | None = None


@dataclass(frozen=True)
class CompleteSessionCommand:
    session_id: int
    user_id: int
