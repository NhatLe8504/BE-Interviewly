from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from ....application.container import ServiceContainer
from ....application.evaluation.commands import EvaluateTurnCommand
from ....application.interview.commands import StartSessionCommand, SubmitTurnCommand
from ..dependencies import get_container, get_session
from ..schemas.auth import UserOut
from ..schemas.interview import (
    SessionOut,
    StartSessionIn,
    TurnOut,
    TurnSubmitIn,
    TurnSubmitResultOut,
)
from .auth import bearer_scheme

router = APIRouter(prefix="/api/v1/interviews", tags=["interviews"])


def _extract_user_id(
    credentials: Any, session: Any, container: ServiceContainer, fallback_id: int = 1,
) -> int:
    if credentials and credentials.credentials:
        try:
            return container.auth_service.tokens.parse(credentials.credentials)
        except Exception:
            pass
    return fallback_id


@router.post("/sessions", response_model=SessionOut, status_code=201)
def start_session(
    data: StartSessionIn,
    credentials: Any = Depends(bearer_scheme),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> SessionOut:
    user_id = _extract_user_id(credentials, session, container)
    cmd = StartSessionCommand(
        user_id=user_id,
        domain_id=data.domain_id,
        role_id=data.role_id,
        role_name=data.role_name,
        level=data.level,
        language=data.language,
        mode=data.mode,
    )
    interview_session, first_turn = container.interview_service.start_session(session, cmd)

    return SessionOut(
        session_id=interview_session.session_id,
        user_id=interview_session.user_id,
        level=interview_session.level,
        language=interview_session.language,
        mode=interview_session.mode,
        status=interview_session.status,
        total_score=float(interview_session.total_score) if interview_session.total_score else None,
        current_turn=TurnOut(
            turn_id=first_turn.turn_id,
            session_id=first_turn.session_id,
            turn_number=first_turn.turn_number,
            question_text=first_turn.question_text,
            speaker=first_turn.speaker,
            duration_seconds=first_turn.duration_seconds,
        ),
    )


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session_details(
    session_id: int,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> SessionOut:
    interview_session = container.interview_service.get_session(session, session_id)
    turns = container.interview_service.get_turns(session, session_id)
    last_turn = turns[-1] if turns else None

    return SessionOut(
        session_id=interview_session.session_id,
        user_id=interview_session.user_id,
        level=interview_session.level,
        language=interview_session.language,
        mode=interview_session.mode,
        status=interview_session.status,
        total_score=float(interview_session.total_score) if interview_session.total_score else None,
        current_turn=TurnOut(
            turn_id=last_turn.turn_id,
            session_id=last_turn.session_id,
            turn_number=last_turn.turn_number,
            question_text=last_turn.question_text,
            answer_text=last_turn.answer_text,
            speaker=last_turn.speaker,
            duration_seconds=last_turn.duration_seconds,
        ) if last_turn else None,
    )


@router.post("/sessions/{session_id}/turns", response_model=TurnSubmitResultOut)
def submit_turn(
    session_id: int,
    data: TurnSubmitIn,
    turn_number: int = Query(default=1, ge=1),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> TurnSubmitResultOut:
    interview_session = container.interview_service.get_session(session, session_id)

    cmd = SubmitTurnCommand(
        session_id=session_id,
        turn_number=turn_number,
        answer_text=data.answer_text,
        duration_seconds=data.duration_seconds,
        pause_duration_seconds=data.pause_duration_seconds,
        audio_url=data.audio_url,
    )
    saved_turn, next_turn, is_completed = container.interview_service.submit_turn(
        session=session,
        command=cmd,
        role_name="Software Engineer",
        level=interview_session.level,
        language=interview_session.language,
    )

    # Trigger async rubric evaluation and save to db
    if container.evaluation_service is not None:
        eval_cmd = EvaluateTurnCommand(
            session_id=session_id,
            turn_id=saved_turn.turn_id,
            question_text=saved_turn.question_text,
            answer_text=data.answer_text,
            role_name="Software Engineer",
            level=interview_session.level,
            language=interview_session.language,
        )
        container.evaluation_service.evaluate_turn(session, eval_cmd)

    return TurnSubmitResultOut(
        submitted_turn=TurnOut(
            turn_id=saved_turn.turn_id,
            session_id=saved_turn.session_id,
            turn_number=saved_turn.turn_number,
            question_text=saved_turn.question_text,
            answer_text=saved_turn.answer_text,
            speaker=saved_turn.speaker,
            duration_seconds=saved_turn.duration_seconds,
        ),
        next_turn=TurnOut(
            turn_id=next_turn.turn_id,
            session_id=next_turn.session_id,
            turn_number=next_turn.turn_number,
            question_text=next_turn.question_text,
            speaker=next_turn.speaker,
            duration_seconds=next_turn.duration_seconds,
        ) if next_turn else None,
        is_completed=is_completed,
    )


@router.get("/sessions/{session_id}/stream")
async def stream_question(
    session_id: int,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> StreamingResponse:
    interview_session = container.interview_service.get_session(session, session_id)
    turns = container.interview_service.get_turns(session, session_id)
    question_text = turns[-1].question_text if turns else "Xin chào, hãy bắt đầu buổi phỏng vấn."

    async def event_generator():
        async for token in container.interview_service.llm.stream_question(question_text):
            yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"
        yield f"data: {json.dumps({'token': '', 'done': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
