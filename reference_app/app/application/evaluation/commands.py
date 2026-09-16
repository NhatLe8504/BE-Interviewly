from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvaluateTurnCommand:
    session_id: int
    turn_id: int
    question_text: str
    answer_text: str
    role_name: str = "Software Engineer"
    level: str = "fresher"
    language: str = "vi"


@dataclass(frozen=True)
class GenerateSessionSummaryCommand:
    session_id: int
    candidate_id: int
