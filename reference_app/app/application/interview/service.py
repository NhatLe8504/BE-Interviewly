from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from ...domain.errors import DomainValidationError, NotFoundError
from ...domain.interview import (
    InterviewSession,
    InterviewTurn,
    SessionStatus,
    TurnSpeaker,
)
from ..common import ClockPort
from .commands import CompleteSessionCommand, StartSessionCommand, SubmitTurnCommand
from .ports import (
    InterviewSessionRepoPort,
    InterviewTurnRepoPort,
    LLMInterviewerPort,
)

MAX_INTERVIEW_TURNS = 5


@dataclass
class InterviewService:
    sessions: InterviewSessionRepoPort
    turns: InterviewTurnRepoPort
    llm: LLMInterviewerPort
    clock: ClockPort

    def start_session(
        self, session: Any, command: StartSessionCommand,
    ) -> tuple[InterviewSession, InterviewTurn]:
        now = self.clock.now()
        domain_session = InterviewSession(
            session_id=0,
            user_id=command.user_id,
            domain_id=command.domain_id,
            role_id=command.role_id,
            level=command.level,
            language=command.language,
            mode=command.mode,
            status=SessionStatus.in_progress.value,
            started_at=now,
        )
        created_session = self.sessions.create(session, domain_session)

        # Generate first question from AI interviewer
        first_question = self.llm.generate_first_question(
            role=command.role_name,
            level=command.level,
            language=command.language,
        )

        turn_item = InterviewTurn(
            turn_id=0,
            session_id=created_session.session_id,
            turn_number=1,
            question_text=first_question,
            speaker=TurnSpeaker.ai.value,
        )
        created_turn = self.turns.add_turn(session, turn_item)
        return created_session, created_turn

    def submit_turn(
        self,
        session: Any,
        command: SubmitTurnCommand,
        role_name: str = "Software Engineer",
        level: str = "fresher",
        language: str = "vi",
    ) -> tuple[InterviewTurn, InterviewTurn | None, bool]:
        existing_session = self.sessions.find_by_id(session, command.session_id)
        if existing_session is None:
            raise NotFoundError(f"interview session {command.session_id} not found")
        if not existing_session.is_active:
            raise DomainValidationError("cannot submit turn to an inactive session")

        turn = self.turns.find_turn(session, command.session_id, command.turn_number)
        if turn is None:
            raise NotFoundError(f"turn {command.turn_number} not found in session {command.session_id}")

        updated_turn = turn.with_answer(
            answer_text=command.answer_text,
            duration_seconds=command.duration_seconds,
            audio_url=command.audio_url,
        )
        saved_turn = self.turns.update_turn(session, updated_turn)

        is_final = command.turn_number >= MAX_INTERVIEW_TURNS
        if is_final:
            return saved_turn, None, True

        # Build turn history for LLM context
        all_turns = self.turns.find_by_session_id(session, command.session_id)
        history: list[dict[str, str]] = []
        for t in all_turns:
            if t.question_text:
                history.append({"role": "assistant", "content": t.question_text})
            if t.answer_text:
                history.append({"role": "user", "content": t.answer_text})

        next_turn_number = command.turn_number + 1
        is_next_final = next_turn_number >= MAX_INTERVIEW_TURNS

        next_question = self.llm.generate_follow_up(
            history=history,
            last_question=turn.question_text,
            last_answer=command.answer_text,
            turn_number=next_turn_number,
            role=role_name,
            level=level,
            language=language,
            is_final_turn=is_next_final,
        )

        next_turn = InterviewTurn(
            turn_id=0,
            session_id=command.session_id,
            turn_number=next_turn_number,
            question_text=next_question,
            speaker=TurnSpeaker.ai.value,
        )
        created_next_turn = self.turns.add_turn(session, next_turn)
        return saved_turn, created_next_turn, False

    def complete_session(
        self, session: Any, command: CompleteSessionCommand, total_score: Decimal | None = None,
    ) -> InterviewSession:
        interview_session = self.sessions.find_by_id(session, command.session_id)
        if interview_session is None:
            raise NotFoundError(f"session {command.session_id} not found")

        completed = interview_session.mark_completed(
            total_score=total_score,
            completed_at=self.clock.now(),
        )
        return self.sessions.update(session, completed)

    def get_session(self, session: Any, session_id: int) -> InterviewSession:
        found = self.sessions.find_by_id(session, session_id)
        if found is None:
            raise NotFoundError(f"session {session_id} not found")
        return found

    def get_turns(self, session: Any, session_id: int) -> list[InterviewTurn]:
        return self.turns.find_by_session_id(session, session_id)
