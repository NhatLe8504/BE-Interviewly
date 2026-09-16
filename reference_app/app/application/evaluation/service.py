from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...domain.errors import NotFoundError
from ...domain.evaluation import (
    ActionableFeedback,
    RubricScores,
    SessionSummary,
    StarAnalysis,
    TurnEvaluation,
)
from ..common import ClockPort
from .commands import EvaluateTurnCommand, GenerateSessionSummaryCommand
from .ports import EvaluationRepoPort, RubricEvaluatorPort


@dataclass
class EvaluationService:
    evaluations: EvaluationRepoPort
    evaluator: RubricEvaluatorPort
    clock: ClockPort

    def evaluate_turn(
        self, session: Any, command: EvaluateTurnCommand,
    ) -> TurnEvaluation:
        # Call LLM / Rubric evaluator adapter
        data = self.evaluator.evaluate(
            question=command.question_text,
            answer=command.answer_text,
            role=command.role_name,
            level=command.level,
            language=command.language,
        )

        rubric = RubricScores(
            clarity=data.clarity_score,
            structure=data.structure_score,
            evidence=data.evidence_score,
        )
        star = StarAnalysis(
            situation=bool(data.star_analysis.get("situation", False)),
            task=bool(data.star_analysis.get("task", False)),
            action=bool(data.star_analysis.get("action", False)),
            result=bool(data.star_analysis.get("result", False)),
        )
        feedback = ActionableFeedback(
            sample_better_answer=data.sample_better_answer,
            feedback_summary=data.feedback,
        )

        turn_eval = TurnEvaluation(
            evaluation_id=0,
            turn_id=command.turn_id,
            rubric=rubric,
            star=star,
            feedback=feedback,
            evaluated_at=self.clock.now(),
        )
        return self.evaluations.save_turn_evaluation(session, command.turn_id, turn_eval)

    def generate_session_summary(
        self,
        session: Any,
        command: GenerateSessionSummaryCommand,
        turn_evaluations: list[TurnEvaluation],
    ) -> SessionSummary:
        if not turn_evaluations:
            summary = SessionSummary(
                session_id=command.session_id,
                candidate_id=command.candidate_id,
                avg_clarity=0.0,
                avg_structure=0.0,
                avg_evidence=0.0,
                avg_overall=0.0,
                total_turns=0,
            )
            return self.evaluations.save_session_summary(session, summary)

        count = len(turn_evaluations)
        avg_clarity = round(sum(e.rubric.clarity for e in turn_evaluations) / count, 2)
        avg_structure = round(sum(e.rubric.structure for e in turn_evaluations) / count, 2)
        avg_evidence = round(sum(e.rubric.evidence for e in turn_evaluations) / count, 2)
        avg_overall = round(sum(e.rubric.overall for e in turn_evaluations) / count, 2)

        summary = SessionSummary(
            session_id=command.session_id,
            candidate_id=command.candidate_id,
            avg_clarity=avg_clarity,
            avg_structure=avg_structure,
            avg_evidence=avg_evidence,
            avg_overall=avg_overall,
            total_turns=count,
        )
        return self.evaluations.save_session_summary(session, summary)

    def get_turn_evaluation(self, session: Any, turn_id: int) -> TurnEvaluation:
        found = self.evaluations.find_by_turn_id(session, turn_id)
        if found is None:
            raise NotFoundError(f"evaluation for turn {turn_id} not found")
        return found

    def get_session_summary(self, session: Any, session_id: int) -> SessionSummary:
        found = self.evaluations.find_summary_by_session_id(session, session_id)
        if found is None:
            raise NotFoundError(f"summary for session {session_id} not found")
        return found
