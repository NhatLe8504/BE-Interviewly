from __future__ import annotations

from decimal import Decimal
import json
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ...application.evaluation.ports import EvaluationRepoPort
from ...domain.evaluation import (
    ActionableFeedback,
    RubricScores,
    SessionSummary,
    StarAnalysis,
    TurnEvaluation,
)
from .models.session import (
    AnswerEvaluation as DbEvaluation,
    InterviewSession as DbSession,
    InterviewTurn as DbTurn,
    SessionProgressSummary as DbSummary,
)
from .models.session_plan import InterviewFlowState
from .models.enums import SessionStatus
from .score_rollup import answer_groups


class SqlAlchemyEvaluationRepository(EvaluationRepoPort):
    def refresh_session_score(self, session: Any, session_id: int) -> None:
        interview = session.get(DbSession, session_id)
        if interview is None:
            return
        flow = session.get(InterviewFlowState, session_id)
        turns = list(session.scalars(
            select(DbTurn).where(DbTurn.session_id == session_id)
            .options(selectinload(DbTurn.evaluation))
        ))
        groups = answer_groups(turns, flow.snapshot if flow else None)
        eligible = [turn for group in groups for turn in group]
        complete = interview.status == SessionStatus.completed and bool(eligible) and all(
            turn.evaluation is not None and all(value is not None for value in (
                turn.evaluation.overall_score, turn.evaluation.clarity_score,
                turn.evaluation.logic_score, turn.evaluation.example_score,
            )) for turn in eligible
        )
        interview.total_score = Decimal(str(round(
            sum(sum(float(turn.evaluation.overall_score) for turn in group) / len(group)
                for group in groups) / len(groups), 2,
        ))) if complete else None
        session.flush()

    def save_turn_evaluation(
        self, session: Any, turn_id: int, evaluation: TurnEvaluation,
    ) -> TurnEvaluation:
        stmt = select(DbEvaluation).where(DbEvaluation.turn_id == turn_id)
        row = session.scalar(stmt)
        feedback_str = evaluation.feedback.feedback_summary if evaluation.feedback else ""
        if evaluation.feedback and evaluation.feedback.sample_better_answer:
            feedback_str += f"\n\n[Gợi ý trả lời mẫu]: {evaluation.feedback.sample_better_answer}"

        star_tag = ""
        if evaluation.star:
            star_json = json.dumps({
                "situation": evaluation.star.situation,
                "task": evaluation.star.task,
                "action": evaluation.star.action,
                "result": evaluation.star.result,
            })
            star_tag = f"<!--STAR:{star_json}-->\n"
        full_feedback = star_tag + feedback_str

        c_10 = Decimal(str(round(evaluation.rubric.clarity / 10.0, 2)))
        s_10 = Decimal(str(round(evaluation.rubric.structure / 10.0, 2)))
        e_10 = Decimal(str(round(evaluation.rubric.evidence / 10.0, 2)))
        o_10 = Decimal(str(round(evaluation.rubric.overall / 10.0, 2)))

        if row is None:
            row = DbEvaluation(
                turn_id=turn_id,
                clarity_score=c_10,
                logic_score=s_10,
                example_score=e_10,
                overall_score=o_10,
                feedback_text=full_feedback,
                question_type=evaluation.question_type,
                rubric_version=evaluation.rubric_version,
            )
            session.add(row)
        else:
            row.clarity_score = c_10
            row.logic_score = s_10
            row.example_score = e_10
            row.overall_score = o_10
            row.feedback_text = full_feedback
            row.question_type = evaluation.question_type
            row.rubric_version = evaluation.rubric_version

        session.flush()
        turn = session.get(DbTurn, turn_id)
        if turn is not None:
            self.refresh_session_score(session, turn.session_id)
        session.commit()
        session.refresh(row)
        return evaluation

    def find_by_turn_id(self, session: Any, turn_id: int) -> TurnEvaluation | None:
        stmt = select(DbEvaluation).where(DbEvaluation.turn_id == turn_id)
        row = session.scalar(stmt)
        if row is None:
            return None

        clarity = float(row.clarity_score or 0) * 10.0
        structure = float(row.logic_score or 0) * 10.0
        evidence = float(row.example_score or 0) * 10.0
        overall = float(row.overall_score or 0) * 10.0

        rubric = RubricScores(
            clarity=clarity,
            structure=structure,
            evidence=evidence,
            overall=overall,
        )

        raw_feedback = row.feedback_text or ""
        star = None
        if "<!--STAR:" in raw_feedback:
            start = raw_feedback.find("<!--STAR:") + len("<!--STAR:")
            end = raw_feedback.find("-->", start)
            if end != -1:
                try:
                    s_data = json.loads(raw_feedback[start:end])
                    star = StarAnalysis(
                        situation=bool(s_data.get("situation", False)),
                        task=bool(s_data.get("task", False)),
                        action=bool(s_data.get("action", False)),
                        result=bool(s_data.get("result", False)),
                    )
                    raw_feedback = raw_feedback[end + 3:].lstrip("\n")
                except Exception:
                    pass

        feedback = ActionableFeedback(
            feedback_summary=raw_feedback,
        )
        return TurnEvaluation(
            evaluation_id=row.evaluation_id,
            turn_id=row.turn_id,
            rubric=rubric,
            star=star,
            feedback=feedback,
            question_type=row.question_type,
            rubric_version=row.rubric_version,
            evaluated_at=row.created_at,
        )

    def save_session_summary(
        self, session: Any, summary: SessionSummary,
    ) -> SessionSummary:
        stmt = select(DbSummary).where(DbSummary.session_id == summary.session_id)
        row = session.scalar(stmt)
        c_10 = Decimal(str(round(summary.avg_clarity / 10.0, 2)))
        s_10 = Decimal(str(round(summary.avg_structure / 10.0, 2)))
        e_10 = Decimal(str(round(summary.avg_evidence / 10.0, 2)))
        o_10 = Decimal(str(round(summary.avg_overall / 10.0, 2)))

        if row is None:
            row = DbSummary(
                session_id=summary.session_id,
                candidate_id=summary.candidate_id,
                avg_clarity_score=c_10,
                avg_logic_score=s_10,
                avg_example_score=e_10,
                avg_overall_score=o_10,
                total_turns=summary.total_turns,
            )
            session.add(row)
        else:
            row.avg_clarity_score = c_10
            row.avg_logic_score = s_10
            row.avg_example_score = e_10
            row.avg_overall_score = o_10
            row.total_turns = summary.total_turns

        session.commit()
        session.refresh(row)
        return summary

    def find_summary_by_session_id(
        self, session: Any, session_id: int,
    ) -> SessionSummary | None:
        stmt = select(DbSummary).where(DbSummary.session_id == session_id)
        row = session.scalar(stmt)
        if row is None:
            return None

        return SessionSummary(
            session_id=row.session_id,
            candidate_id=row.candidate_id,
            avg_clarity=float(row.avg_clarity_score or 0) * 10.0,
            avg_structure=float(row.avg_logic_score or 0) * 10.0,
            avg_evidence=float(row.avg_example_score or 0) * 10.0,
            avg_overall=float(row.avg_overall_score or 0) * 10.0,
            total_turns=row.total_turns or 0,
        )
