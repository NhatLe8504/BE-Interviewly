from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ....application.container import ServiceContainer
from ....application.evaluation.commands import GenerateSessionSummaryCommand
from ..dependencies import get_container, get_session
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
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> RubricEvaluationOut:
    turn_eval = container.evaluation_service.get_turn_evaluation(session, turn_id)

    # If speech service is available, analyze speech metrics
    turn = None
    turns = container.interview_service.get_turns(session, session_id)
    for t in turns:
        if t.turn_id == turn_id:
            turn = t
            break

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
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> SessionResultOut:
    interview_session = container.interview_service.get_session(session, session_id)
    turns = container.interview_service.get_turns(session, session_id)

    eval_list = []
    evaluations_domain = []
    for turn in turns:
        if not turn.answer_text:
            continue
        try:
            e = container.evaluation_service.get_turn_evaluation(session, turn.turn_id)
            evaluations_domain.append(e)

            speech_out = None
            if container.speech_service is not None:
                m = container.speech_service.analyze_answer(turn.answer_text, turn.duration_seconds)
                speech_out = SpeechMetricsOut(
                    wpm=m.wpm_metrics.wpm,
                    pause_duration=m.wpm_metrics.pause_duration,
                    filler_count=m.wpm_metrics.filler_count,
                    filler_words=list(m.wpm_metrics.filler_words),
                    pace_assessment=m.pace_assessment,
                    tips=list(m.tips),
                )

            eval_list.append(
                RubricEvaluationOut(
                    turn_id=e.turn_id,
                    clarity_score=e.rubric.clarity,
                    structure_score=e.rubric.structure,
                    evidence_score=e.rubric.evidence,
                    overall_score=e.rubric.overall,
                    star_analysis=StarAnalysisOut(
                        situation=e.star.situation if e.star else False,
                        task=e.star.task if e.star else False,
                        action=e.star.action if e.star else False,
                        result=e.star.result if e.star else False,
                        completeness_percentage=e.star.completeness_percentage if e.star else 0.0,
                    ) if e.star else None,
                    feedback=e.feedback.feedback_summary if e.feedback else "",
                    sample_better_answer=e.feedback.sample_better_answer if e.feedback else "",
                    speech_metrics=speech_out,
                ),
            )
        except Exception:
            continue

    summary_cmd = GenerateSessionSummaryCommand(
        session_id=session_id,
        candidate_id=interview_session.user_id,
    )
    summary = container.evaluation_service.generate_session_summary(
        session=session,
        command=summary_cmd,
        turn_evaluations=evaluations_domain,
    )

    return SessionResultOut(
        session_id=summary.session_id,
        candidate_id=summary.candidate_id,
        avg_clarity=summary.avg_clarity,
        avg_structure=summary.avg_structure,
        avg_evidence=summary.avg_evidence,
        avg_overall=summary.avg_overall,
        total_turns=summary.total_turns,
        performance_rating=summary.performance_rating,
        evaluations=eval_list,
    )
