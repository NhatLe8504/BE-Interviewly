from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from .errors import DomainValidationError


@dataclass(frozen=True)
class RubricScores:
    clarity: float
    structure: float
    evidence: float
    overall: float = field(default=0.0)

    def __post_init__(self) -> None:
        for name, val in (
            ("clarity", self.clarity),
            ("structure", self.structure),
            ("evidence", self.evidence),
        ):
            if not (0.0 <= float(val) <= 100.0):
                raise DomainValidationError(f"{name} must be between 0 and 100")

        computed_overall = self.overall
        if computed_overall == 0.0:
            computed_overall = round(
                (float(self.clarity) + float(self.structure) + float(self.evidence)) / 3.0,
                2,
            )
        elif not (0.0 <= float(computed_overall) <= 100.0):
            raise DomainValidationError("overall must be between 0 and 100")
        object.__setattr__(self, "overall", float(computed_overall))


@dataclass(frozen=True)
class StarAnalysis:
    situation: bool = False
    task: bool = False
    action: bool = False
    result: bool = False
    notes: str = ""

    @property
    def completeness_percentage(self) -> float:
        parts = [self.situation, self.task, self.action, self.result]
        return round((sum(parts) / 4.0) * 100.0, 1)


@dataclass(frozen=True)
class ActionableFeedback:
    strengths: tuple[str, ...] = ()
    improvements: tuple[str, ...] = ()
    sample_better_answer: str = ""
    feedback_summary: str = ""


@dataclass(frozen=True)
class TurnEvaluation:
    evaluation_id: int
    turn_id: int
    rubric: RubricScores
    star: StarAnalysis | None = None
    feedback: ActionableFeedback | None = None
    evaluated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.turn_id <= 0:
            raise DomainValidationError("turn_id must be positive")


def determine_performance_rating(score: float) -> str:
    if score >= 85.0:
        return "Excellent"
    if score >= 70.0:
        return "Good"
    if score >= 50.0:
        return "Average"
    return "Needs Improvement"


@dataclass(frozen=True)
class SessionSummary:
    session_id: int
    candidate_id: int
    avg_clarity: float
    avg_structure: float
    avg_evidence: float
    avg_overall: float
    total_turns: int
    performance_rating: str = ""

    def __post_init__(self) -> None:
        if self.session_id <= 0:
            raise DomainValidationError("session_id must be positive")
        if self.candidate_id <= 0:
            raise DomainValidationError("candidate_id must be positive")
        if self.total_turns < 0:
            raise DomainValidationError("total_turns cannot be negative")
        if not self.performance_rating:
            rating = determine_performance_rating(self.avg_overall)
            object.__setattr__(self, "performance_rating", rating)
