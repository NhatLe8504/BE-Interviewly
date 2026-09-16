from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ...domain.evaluation import SessionSummary, TurnEvaluation


@dataclass(frozen=True)
class RubricEvaluationData:
    clarity_score: float
    structure_score: float
    evidence_score: float
    star_analysis: dict[str, bool]
    feedback: str
    sample_better_answer: str


class RubricEvaluatorPort(Protocol):
    def evaluate(
        self,
        question: str,
        answer: str,
        role: str = "Software Engineer",
        level: str = "fresher",
        language: str = "vi",
    ) -> RubricEvaluationData:
        ...


class EvaluationRepoPort(Protocol):
    def save_turn_evaluation(
        self, session: Any, turn_id: int, evaluation: TurnEvaluation,
    ) -> TurnEvaluation:
        ...

    def find_by_turn_id(
        self, session: Any, turn_id: int,
    ) -> TurnEvaluation | None:
        ...

    def save_session_summary(
        self, session: Any, summary: SessionSummary,
    ) -> SessionSummary:
        ...

    def find_summary_by_session_id(
        self, session: Any, session_id: int,
    ) -> SessionSummary | None:
        ...
