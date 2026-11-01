from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ....application.container import ServiceContainer
from ....domain.errors import NotFoundError
from ..dependencies import (
    ensure_session_owner,
    get_container,
    get_current_user_id,
    get_session,
)
from ..schemas.evaluation import (
    RubricEvaluationOut,
    SessionResultOut,
    SpeechMetricsOut,
    StarAnalysisOut,
)

router = APIRouter(prefix="/api/v1/interviews", tags=["evaluations"])


@router.get(
    "/sessions/{session_id}/turns/{turn_id}/evaluation",
    response_model=RubricEvaluationOut,
)
def get_turn_evaluation(
    session_id: int,
    turn_id: int,
    user_id: int = Depends(get_current_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> RubricEvaluationOut:
    interview_session = ensure_session_owner(session_id, user_id, session, container)

    turns = container.interview_service.get_turns(session, session_id)
    turn = next((t for t in turns if t.turn_id == turn_id), None)
    if turn is None:
        raise NotFoundError(f"Turn #{turn_id} not found in session #{session_id}")

    turn_eval = container.evaluation_service.get_turn_evaluation(session, turn_id)
    if turn_eval is None:
        raise NotFoundError(f"Evaluation for turn #{turn_id} not found")

    speech_out = None
    if turn and turn.answer_text and container.speech_service is not None:
        metrics = container.speech_service.analyze_answer(
            turn.answer_text, duration_seconds=turn.duration_seconds,
        )
        speech_out = SpeechMetricsOut(
            wpm=metrics.wpm_metrics.wpm,
            pause_duration=metrics.wpm_metrics.pause_duration,
            filler_count=metrics.wpm_metrics.filler_count,
            filler_words=list(metrics.wpm_metrics.filler_words),
            pace_assessment=metrics.pace_assessment,
            tips=list(metrics.tips),
        )

    return RubricEvaluationOut(
        turn_id=turn_eval.turn_id,
        clarity_score=turn_eval.rubric.clarity,
        structure_score=turn_eval.rubric.structure,
        evidence_score=turn_eval.rubric.evidence,
        overall_score=turn_eval.rubric.overall,
        star_analysis=StarAnalysisOut(
            situation=turn_eval.star.situation if turn_eval.star else False,
            task=turn_eval.star.task if turn_eval.star else False,
            action=turn_eval.star.action if turn_eval.star else False,
            result=turn_eval.star.result if turn_eval.star else False,
            completeness_percentage=turn_eval.star.completeness_percentage if turn_eval.star else 0.0,
        ) if turn_eval.star else None,
        feedback=turn_eval.feedback.feedback_summary if turn_eval.feedback else "",
        sample_better_answer=turn_eval.feedback.sample_better_answer if turn_eval.feedback else "",
        speech_metrics=speech_out,
    )


@router.get(
    "/sessions/{session_id}/result",
    response_model=SessionResultOut,
)
def get_session_result(
    session_id: int,
    user_id: int = Depends(get_current_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> SessionResultOut:
    ensure_session_owner(session_id, user_id, session, container)
    result = container.analytics_service.get_session_result(session, user_id, session_id)
    evaluations = []
    for turn in result.turns:
        if any(score is None for score in (
            turn.overall_score, turn.clarity_score, turn.logic_score, turn.example_score,
        )):
            continue
        star = turn.star_analysis
        evaluations.append(RubricEvaluationOut(
            turn_id=turn.turn_id,
            clarity_score=turn.clarity_score,
            structure_score=turn.logic_score,
            evidence_score=turn.example_score,
            overall_score=turn.overall_score,
            star_analysis=StarAnalysisOut(
                **star, completeness_percentage=25.0 * sum(star.values()),
            ) if star is not None else None,
            feedback=turn.feedback_text or "",
            sample_better_answer=turn.ideal_answer or "",
            speech_metrics=None,
        ))
    return SessionResultOut(
        session_id=session_id,
        candidate_id=user_id,
        avg_clarity=result.clarity_score,
        avg_structure=result.structure_score,
        avg_evidence=result.evidence_score,
        avg_overall=result.total_score,
        total_score=result.total_score,
        readiness_badge=result.readiness_badge,
        pace_rating=result.pace_rating,
        star_analysis=result.star_analysis,
        evaluation_status=result.evaluation_status,
        evaluated_turns=result.evaluated_turns,
        eligible_turns=result.eligible_turns,
        total_turns=len(result.turns),
        performance_rating=result.performance_rating,
        evaluations=evaluations,
    )
