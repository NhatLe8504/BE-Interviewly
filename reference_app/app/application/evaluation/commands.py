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
    question_type: str | None = None
    reference_question: str | None = None
    competency: str | None = None
    expected_signals: tuple[str, ...] = ()
    previous_answers: tuple[str, ...] = ()


@dataclass(frozen=True)
class GenerateSessionSummaryCommand:
    session_id: int
    candidate_id: int
