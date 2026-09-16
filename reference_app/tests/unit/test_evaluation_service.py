from __future__ import annotations

from datetime import datetime, timezone
import pytest

from app.application.evaluation.commands import (
    EvaluateTurnCommand,
    GenerateSessionSummaryCommand,
)
from app.application.evaluation.ports import RubricEvaluationData
from app.application.evaluation.service import EvaluationService
from app.domain.evaluation import (
    ActionableFeedback,
    RubricScores,
    SessionSummary,
    StarAnalysis,
    TurnEvaluation,
)


class FakeClock:
    def now(self) -> datetime:
        return datetime(2026, 9, 16, 12, 0, 0, tzinfo=timezone.utc)


class FakeEvaluationRepo:
    def __init__(self) -> None:
        self.evaluations: dict[int, TurnEvaluation] = {}
        self.summaries: dict[int, SessionSummary] = {}
        self.next_id = 1

    def save_turn_evaluation(self, session, turn_id: int, evaluation: TurnEvaluation) -> TurnEvaluation:
        eid = self.next_id
        self.next_id += 1
        saved = TurnEvaluation(
            evaluation_id=eid,
            turn_id=turn_id,
            rubric=evaluation.rubric,
            star=evaluation.star,
            feedback=evaluation.feedback,
            evaluated_at=evaluation.evaluated_at,
        )
        self.evaluations[turn_id] = saved
        return saved

    def find_by_turn_id(self, session, turn_id: int) -> TurnEvaluation | None:
        return self.evaluations.get(turn_id)

    def save_session_summary(self, session, summary: SessionSummary) -> SessionSummary:
        self.summaries[summary.session_id] = summary
        return summary

    def find_summary_by_session_id(self, session, session_id: int) -> SessionSummary | None:
        return self.summaries.get(session_id)


class FakeRubricEvaluator:
    def evaluate(self, question: str, answer: str, role="Software Engineer", level="fresher", language="vi") -> RubricEvaluationData:
        return RubricEvaluationData(
            clarity_score=85.0,
            structure_score=75.0,
            evidence_score=80.0,
            star_analysis={"situation": True, "task": True, "action": True, "result": False},
            feedback="Good technical explanation.",
            sample_better_answer="Quantify your business impact.",
        )


def make_eval_service() -> EvaluationService:
    return EvaluationService(
        evaluations=FakeEvaluationRepo(),
        evaluator=FakeRubricEvaluator(),
        clock=FakeClock(),
    )


def test_evaluate_turn_flow() -> None:
    service = make_eval_service()
    turn_eval = service.evaluate_turn(
        None,
        EvaluateTurnCommand(
            session_id=1,
            turn_id=10,
            question_text="Tell me about indexing.",
            answer_text="B-tree indexes accelerate range searches.",
        ),
    )
    assert turn_eval.turn_id == 10
    assert turn_eval.rubric.clarity == 85.0
    assert turn_eval.rubric.overall == 80.0
    assert turn_eval.star.situation is True
    assert turn_eval.star.result is False
    assert "indexing" not in turn_eval.feedback.feedback_summary or len(turn_eval.feedback.feedback_summary) > 0


def test_generate_session_summary_averages() -> None:
    service = make_eval_service()
    eval1 = TurnEvaluation(
        evaluation_id=1,
        turn_id=101,
        rubric=RubricScores(clarity=80.0, structure=80.0, evidence=80.0, overall=80.0),
    )
    eval2 = TurnEvaluation(
        evaluation_id=2,
        turn_id=102,
        rubric=RubricScores(clarity=90.0, structure=90.0, evidence=90.0, overall=90.0),
    )

    summary = service.generate_session_summary(
        None,
        GenerateSessionSummaryCommand(session_id=1, candidate_id=5),
        turn_evaluations=[eval1, eval2],
    )
    assert summary.session_id == 1
    assert summary.avg_clarity == 85.0
    assert summary.avg_overall == 85.0
    assert summary.total_turns == 2
    assert summary.performance_rating == "Excellent"
