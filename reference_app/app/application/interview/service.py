from __future__ import annotations

from sqlalchemy import select, func
from ...infrastructure.persistence.models.session_plan import InterviewSessionConfig
from .question_selection import QuestionSelectionService
from .intent_composer import QuestionIntentComposer

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
    ApprovedQuestionLookupPort,
    InterviewSessionRepoPort,
    InterviewTurnRepoPort,
    LLMInterviewerPort,
)
from .session_plan import default_stage_configs, validate_stage_configs

MAX_INTERVIEW_TURNS = 5


@dataclass
class InterviewService:
    sessions: InterviewSessionRepoPort
    turns: InterviewTurnRepoPort
    llm: LLMInterviewerPort
    clock: ClockPort
    questions: ApprovedQuestionLookupPort | None = None

    def start_session(
        self, session: Any, command: StartSessionCommand,
    ) -> tuple[InterviewSession, InterviewTurn]:
        stage_configs = validate_stage_configs(
            command.stage_configs or default_stage_configs(),
        )
        self._validate_selected_questions(session, stage_configs, command.language)

        now = self.clock.now()
        domain_session = InterviewSession(
            session_id=0,
            user_id=command.user_id,
            domain_id=command.domain_id,
            role_id=command.role_id,
            level=command.level,
            language=command.language,
            mode=command.mode,
            barge_in_enabled=command.barge_in_enabled,
            status=SessionStatus.in_progress.value,
            started_at=now,
        )
        created_session = self.sessions.create(session, domain_session)

        first_intent = None
        first_stage = stage_configs[0]
        if session is not None and hasattr(session, "add"):
            for order, sc in enumerate(stage_configs, start=1):
                cfg_record = InterviewSessionConfig(
                    session_id=created_session.session_id,
                    stage_key=sc.stage_key,
                    stage_order=order,
                    source_mode=sc.source_mode,
                    min_turns=sc.min_turns,
                    max_turns=sc.max_turns,
                    selected_question_ids=sc.selected_question_ids,
                    difficulty_filter=sc.difficulty_filter,
                )
                session.add(cfg_record)
            session.flush()

            # Sample question intent for first stage
            intents = QuestionSelectionService.sample_questions_for_stage(
                session=session,
                session_id=created_session.session_id,
                stage_key=first_stage.stage_key,
                source_mode=first_stage.source_mode,
                target_count=first_stage.max_turns,
                selected_question_ids=first_stage.selected_question_ids,
                domain_id=command.domain_id,
                role_id=command.role_id,
            )
            first_intent = intents[0] if intents else None
        situational_system = QuestionIntentComposer.build_situational_system_prompt(
            role=command.role_name,
            level=command.level,
            stage_key=first_stage.stage_key,
            intent_ctx=first_intent,
            language=command.language,
        )

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

    def _validate_selected_questions(
        self, session: Any, stage_configs: list[Any], language: str,
    ) -> None:
        selected_question_ids = sorted(
            {
                question_id
                for config in stage_configs
                for question_id in (config.selected_question_ids or [])
            },
        )
        if not selected_question_ids or session is None:
            return
        if self.questions is None:
            raise DomainValidationError("question lookup is not configured")

        available_question_ids = self.questions.find_available_question_ids(
            session,
            selected_question_ids,
            language,
        )
        unavailable_question_ids = set(selected_question_ids) - available_question_ids
        if unavailable_question_ids:
            unavailable_ids = ", ".join(str(item) for item in sorted(unavailable_question_ids))
            raise DomainValidationError(
                f"selected questions must be active, approved, and use the session language: {unavailable_ids}",
            )

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

        # Determine dynamic total turns from session config
        total_configured_turns = MAX_INTERVIEW_TURNS
        if session is not None and hasattr(session, "execute"):
            stmt = select(func.sum(InterviewSessionConfig.max_turns)).where(
                InterviewSessionConfig.session_id == command.session_id
            )
            total_configured_turns = session.execute(stmt).scalar() or MAX_INTERVIEW_TURNS
        is_final = command.turn_number >= total_configured_turns
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
