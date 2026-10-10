from __future__ import annotations

from pathlib import Path

import asyncio
import logging
import time
from typing import Any
import uuid

from ...domain.voice import (
    ALL_STAGE_DEFINITIONS,
    InterviewStageDefinition,
    StageId,
    VoiceEventType,
    VoiceGenerationContext,
    VoiceSessionState,
)
from ...domain.errors import DomainValidationError
from .languages import INTERVIEW_LANGUAGE_SETTINGS
from .ports import LLMVoiceStreamPort, TTSPort, VoiceConnectionPort
from .sentence_splitter import StreamingSentenceSplitter
from ...infrastructure.llm.prompt_templates import (
    build_interviewer_system_prompt,
    build_dynamic_warmup_opening_text,
    build_stage_transition_instruction,
    build_hint_prompt,
    build_follow_up_user_prompt,
)
from .text_sanitizer import sanitize_spoken_text
from ..interview.intent_composer import QuestionIntentComposer, QuestionIntentContext
from ..interview.question_selection import QuestionSelectionService


class VoiceInterviewOrchestrator:
    """
    Coordinates real-time voice interview lifecycle (LISTEN -> THINK -> SPEAK)
    across dynamic stages (Warm-up -> Technical -> Closing or any subset).
    Handles barge-in interruptions, sentence streaming to Edge TTS, and
    event broadcasting over WebSocket.
    """

    def __init__(
        self,
        session_id: int,
        connection: VoiceConnectionPort,
        tts: TTSPort,
        llm: LLMVoiceStreamPort,
        role_name: str = "Software Engineer",
        level: str = "fresher",
        language: str = "vi",
        voice: str = "vi-VN-HoaiMyNeural",
        persona_name: str = "Alex Vance",
        company_name: str | None = None,
        mock_mode: str = "guided",
        total_duration_minutes: int = 45,
        system_prompt: str | None = None,
        barge_in_enabled: bool = True,
        selected_stages: list[str] | None = None,
        questions_per_stage: dict[str, int] | None = None,
        session_factory: Any = None,
        evaluation_service: Any = None,
        user_id: int | None = None,
    ) -> None:
        self.user_id = user_id
        self.session_factory = session_factory
        self.evaluation_service = evaluation_service
        self.current_intent_ctx: QuestionIntentContext | None = None
        self.session_id = session_id
        self.connection = connection
        self.tts = tts
        self.llm = llm
        self.role_name = role_name
        self.level = level
        self.language = language
        self.voice = voice
        self.persona_name = persona_name or "Alex Vance"
        self.company_name = company_name
        self.mock_mode = mock_mode or "guided"
        self.total_duration_minutes = total_duration_minutes or 45
        self.stage_time_limits = self._calculate_stage_time_limits(self.total_duration_minutes)
        self.stage_start_times: dict[str, float] = {}
        self.is_waiting_stage_confirmation = False
        self.pending_transition_next_stage: InterviewStageDefinition | None = None

        self._custom_system_prompt = system_prompt
        self.system_prompt = system_prompt or build_interviewer_system_prompt(
            role=self.role_name,
            level=self.level,
            language=self.language,
            persona_name=self.persona_name,
            company_name=self.company_name,
            mock_mode=self.mock_mode,
        )
        self.barge_in_enabled = barge_in_enabled
        self.pitch: str = "+0Hz" 

        # Configure dynamic stages
        self.questions_per_stage: dict[str, int] = questions_per_stage or {
            StageId.WARMUP.value: 1,
            StageId.TECHNICAL.value: 2,
            StageId.CLOSING.value: 1,
        }
        self.active_stages: list[InterviewStageDefinition] = self._resolve_stages(selected_stages)
        self.current_stage_index: int = 0
        self.turns_in_current_stage: int = 0

        self.state: VoiceSessionState = VoiceSessionState.IDLE
        self.current_turn_id: int = 1
        self.current_generation_id: str | None = None
        self._active_task: asyncio.Task | None = None
        self._generation_counter: int = 0
        self._cancelled_generation_ids: set[str] = set()
        self.conversation_history: list[dict[str, str]] = []
        self._initial_opening_text: str | None = None
        self._has_unvoiced_opening: bool = False
        self._background_tasks: set[asyncio.Task] = set()

        self._load_existing_turns_from_db()

    def _calculate_stage_time_limits(self, total_minutes: int) -> dict[str, int]:
        total_sec = max(300, int(total_minutes * 60))
        return {
            StageId.WARMUP.value: max(60, int(total_sec * (1 / 6))),
            StageId.TECHNICAL.value: max(180, int(total_sec * (4 / 6))),
            StageId.CLOSING.value: max(60, int(total_sec * (1 / 6))),
        }

    def get_stage_elapsed_seconds(self, stage_id: str) -> float:
        start = self.stage_start_times.get(stage_id)
        if start is None:
            return 0.0
        return max(0.0, time.time() - start)

    def _ensure_stage_timer_started(self, stage_id: str) -> None:
        if stage_id not in self.stage_start_times:
            self.stage_start_times[stage_id] = time.time()

    
    def _save_audio_file(self, turn_id: int, speaker: str, audio_bytes: bytes) -> str | None:
        try:
            base_dir = Path("/srv/storage/audio")
            if not base_dir.exists():
                base_dir = Path(__file__).resolve().parents[4] / "storage" / "audio"
            session_dir = base_dir / str(self.session_id)
            session_dir.mkdir(parents=True, exist_ok=True)
            ext = "mp3" if speaker == "ai" else "webm"
            filename = f"turn_{turn_id}_{speaker}.{ext}"
            filepath = session_dir / filename
            filepath.write_bytes(audio_bytes)
            return f"/api/v1/voice/audio/{self.session_id}/{filename}"
        except Exception as exc:
            logging.getLogger("VoiceOrchestrator").warning("Failed to save audio file: %s", exc)
            return None

    def _load_existing_turns_from_db(self) -> None:
        if not self.session_factory:
            return
        db = self.session_factory()
        try:
            from ...infrastructure.persistence.models.session import InterviewTurn as OrmInterviewTurn
            rows = (
                db.query(OrmInterviewTurn)
                .filter_by(session_id=self.session_id)
                .order_by(OrmInterviewTurn.turn_number.asc())
                .all()
            )
            if not rows:
                return

            self.conversation_history = []
            for r in rows:
                if r.message_text:
                    self.conversation_history.append({"role": "assistant", "content": r.message_text})
                if r.transcribed_text:
                    self.conversation_history.append({"role": "user", "content": r.transcribed_text})

            last_row = rows[-1]
            if last_row.transcribed_text and last_row.transcribed_text.strip():
                self.current_turn_id = last_row.turn_number + 1
                self._has_unvoiced_opening = False
            else:
                self.current_turn_id = last_row.turn_number
                self._has_unvoiced_opening = not bool(last_row.audio_url)
                if last_row.message_text:
                    self._initial_opening_text = last_row.message_text

            # If starting at warmup stage and no candidate response has occurred yet,
            # ensure a stale pre-seeded technical question is discarded so small talk is used instead.
            cur_stg = self.get_current_stage()
            if cur_stg.id == StageId.WARMUP.value and not any(m.get("role") == "user" for m in self.conversation_history):
                msg = (last_row.message_text or "").lower()
                is_small_talk = any(k in msg for k in ("thời tiết", "đường đi", "cà phê", "năng lượng", "tâm trạng", "weather", "traffic", "coffee", "đồng hành"))
                if not is_small_talk:
                    self.conversation_history = []
                    self._initial_opening_text = None
                    self._has_unvoiced_opening = False
                    self.current_turn_id = 1
        except Exception as exc:
            logging.getLogger("VoiceOrchestrator").warning("Failed to load existing turns: %s", exc)
        finally:
            db.close()

    async def _broadcast_conversation_history(self) -> None:
        if not self.session_factory or not self.connection.is_open():
            return
        db = self.session_factory()
        try:
            from ...infrastructure.persistence.models.session import InterviewTurn as OrmInterviewTurn
            from ...infrastructure.persistence.models.enums import TurnSpeaker
            rows = (
                db.query(OrmInterviewTurn)
                .filter_by(session_id=self.session_id)
                .order_by(OrmInterviewTurn.turn_number.asc())
                .all()
            )
            turns_payload: list[dict[str, Any]] = []
            for r in rows:
                if r.message_text:
                    ai_audio = r.audio_url if r.audio_url and r.audio_url != "voice_streamed" else None
                    turns_payload.append({
                        "id": f"turn-ai-{r.turn_number}",
                        "turnNumber": r.turn_number,
                        "speaker": "ai",
                        "text": r.message_text,
                        "audioUrl": ai_audio,
                    })
                if r.transcribed_text:
                    user_audio = getattr(r, "user_audio_url", None)
                    turns_payload.append({
                        "id": f"turn-u-{r.turn_number}",
                        "turnNumber": r.turn_number,
                        "speaker": "user",
                        "text": r.transcribed_text,
                        "audioUrl": user_audio,
                    })
            if turns_payload:
                await self.connection.send_event({
                    "type": "conversation_history",
                    "turns": turns_payload,
                })
        except Exception as exc:
            logging.getLogger("VoiceOrchestrator").warning("Failed to broadcast conversation history: %s", exc)
        finally:
            db.close()

    async def _emit_question_context(self) -> None:
        if self.current_intent_ctx and self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.QUESTION_CONTEXT.value,
                "question_id": self.current_intent_ctx.question_id,
                "topic_label": self.current_intent_ctx.topic_label,
                "stage_key": self.current_intent_ctx.stage_key,
                "difficulty": self.current_intent_ctx.difficulty,
            })

    def _persist_ai_turn(
        self,
        turn_id: int,
        message_text: str,
        intent_ctx: QuestionIntentContext | None = None,
        audio_url: str | None = None,
    ) -> None:
        if not self.session_factory or not message_text.strip():
            return
        question_id = intent_ctx.question_id if intent_ctx else None
        stage_key = intent_ctx.stage_key if intent_ctx else None
        db = self.session_factory()
        try:
            from ...infrastructure.persistence.models.session import InterviewTurn as OrmInterviewTurn
            from ...infrastructure.persistence.models.enums import TurnSpeaker
            existing = (
                db.query(OrmInterviewTurn)
                .filter_by(session_id=self.session_id, turn_number=turn_id)
                .first()
            )
            if existing:
                existing.message_text = message_text.strip()
                existing.speaker = TurnSpeaker.ai
                existing.audio_url = audio_url or existing.audio_url or "voice_streamed"
                if question_id is not None:
                    existing.question_id = int(question_id)
            else:
                turn_rec = OrmInterviewTurn(
                    session_id=self.session_id,
                    turn_number=turn_id,
                    speaker=TurnSpeaker.ai,
                    message_text=message_text.strip(),
                    audio_url=audio_url or "voice_streamed",
                    question_id=int(question_id) if question_id is not None else None,
                )
                db.add(turn_rec)
            if question_id is not None and stage_key:
                # Câu hỏi ngân hàng đã thực sự được hỏi ở lượt này.
                QuestionSelectionService.mark_selection_used(
                    db, self.session_id, stage_key, int(question_id), turn_id,
                )
            db.commit()
            self._has_unvoiced_opening = False
        except Exception as exc:
            db.rollback()
            logging.getLogger("VoiceOrchestrator").warning("Failed to persist AI turn #%d: %s", turn_id, exc)
        finally:
            db.close()

    def _persist_user_transcript(self, turn_id: int, transcript: str) -> None:
        if not self.session_factory or not transcript.strip():
            return
        db = self.session_factory()
        try:
            from ...infrastructure.persistence.models.session import InterviewTurn as OrmInterviewTurn
            from ...infrastructure.persistence.models.enums import TurnSpeaker
            existing = (
                db.query(OrmInterviewTurn)
                .filter_by(session_id=self.session_id, turn_number=turn_id)
                .first()
            )
            if existing:
                existing.transcribed_text = transcript.strip()
            else:
                turn_rec = OrmInterviewTurn(
                    session_id=self.session_id,
                    turn_number=turn_id,
                    speaker=TurnSpeaker.candidate,
                    transcribed_text=transcript.strip(),
                )
                db.add(turn_rec)
            db.commit()
        except Exception as exc:
            db.rollback()
            logging.getLogger("VoiceOrchestrator").warning("Failed to persist user transcript turn #%d: %s", turn_id, exc)
        finally:
            db.close()

    def _resolve_stages(self, selected_stages: list[str] | None) -> list[InterviewStageDefinition]:
        if not selected_stages:
            return [
                ALL_STAGE_DEFINITIONS[StageId.WARMUP.value],
                ALL_STAGE_DEFINITIONS[StageId.TECHNICAL.value],
                ALL_STAGE_DEFINITIONS[StageId.CLOSING.value],
            ]
        resolved: list[InterviewStageDefinition] = []
        for s_id in selected_stages:
            clean_id = str(s_id).lower().strip()
            if clean_id in ALL_STAGE_DEFINITIONS:
                resolved.append(ALL_STAGE_DEFINITIONS[clean_id])
        if not resolved:
            resolved = [ALL_STAGE_DEFINITIONS[StageId.TECHNICAL.value]]
        return resolved

    def get_current_stage(self) -> InterviewStageDefinition:
        idx = max(0, min(self.current_stage_index, len(self.active_stages) - 1))
        return self.active_stages[idx]

    def get_target_turns_for_current_stage(self) -> int:
        cur = self.get_current_stage()
        return self.questions_per_stage.get(cur.id, cur.default_target_turns)

    def get_current_stage_data(self) -> dict[str, Any]:
        cur = self.get_current_stage()
        is_vi = self.language == "vi"
        return {
            "id": cur.id,
            "name": cur.name_vi if is_vi else cur.name_en,
            "description": cur.description_vi if is_vi else cur.description_en,
            "subtopics": cur.subtopics_vi if is_vi else cur.subtopics_en,
            "index": self.current_stage_index + 1,
            "total": len(self.active_stages),
            "is_first": self.current_stage_index == 0,
            "is_last": self.current_stage_index >= len(self.active_stages) - 1,
        }

    def get_all_stages_data(self) -> list[dict[str, Any]]:
        is_vi = self.language == "vi"
        return [
            {
                "id": stage.id,
                "name": stage.name_vi if is_vi else stage.name_en,
                "description": stage.description_vi if is_vi else stage.description_en,
                "subtopics": stage.subtopics_vi if is_vi else stage.subtopics_en,
                "order": idx + 1,
            }
            for idx, stage in enumerate(self.active_stages)
        ]

    def is_generation_cancelled(self, generation_id: str) -> bool:
        return (
            generation_id in self._cancelled_generation_ids
            or generation_id != self.current_generation_id
        )

    async def set_state(self, new_state: VoiceSessionState) -> None:
        self.state = new_state
        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.STATE.value,
                "state": new_state.value,
                "turn_id": self.current_turn_id,
                "generation_id": self.current_generation_id or "",
                "current_stage": self.get_current_stage_data(),
                "stages": self.get_all_stages_data(),
                "turn_in_stage": self.turns_in_current_stage + 1,
                "target_turns_in_stage": self.get_target_turns_for_current_stage(),
            })

    def set_barge_in_enabled(self, enabled: bool) -> None:
        self.barge_in_enabled = enabled

    def set_interview_language(self, language: str) -> None:
        if not isinstance(language, str) or language not in INTERVIEW_LANGUAGE_SETTINGS:
            raise DomainValidationError("Unsupported interview language")
        if language == self.language:
            return
        if self.state not in (VoiceSessionState.IDLE, VoiceSessionState.LISTEN):
            raise DomainValidationError("Change language while the interviewer is waiting for your answer")
        self.language = language
        self.voice = INTERVIEW_LANGUAGE_SETTINGS[language][1]
        if not self._custom_system_prompt:
            self.system_prompt = build_interviewer_system_prompt(
                role=self.role_name,
                level=self.level,
                language=self.language,
                persona_name=self.persona_name,
                company_name=self.company_name,
                mock_mode=self.mock_mode,
            )

    def set_pitch(self, pitch: str | int | float | None) -> None:
        from ...infrastructure.tts.edge_tts_adapter import EdgeTTSAdapter
        self.pitch = EdgeTTSAdapter._sanitize_pitch(pitch)

    def _build_opening_question(self) -> str:
        cur_stage = self.get_current_stage()
        is_vi = self.language == "vi"

        if cur_stage.id == StageId.WARMUP.value:
            # Chặng Khởi Động (Warm-up) LUÔN LUÔN là small talk, trò chuyện phá băng.
            # Tuyệt đối không gắn câu hỏi chuyên môn vào câu mở đầu này.
            seed = int(time.time() * 1000) ^ (self.session_id * 31)
            return build_dynamic_warmup_opening_text(
                role=self.role_name,
                level=self.level,
                persona_name=self.persona_name,
                company_name=self.company_name,
                language=self.language,
                variant_seed=seed,
            )

        if cur_stage.id == StageId.TECHNICAL.value:
            if self.current_intent_ctx and self.current_intent_ctx.intent:
                if is_vi:
                    return (
                        f"Chào bạn, chúng ta sẽ bắt đầu trực tiếp với phần phỏng vấn chuyên môn cho vị trí {self.role_name} ({self.level}). "
                        f"Câu hỏi đầu tiên: {self.current_intent_ctx.intent}"
                    )
                return (
                    f"Hello! We will dive straight into the technical interview for {self.role_name} ({self.level}). "
                    f"First question: {self.current_intent_ctx.intent}"
                )
            if is_vi:
                return (
                    f"Chào bạn, chúng ta sẽ bắt đầu trực tiếp với phần phỏng vấn chuyên môn cho vị trí {self.role_name} ({self.level}). "
                    "Bạn hãy giới thiệu về một kiến trúc hệ thống hoặc bài toán kỹ thuật phức tạp nhất mà bạn từng trực tiếp thiết kế và giải quyết."
                )
            return (
                f"Hello! We will dive straight into the technical interview for {self.role_name} ({self.level}). "
                "Could you tell me about the most complex system architecture or engineering challenge you have solved?"
            )

        if is_vi:
            return (
                f"Chào bạn, chúng ta bước vào phần trao đổi về định hướng và mong muốn cho vị trí {self.role_name}. "
                "Bạn có câu hỏi nào muốn đặt ra cho công ty chúng tôi về văn hóa, lộ trình phát triển hay đội ngũ trước không?"
            )
        return (
            f"Hello! We are now in the closing session for {self.role_name}. "
            "What questions do you have for our team and company regarding culture, expectations, or projects?"
        )

    async def handle_client_ready(
        self,
        role_name: str | None = None,
        level: str | None = None,
        language: str | None = None,
        voice: str | None = None,
        pitch: str | int | None = None,
        barge_in_enabled: bool | None = None,
        selected_stages: list[str] | None = None,
        questions_per_stage: dict[str, int] | None = None,
        persona_name: str | None = None,
        company_name: str | None = None,
        mock_mode: str | None = None,
        total_duration_minutes: int | None = None,
    ) -> None:
        if role_name:
            self.role_name = role_name
        if level:
            self.level = level
        if persona_name:
            self.persona_name = persona_name
        if company_name:
            self.company_name = company_name
        if mock_mode:
            self.mock_mode = mock_mode
        if total_duration_minutes:
            self.total_duration_minutes = max(5, int(total_duration_minutes))
            self.stage_time_limits = self._calculate_stage_time_limits(self.total_duration_minutes)

        if not self._custom_system_prompt:
            self.system_prompt = build_interviewer_system_prompt(
                role=self.role_name,
                level=self.level,
                language=self.language,
                persona_name=self.persona_name,
                company_name=self.company_name,
                mock_mode=self.mock_mode,
            )

        if language:
            self.set_interview_language(language)
        if voice:
            self.voice = voice
        if pitch is not None:
            self.set_pitch(pitch)
        if barge_in_enabled is not None:
            self.barge_in_enabled = barge_in_enabled
        if questions_per_stage:
            self.questions_per_stage.update(questions_per_stage)
        if selected_stages:
            self.active_stages = self._resolve_stages(selected_stages)
            self.current_stage_index = 0
            self.turns_in_current_stage = 0

        cur_stg = self.get_current_stage()
        self._ensure_stage_timer_started(cur_stg.id)

        # Broadcast initial stage info
        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.STAGE_INFO.value,
                "current_stage": self.get_current_stage_data(),
                "stages": self.get_all_stages_data(),
                "turn_in_stage": self.turns_in_current_stage + 1,
                "target_turns_in_stage": self.get_target_turns_for_current_stage(),
                "stage_elapsed_seconds": int(self.get_stage_elapsed_seconds(cur_stg.id)),
                "stage_max_seconds": self.stage_time_limits.get(cur_stg.id, 600),
                "total_duration_minutes": self.total_duration_minutes,
                "mock_mode": self.mock_mode,
                "persona_name": self.persona_name,
                "company_name": self.company_name,
            })

        # Resolve intent for current stage if DB session is available
        self._resolve_next_intent()
        await self._emit_question_context()

        # Broadcast conversation history if available
        if self.conversation_history and self.connection.is_open():
            await self._broadcast_conversation_history()

        # If voice session has no history yet, or has an unvoiced initial opening
        should_speak_opening = False
        if not self.conversation_history and self.state == VoiceSessionState.IDLE:
            should_speak_opening = True
        elif (
            self._has_unvoiced_opening
            and self.state == VoiceSessionState.IDLE
            and not any(m.get("role") == "user" for m in self.conversation_history)
        ):
            should_speak_opening = True

        if should_speak_opening:
            await self.set_state(VoiceSessionState.THINK)
            prompt = self._build_opening_question()
            self._active_task = asyncio.create_task(
                self._stream_predefined_text(prompt),
            )
        else:
            await self.set_state(VoiceSessionState.LISTEN)

    async def handle_user_speech_start(self, *, force: bool = False) -> None:
        if not force and not self.barge_in_enabled:
            return

        if self.state in (VoiceSessionState.SPEAK, VoiceSessionState.THINK) or (
            self._active_task and not self._active_task.done()
        ) or (force and self.current_generation_id):
            await self.cancel_current_generation()
            await self.set_state(VoiceSessionState.LISTEN)

    async def handle_interim_transcript(self, text: str) -> None:
        if self.barge_in_enabled and len(text.strip()) >= 2 and self.state in (
            VoiceSessionState.SPEAK, VoiceSessionState.THINK,
        ):
            await self.cancel_current_generation()
            await self.set_state(VoiceSessionState.LISTEN)

        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.TRANSCRIPT.value,
                "role": "candidate",
                "text": text,
                "is_final": False,
                "turn_id": self.current_turn_id,
            })

    async def handle_final_transcript(
        self, text: str, duration_seconds: float = 0.0,
    ) -> None:
        clean_text = text.strip()
        if not clean_text:
            return


        # Ensure any leftover generation is stopped
        await self.cancel_current_generation()

        # Broadcast final user transcript
        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.TRANSCRIPT.value,
                "role": "candidate",
                "text": clean_text,
                "is_final": True,
                "turn_id": self.current_turn_id,
                "duration_seconds": duration_seconds,
            })

        self.conversation_history.append({"role": "user", "content": clean_text})
        self._persist_user_transcript(self.current_turn_id, clean_text)
        self.turns_in_current_stage += 1

        # Transition state to THINK first
        await self.set_state(VoiceSessionState.THINK)

        cur_stage = self.get_current_stage()
        self._ensure_stage_timer_started(cur_stage.id)
        elapsed_sec = self.get_stage_elapsed_seconds(cur_stage.id)
        stage_limit_sec = self.stage_time_limits.get(cur_stage.id, 600)
        is_time_limit_reached = elapsed_sec >= stage_limit_sec
        is_last_stage = self.current_stage_index >= len(self.active_stages) - 1

        should_propose_transition = False
        is_session_finishing = False
        is_transitioning = False

        if is_last_stage:
            if is_time_limit_reached or self.turns_in_current_stage >= 2:
                is_session_finishing = True
        else:
            if is_time_limit_reached:
                should_propose_transition = True
            elif cur_stage.id == StageId.WARMUP.value:
                if self.turns_in_current_stage >= 3:
                    should_propose_transition = True
            else:
                target_turns = self.get_target_turns_for_current_stage()
                if self.turns_in_current_stage >= target_turns:
                    should_propose_transition = True

        if should_propose_transition and not is_last_stage:
            is_transitioning = True
            self.is_waiting_stage_confirmation = True
            self.pending_transition_next_stage = self.active_stages[self.current_stage_index + 1]

        # Resolve câu hỏi ngân hàng kế tiếp TRƯỚC khi sinh câu hỏi mới để lượt
        # được liên kết thật với question_bank (hoặc None nếu không có).
        if not is_session_finishing:
            self._resolve_next_intent(exclude_used=True)
            await self._emit_question_context()

        # Chấm điểm + tracking câu trả lời vừa gửi, chạy nền để không chặn hội thoại.
        self._schedule_answer_evaluation(self.current_turn_id, clean_text)

        # Spawn background LLM streaming + sentence TTS pipeline
        self._active_task = asyncio.create_task(
            self._run_llm_and_tts_pipeline(
                is_transitioning=is_transitioning,
                is_session_finishing=is_session_finishing,
            ),
        )

    async def handle_stage_transition_confirm(self) -> None:
        if not self.is_waiting_stage_confirmation or not self.pending_transition_next_stage:
            await self.handle_next_stage()
            return

        await self.cancel_current_generation()
        self.current_stage_index += 1
        self.turns_in_current_stage = 0
        self.current_turn_id += 1
        next_stage = self.get_current_stage()
        self.stage_start_times[next_stage.id] = time.time()
        self.is_waiting_stage_confirmation = False
        self.pending_transition_next_stage = None

        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.STAGE_CHANGE.value,
                "stage_id": next_stage.id,
                "stage_index": self.current_stage_index + 1,
                "total_stages": len(self.active_stages),
                "stage_name": next_stage.name_vi if self.language == "vi" else next_stage.name_en,
                "turn_id": self.current_turn_id,
                "current_stage": self.get_current_stage_data(),
                "stages": self.get_all_stages_data(),
                "stage_max_seconds": self.stage_time_limits.get(next_stage.id, 600),
            })

        await self.set_state(VoiceSessionState.THINK)
        self._resolve_next_intent(exclude_used=True)
        await self._emit_question_context()
        prompt = self._build_opening_question()
        self._active_task = asyncio.create_task(
            self._stream_predefined_text(prompt),
        )

    async def handle_stage_transition_defer(self, continue_message: str | None = None) -> None:
        self.is_waiting_stage_confirmation = False
        self.pending_transition_next_stage = None
        await self.set_state(VoiceSessionState.LISTEN)

    async def handle_request_hint(self, question_id: int | None = None) -> None:
        if self.mock_mode == "strict":
            if self.connection.is_open():
                await self.connection.send_event({
                    "type": VoiceEventType.HINT_RESPONSE.value,
                    "hint_text": "Chế độ phỏng vấn thực chiến (Strict Mock) yêu cầu ứng viên tự lực giải quyết, không hỗ trợ gợi ý.",
                    "is_supported": False,
                })
            return

        question = ""
        if self.current_intent_ctx and self.current_intent_ctx.intent:
            question = self.current_intent_ctx.intent
        elif self.conversation_history:
            for m in reversed(self.conversation_history):
                if m.get("role") == "assistant":
                    question = m.get("content", "")
                    break

        hint_prompt = build_hint_prompt(
            question=question or "Câu hỏi phỏng vấn kỹ thuật",
            role=self.role_name,
            level=self.level,
            language=self.language,
        )
        hint_text = "Hãy áp dụng mô hình STAR: Nêu bối cảnh (S), nhiệm vụ cần giải quyết (T), giải pháp kỹ thuật bạn chọn (A) và kết quả đo lường được (R)."
        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": hint_prompt},
            ]
            chunks = []
            async for token in self.llm.stream_ai_tokens(messages):
                chunks.append(token)
            generated = "".join(chunks).strip()
            if generated:
                hint_text = generated
        except Exception:
            pass

        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.HINT_RESPONSE.value,
                "hint_text": hint_text,
                "is_supported": True,
                "turn_id": self.current_turn_id,
            })

    async def handle_next_stage(self) -> None:
        if self.current_stage_index < len(self.active_stages) - 1:
            await self.cancel_current_generation()
            self.current_stage_index += 1
            self.turns_in_current_stage = 0
            self.current_turn_id += 1
            next_stage = self.get_current_stage()
            self.stage_start_times[next_stage.id] = time.time()
            self.is_waiting_stage_confirmation = False
            self.pending_transition_next_stage = None

            if self.connection.is_open():
                await self.connection.send_event({
                    "type": VoiceEventType.STAGE_CHANGE.value,
                    "stage_id": next_stage.id,
                    "stage_index": self.current_stage_index + 1,
                    "total_stages": len(self.active_stages),
                    "stage_name": next_stage.name_vi if self.language == "vi" else next_stage.name_en,
                    "turn_id": self.current_turn_id,
                    "current_stage": self.get_current_stage_data(),
                    "stages": self.get_all_stages_data(),
                    "stage_max_seconds": self.stage_time_limits.get(next_stage.id, 600),
                })

            await self.set_state(VoiceSessionState.THINK)
            self._resolve_next_intent(exclude_used=True)
            await self._emit_question_context()
            prompt = self._build_opening_question()
            self._active_task = asyncio.create_task(
                self._stream_predefined_text(prompt),
            )

    async def cancel_current_generation(self) -> None:
        if self.current_generation_id:
            old_gen_id = self.current_generation_id
            self._cancelled_generation_ids.add(old_gen_id)
            self.current_generation_id = None

            if self._active_task and not self._active_task.done():
                self._active_task.cancel()
                try:
                    await asyncio.wait_for(self._active_task, timeout=0.2)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                self._active_task = None

            if self.connection.is_open():
                await self.connection.send_event({
                    "type": VoiceEventType.INTERRUPTED.value,
                    "generation_id": old_gen_id,
                    "turn_id": self.current_turn_id,
                })

    def _build_stage_instructions(
        self,
        is_transitioning: bool = False,
        is_session_finishing: bool = False,
    ) -> str:
        cur_stage = self.get_current_stage()
        is_vi = self.language == "vi"

        if is_transitioning:
            from_stage_id = cur_stage.id
            to_stage_id = (
                self.pending_transition_next_stage.id
                if self.pending_transition_next_stage
                else (
                    StageId.TECHNICAL.value
                    if cur_stage.id == StageId.WARMUP.value
                    else StageId.CLOSING.value
                )
            )
            return build_stage_transition_instruction(
                from_stage=from_stage_id,
                to_stage=to_stage_id,
                language=self.language,
                mock_mode=self.mock_mode,
            )

        situational_guard = None
        if cur_stage.id != StageId.WARMUP.value and self.current_intent_ctx:
            situational_guard = QuestionIntentComposer.build_situational_system_prompt(
                role=self.role_name,
                level=self.level,
                stage_key=cur_stage.id,
                intent_ctx=self.current_intent_ctx,
                language=self.language,
            )

        stage_desc = ""
        if is_session_finishing:
            stage_desc = (
                "Buổi phỏng vấn đã hoàn tất tất cả các chặng. "
                "Hãy đưa ra nhận xét tổng quát tích cực, gửi lời cảm ơn chân thành tới ứng viên và "
                "thông báo kết thúc buổi phỏng vấn. TUYỆT ĐỐI KHÔNG NÓI 'hết giờ'."
                if is_vi
                else "All interview stages are now complete. "
                "Provide a brief warm closing remark, thank the candidate sincerely, and conclude the interview session."
            )
        elif cur_stage.id == StageId.WARMUP.value:
            stage_desc = (
                f"Bạn là {self.persona_name}, người phỏng vấn vị trí {self.role_name} ({self.level}). "
                "Bạn đang ở Chặng 1: Khởi động & Phá băng (Warm-up). "
                "Mục tiêu: Trò chuyện xã giao, nhỏ to thân mật (small talk) về thời tiết, lộ trình đi lại, năng lượng, một tách cà phê hoặc giới thiệu bản thân nhẹ nhàng. "
                "Hãy phản hồi câu trả lời của ứng viên một cách tự nhiên, ấm áp (1-2 câu ngắn), duy trì cuộc trò chuyện cởi mở như hai người bạn đồng nghiệp. "
                "TUYỆT ĐỐI CẤM hỏi các câu hỏi kỹ thuật, kiến trúc hay chuyên môn ở chặng này."
                if is_vi
                else "You are in Stage 1: Warm-up & Greeting. "
                "Goal: establish a welcoming atmosphere, engage in light conversational small talk (weather, commute, energy, coffee, brief self-intro). "
                "DO NOT ask technical or engineering interview questions during this warm-up stage."
            )
        elif cur_stage.id == StageId.TECHNICAL.value:
            strict_note = (
                " Ở chế độ Thực chiến, hãy đào sâu bắt bẻ các lỗ hổng kỹ thuật và hỏi xoáy trade-offs."
                if self.mock_mode == "strict"
                else " Ở chế độ Hướng dẫn, hãy gợi mở cấu trúc STAR khi ứng viên bối rối."
            )
            stage_desc = (
                f"Bạn đang ở chặng: Phỏng vấn chuyên môn (Technical Interview).{strict_note} "
                f"Vị trí: {self.role_name} ({self.level}). "
                "Mục tiêu: Đào sâu vào kinh nghiệm thực tế, kiến trúc hệ thống, trade-offs kỹ thuật hoặc phương pháp STAR. "
                "Phản hồi súc tích, chuyên nghiệp (2-3 câu)."
                if is_vi
                else f"You are in the Technical Interview stage for {self.role_name} ({self.level}). "
                "Focus on engineering challenges, architecture decisions, trade-offs, and STAR methodology."
            )
        else:
            stage_desc = (
                f"Bạn đang ở chặng: Thỏa thuận & Chào kết (Closing & Q&A). "
                "Mục tiêu: Trả lời tự nhiên các câu hỏi của ứng viên đặt ra về doanh nghiệp, môi trường văn hóa, dự án kỹ thuật hoặc lộ trình phát triển."
                if is_vi
                else f"You are in the Closing & Negotiation stage. "
                "Address candidate questions regarding the team, career growth, or compensation expectations."
            )

        if situational_guard:
            return stage_desc + chr(10) + chr(10) + situational_guard
        return stage_desc

    async def _run_llm_and_tts_pipeline(
        self,
        is_transitioning: bool = False,
        is_session_finishing: bool = False,
        question_text: str | None = None,
    ) -> None:
        self._generation_counter += 1
        turn_id = self.current_turn_id if question_text is not None else self.current_turn_id + 1
        self.current_turn_id = turn_id
        gen_id = f"gen_{self.session_id}_{turn_id}_{self._generation_counter}"
        self.current_generation_id = gen_id
        turn_intent = self.current_intent_ctx

        splitter = StreamingSentenceSplitter(min_sentence_chars=12)
        full_ai_response: list[str] = []

        try:
            stage_instruction = self._build_stage_instructions(
                is_transitioning=is_transitioning,
                is_session_finishing=is_session_finishing,
            )

            messages: list[dict[str, str]] = []
            if self.system_prompt:
                messages.append({"role": "system", "content": self.system_prompt})
            messages.append({"role": "system", "content": stage_instruction})
            language_name = INTERVIEW_LANGUAGE_SETTINGS[self.language][0]
            messages.append({
                "role": "system",
                "content": (
                    f"Conduct this interview and respond exclusively in {language_name}. "
                    "This choice is independent of the job description, interface, and prior messages. "
                    "Keep the same interview topic and progression; do not restart the interview "
                    "or translate the entire job description. Preserve technical terms when appropriate."
                ),
            })
            if question_text is not None:
                messages.append({
                    "role": "system",
                    "content": (
                        "For this turn, only present the supplied interview question in the chosen language. "
                        "Preserve its meaning, do not answer it, and do not introduce additional questions."
                    ),
                })
            messages.extend(self.conversation_history[-8:])
            if question_text is not None:
                messages.append({"role": "user", "content": question_text})

            turn_audio_collector: dict[int, bytes] = {}
            synth_sem = asyncio.Semaphore(2)

            async def synthesize_one(idx: int, s_text: str):
                if self.is_generation_cancelled(gen_id):
                    return
                clean_s = sanitize_spoken_text(s_text)
                if not clean_s:
                    return
                if self.state != VoiceSessionState.SPEAK:
                    await self.set_state(VoiceSessionState.SPEAK)

                if self.connection.is_open():
                    await self.connection.send_event({
                        "type": VoiceEventType.SUBTITLE.value,
                        "sentence": clean_s,
                        "sentence_index": idx,
                        "generation_id": gen_id,
                        "turn_id": turn_id,
                    })

                chunks: list[bytes] = []
                async for audio_chunk in self.tts.synthesize_stream(clean_s, voice=self.voice, pitch=self.pitch):
                    if self.is_generation_cancelled(gen_id):
                        break
                    if audio_chunk:
                        chunks.append(audio_chunk)

                if chunks and not self.is_generation_cancelled(gen_id):
                    full_audio = b"".join(chunks)
                    turn_audio_collector[idx] = full_audio
                    if self.connection.is_open():
                        await self.connection.send_event({
                            "type": VoiceEventType.AUDIO.value,
                            "audio_chunk": full_audio,
                            "mime_type": "audio/mpeg",
                            "sentence_index": idx,
                            "generation_id": gen_id,
                            "turn_id": turn_id,
                        })

            async def worker_synth(idx: int, s_text: str):
                async with synth_sem:
                    await synthesize_one(idx, s_text)

            synth_tasks: list[asyncio.Task] = []

            async def produce_sentences() -> None:
                async for token in self.llm.stream_ai_tokens(messages):
                    if self.is_generation_cancelled(gen_id):
                        break
                    full_ai_response.append(token)
                    if self.connection.is_open():
                        await self.connection.send_event({
                            "type": VoiceEventType.AI_TOKEN.value,
                            "token": token,
                            "turn_id": turn_id,
                            "generation_id": gen_id,
                        })
                    for sentence in splitter.feed(token):
                        idx, s_text = sentence
                        synth_tasks.append(asyncio.create_task(worker_synth(idx, s_text)))

                if not self.is_generation_cancelled(gen_id):
                    for sentence in splitter.flush():
                        idx, s_text = sentence
                        synth_tasks.append(asyncio.create_task(worker_synth(idx, s_text)))

            await produce_sentences()
            if synth_tasks and not self.is_generation_cancelled(gen_id):
                await asyncio.gather(*synth_tasks, return_exceptions=True)

            # If not cancelled, record AI message in history and finalize turn
            if not self.is_generation_cancelled(gen_id):
                final_text = sanitize_spoken_text("".join(full_ai_response))
                ai_audio_url = None
                if turn_audio_collector:
                    full_turn_audio = b"".join(
                        turn_audio_collector[k] for k in sorted(turn_audio_collector.keys())
                    )
                    ai_audio_url = self._save_audio_file(turn_id, "ai", full_turn_audio)

                if final_text:
                    self.conversation_history.append({"role": "assistant", "content": final_text})
                    self._persist_ai_turn(turn_id, final_text, turn_intent, audio_url=ai_audio_url)

                if is_session_finishing:
                    await self.set_state(VoiceSessionState.COMPLETED)
                    if self.connection.is_open():
                        await self.connection.send_event({
                            "type": VoiceEventType.DONE.value,
                            "turn_id": turn_id,
                            "generation_id": gen_id,
                            "full_text": final_text,
                            "audio_url": ai_audio_url,
                            "is_completed": True,
                        })
                else:
                    if self.connection.is_open():
                        await self.connection.send_event({
                            "type": VoiceEventType.DONE.value,
                            "turn_id": turn_id,
                            "generation_id": gen_id,
                            "full_text": final_text,
                            "audio_url": ai_audio_url,
                            "total_sentences": splitter.sentence_index,
                            "is_completed": False,
                        })

                        if is_transitioning and self.pending_transition_next_stage:
                            next_stg = self.pending_transition_next_stage
                            cur_stg = self.get_current_stage()
                            await self.connection.send_event({
                                "type": VoiceEventType.STAGE_TRANSITION_PROPOSED.value,
                                "current_stage": cur_stg.id,
                                "next_stage": next_stg.id,
                                "stage_index": self.current_stage_index + 2,
                                "total_stages": len(self.active_stages),
                                "stage_name": next_stg.name_vi if self.language == "vi" else next_stg.name_en,
                                "turn_id": turn_id,
                                "elapsed_seconds": int(self.get_stage_elapsed_seconds(cur_stg.id)),
                                "stage_max_seconds": self.stage_time_limits.get(cur_stg.id, 600),
                                "summary_message": final_text,
                            })

                    await self.set_state(VoiceSessionState.LISTEN)

        except asyncio.CancelledError:
            return
        except Exception as exc:
            if self.connection.is_open():
                await self.connection.send_event({
                    "type": VoiceEventType.ERROR.value,
                    "message": str(exc),
                    "turn_id": turn_id,
                })
            await self.set_state(VoiceSessionState.LISTEN)

    async def _stream_sentence_tts(
        self,
        sentence_idx: int,
        sentence_text: str,
        generation_id: str,
        turn_id: int,
    ) -> None:
        if self.is_generation_cancelled(generation_id):
            return

        clean_text = sanitize_spoken_text(sentence_text)
        if not clean_text:
            return

        # Transition state to SPEAK on the first sentence
        if self.state != VoiceSessionState.SPEAK:
            await self.set_state(VoiceSessionState.SPEAK)

        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.SUBTITLE.value,
                "sentence": clean_text,
                "sentence_index": sentence_idx,
                "generation_id": generation_id,
                "turn_id": turn_id,
            })

        # Synthesize complete, natural sentence audio to prevent micro-chunk audio stuttering
        audio_chunks: list[bytes] = []
        async for audio_chunk in self.tts.synthesize_stream(clean_text, voice=self.voice, pitch=self.pitch):
            if self.is_generation_cancelled(generation_id):
                break
            if audio_chunk:
                audio_chunks.append(audio_chunk)

        if audio_chunks and not self.is_generation_cancelled(generation_id):
            full_sentence_audio = b"".join(audio_chunks)
            if self.connection.is_open():
                await self.connection.send_event({
                    "type": VoiceEventType.AUDIO.value,
                    "audio_chunk": full_sentence_audio,
                    "mime_type": "audio/mpeg",
                    "sentence_index": sentence_idx,
                    "generation_id": generation_id,
                    "turn_id": turn_id,
                })

    async def _stream_predefined_text(self, text: str) -> None:
        clean_text = sanitize_spoken_text(text)
        if self.language != "vi":
            await self._run_llm_and_tts_pipeline(question_text=clean_text)
            return
        self._generation_counter += 1
        gen_id = f"gen_{self.session_id}_{self.current_turn_id}_{self._generation_counter}"
        self.current_generation_id = gen_id
        turn_id = self.current_turn_id
        turn_intent = self.current_intent_ctx

        try:
            splitter = StreamingSentenceSplitter(min_sentence_chars=12)
            if self.connection.is_open():
                await self.connection.send_event({
                    "type": VoiceEventType.AI_TOKEN.value,
                    "token": clean_text,
                    "turn_id": turn_id,
                    "generation_id": gen_id,
                })

            sentences = list(splitter.feed(clean_text)) + list(splitter.flush())
            if not sentences:
                sentences = [(0, clean_text)]

            turn_audio_collector: dict[int, bytes] = {}
            for sentence_idx, sentence_text in sentences:
                if self.is_generation_cancelled(gen_id):
                    return
                # Stream sentence TTS and collect audio chunks
                if self.state != VoiceSessionState.SPEAK:
                    await self.set_state(VoiceSessionState.SPEAK)

                clean_sentence = sanitize_spoken_text(sentence_text)
                if not clean_sentence:
                    continue

                if self.connection.is_open():
                    await self.connection.send_event({
                        "type": VoiceEventType.SUBTITLE.value,
                        "sentence": clean_sentence,
                        "sentence_index": sentence_idx,
                        "generation_id": gen_id,
                        "turn_id": turn_id,
                    })

                chunks: list[bytes] = []
                async for audio_chunk in self.tts.synthesize_stream(clean_sentence, voice=self.voice, pitch=self.pitch):
                    if self.is_generation_cancelled(gen_id):
                        break
                    if audio_chunk:
                        chunks.append(audio_chunk)

                if chunks and not self.is_generation_cancelled(gen_id):
                    full_audio = b"".join(chunks)
                    turn_audio_collector[sentence_idx] = full_audio
                    if self.connection.is_open():
                        await self.connection.send_event({
                            "type": VoiceEventType.AUDIO.value,
                            "audio_chunk": full_audio,
                            "mime_type": "audio/mpeg",
                            "sentence_index": sentence_idx,
                            "generation_id": gen_id,
                            "turn_id": turn_id,
                        })

            if not self.is_generation_cancelled(gen_id):
                ai_audio_url = None
                if turn_audio_collector:
                    full_turn_audio = b"".join(
                        turn_audio_collector[k] for k in sorted(turn_audio_collector.keys())
                    )
                    ai_audio_url = self._save_audio_file(turn_id, "ai", full_turn_audio)

                self.conversation_history.append({"role": "assistant", "content": clean_text})
                self._persist_ai_turn(turn_id, clean_text, turn_intent, audio_url=ai_audio_url)
                if self.connection.is_open():
                    await self.connection.send_event({
                        "type": VoiceEventType.DONE.value,
                        "turn_id": turn_id,
                        "generation_id": gen_id,
                        "full_text": clean_text,
                        "audio_url": ai_audio_url,
                        "total_sentences": len(sentences),
                        "is_completed": False,
                    })
                await self.set_state(VoiceSessionState.LISTEN)
        except asyncio.CancelledError:
            return
        except Exception:
            logging.getLogger("VoiceOrchestrator").exception("Failed to speak interview question")
            if self.connection.is_open():
                await self.connection.send_event({
                    "type": VoiceEventType.ERROR.value,
                    "message": "Không thể phát giọng AI. Bạn vẫn có thể đọc câu hỏi và trả lời.",
                    "turn_id": turn_id,
                    "generation_id": gen_id,
                    "full_text": text,
                })
            await self.set_state(VoiceSessionState.LISTEN)

    def _resolve_next_intent(self, *, exclude_used: bool = False) -> None:
        if not self.session_factory:
            return
        cur_stage = self.get_current_stage()
        # Ở chặng Khởi động (Warm-up), KHÔNG gán câu hỏi chuyên môn từ JD hay ngân hàng câu hỏi!
        if cur_stage.id == StageId.WARMUP.value:
            self.current_intent_ctx = None
            return

        db = self.session_factory()
        try:
            # Check if this session was generated from a JD interview job
            try:
                from ...infrastructure.persistence.models.jd_interview import JDGenerationJob
                jd_job = db.query(JDGenerationJob).filter_by(session_id=self.session_id).first()
                if jd_job and jd_job.script and jd_job.script.items:
                    items = jd_job.script.items
                    stage_matched = [
                        item for item in items
                        if str(item.get("section_type", "")).lower() == cur_stage.id
                    ]
                    chosen = None
                    if stage_matched:
                        idx = min(self.turns_in_current_stage, len(stage_matched) - 1)
                        chosen = stage_matched[idx]
                    elif items:
                        idx = self.turns_in_current_stage % len(items)
                        chosen = items[idx]

                    if chosen:
                        # Câu hỏi sinh từ kịch bản JD, KHÔNG thuộc ngân hàng câu hỏi
                        # -> không gắn question_id để tránh gán kỹ năng sai.
                        self.current_intent_ctx = QuestionIntentContext(
                            question_id=None,
                            intent=chosen.get("question_text", ""),
                            stage_key=cur_stage.id,
                            difficulty=int(chosen.get("difficulty", 3)),
                            topic_label=chosen.get("competency_name") or chosen.get("section_type", "Chuyên môn"),
                        )
                        return
            except Exception:
                pass

            exclude_used_ids = (
                QuestionSelectionService.get_used_question_ids(db, self.session_id)
                if exclude_used else []
            )
            intents = QuestionSelectionService.sample_questions_for_stage(
                session=db,
                session_id=self.session_id,
                stage_key=cur_stage.id,
                source_mode="auto_random",
                target_count=1,
                exclude_used_ids=exclude_used_ids,
            )
            if intents:
                self.current_intent_ctx = intents[0]
                db.commit()
            else:
                # Hết câu hỏi phù hợp -> để AI hỏi tự do, KHÔNG liên kết bừa.
                self.current_intent_ctx = None
        except Exception:
            db.rollback()
        finally:
            db.close()

    async def handle_reroll_question(self) -> None:
        """
        Re-rolls current question by sampling a new approved question from the bank
        and restarting AI generation.
        """
        await self.cancel_current_generation()
        if (
            not self.session_factory
            or not self.current_intent_ctx
            or self.current_intent_ctx.question_id is None
        ):
            # Chỉ reroll được câu hỏi đến từ ngân hàng câu hỏi.
            return

        db = self.session_factory()
        try:
            cur_stage = self.get_current_stage()
            new_intent = QuestionSelectionService.reroll_question(
                session=db,
                session_id=self.session_id,
                stage_key=cur_stage.id,
                current_question_id=int(self.current_intent_ctx.question_id),
            )
            if new_intent:
                self.current_intent_ctx = new_intent
                db.commit()

                if self.connection.is_open():
                    await self.connection.send_event({
                        "type": VoiceEventType.QUESTION_REROLLED.value,
                        "question_id": new_intent.question_id,
                        "topic_label": new_intent.topic_label,
                        "stage_key": new_intent.stage_key,
                        "difficulty": new_intent.difficulty,
                    })

                await self.set_state(VoiceSessionState.THINK)
                prompt = self._build_opening_question()
                self._active_task = asyncio.create_task(
                    self._stream_predefined_text(prompt),
                )
        except Exception:
            db.rollback()
        finally:
            db.close()

    def _schedule_answer_evaluation(self, turn_number: int, answer_text: str) -> None:
        if not self.session_factory or not self.evaluation_service:
            return
        task = asyncio.create_task(
            self._evaluate_and_track_answer(turn_number, answer_text),
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _evaluate_and_track_answer(self, turn_number: int, answer_text: str) -> None:
        try:
            await asyncio.to_thread(
                self._evaluate_and_track_answer_sync, turn_number, answer_text,
            )
        except Exception as exc:
            logging.getLogger("VoiceOrchestrator").warning(
                "Failed to evaluate answer for turn #%d: %s", turn_number, exc,
            )

    def _evaluate_and_track_answer_sync(self, turn_number: int, answer_text: str) -> None:
        if not self.session_factory or not self.evaluation_service:
            return
        if getattr(self.evaluation_service, "evaluator", None) is None:
            return
        db = self.session_factory()
        try:
            from ...infrastructure.persistence.models.session import InterviewTurn as OrmInterviewTurn
            from ..evaluation.commands import EvaluateTurnCommand

            turn_rec = (
                db.query(OrmInterviewTurn)
                .filter_by(session_id=self.session_id, turn_number=turn_number)
                .first()
            )
            if turn_rec is None or not (turn_rec.message_text or "").strip():
                return
            self.evaluation_service.evaluate_turn(
                db,
                EvaluateTurnCommand(
                    session_id=self.session_id,
                    turn_id=turn_rec.turn_id,
                    question_text=turn_rec.message_text.strip(),
                    answer_text=answer_text,
                    role_name=self.role_name,
                    level=self.level,
                    language=self.language,
                ),
            )
            if turn_rec.question_id:
                from ..skills.service import UserSkillService
                UserSkillService(session=db).sync_interview_turn(self.session_id, turn_number)
        finally:
            db.close()

    def _schedule_session_tracking_sync(self) -> None:
        if not self.session_factory:
            return
        task = asyncio.create_task(asyncio.to_thread(self._sync_session_tracking_sync))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _sync_session_tracking_sync(self) -> None:
        db = self.session_factory()
        try:
            from ..skills.service import UserSkillService
            UserSkillService(session=db).sync_from_interview_session(self.session_id)
        except Exception as exc:
            logging.getLogger("VoiceOrchestrator").warning(
                "Failed to sync session tracking #%d: %s", self.session_id, exc,
            )
        finally:
            db.close()

    async def handle_stop_session(self) -> None:
        await self.cancel_current_generation()
        self._schedule_session_tracking_sync()
        await self.set_state(VoiceSessionState.COMPLETED)
        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.DONE.value,
                "turn_id": self.current_turn_id,
                "generation_id": self.current_generation_id or "",
                "is_completed": True,
            })

