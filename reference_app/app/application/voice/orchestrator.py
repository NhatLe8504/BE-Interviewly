from __future__ import annotations

from pathlib import Path

import asyncio
import json
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
from .ports import LLMVoiceStreamPort, TTSFallbackNotice, TTSPort, VoiceConnectionPort
from .sentence_splitter import StreamingSentenceSplitter
from ...infrastructure.llm.prompt_templates import (
    build_interviewer_system_prompt,
    build_dynamic_warmup_opening_text,
    build_stage_transition_instruction,
    build_hint_prompt,
    build_follow_up_user_prompt,
)
from .text_sanitizer import sanitize_spoken_text
from .adaptive_flow import create_snapshot, current_item, stage_progress, apply_judgment, advance_stage, skip_remaining, pause, resume, active_elapsed, is_candidate_cannot_answer, warmup_topic
from .turn_judge import InterviewTurnJudge, TurnJudgment
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
        turn_judge: InterviewTurnJudge | None = None,
    ) -> None:
        self.user_id = user_id
        self.turn_judge = turn_judge
        self.flow: dict[str, Any] | None = None
        self._judgment_task: asyncio.Task | None = None
        self._adaptive_probe_target: str | None = None
        self._awaiting_playback_id: str | None = None
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
        self.response_mode = "voice"
        self.browser_tts_fallback = False
        self._tts_user_browser_preference = False
        self._tts_browser_forced = False
        self._tts_backup_active = False
        self._tts_generation_id: str | None = None
        self._tts_fallback_notice_sent = False
        self._tts_attempted_synthesis = False
        self._tts_failed_this_turn = False
        self._tts_consecutive_failed_turns = 0
        self._tts_locked_fallback: str | None = None
        self._tts_consent_offer: tuple[str, str] | None = None
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
        if self.session_factory:
            db_chk = self.session_factory()
            try:
                from ...infrastructure.persistence.models.session import InterviewSession as DbInterviewSession
                from ...infrastructure.persistence.models.enums import SessionStatus
                s_row = db_chk.get(DbInterviewSession, self.session_id)
                if s_row and (s_row.status == SessionStatus.completed or str(s_row.status).lower() == "completed"):
                    self.state = VoiceSessionState.COMPLETED
            except Exception:
                pass
            finally:
                db_chk.close()
        self.current_turn_id: int = 1
        self.current_generation_id: str | None = None
        self._active_task: asyncio.Task | None = None
        self._generation_counter: int = 0
        self._cancelled_generation_ids: set[str] = set()
        self.conversation_history: list[dict[str, str]] = []
        self.stage_history: dict[str, list[dict[str, str]]] = {
            StageId.WARMUP.value: [],
            StageId.TECHNICAL.value: [],
            StageId.CLOSING.value: [],
        }
        self.stage_summaries: dict[str, str] = {}
        self._initial_opening_text: str | None = None
        self._has_unvoiced_opening: bool = False
        self._background_tasks: set[asyncio.Task] = set()

        self._load_flow()
        self._load_existing_turns_from_db()

    def _load_flow(self) -> None:
        if not self.session_factory:
            return
        db = self.session_factory()
        try:
            from ...infrastructure.persistence.models.session_plan import InterviewFlowState
            if hasattr(db, "get"):
                row = db.get(InterviewFlowState, self.session_id)
            else:
                row = db.query(InterviewFlowState).filter_by(session_id=self.session_id).first()
            if row and hasattr(row, "snapshot"):
                self.flow = row.snapshot
                pause(self.flow)
                self.current_stage_index = self.flow["stage_index"]
                self.active_stages = self._resolve_stages(self.flow["stages"])
                self.total_duration_minutes = self.flow["duration_minutes"]
                self.stage_time_limits = self.flow["budgets"]
        finally:
            db.close()

    def _save_flow(self) -> None:
        if not self.flow or not self.session_factory:
            return
        db = self.session_factory()
        try:
            from ...infrastructure.persistence.models.session_plan import InterviewFlowState
            if hasattr(db, "get"):
                row = db.get(InterviewFlowState, self.session_id)
            else:
                row = db.query(InterviewFlowState).filter_by(session_id=self.session_id).first()
            if row is None:
                db.add(InterviewFlowState(session_id=self.session_id, snapshot=self.flow))
            else:
                row.snapshot = self.flow
            db.commit()
        except Exception:
            db.rollback()
            logging.getLogger("VoiceOrchestrator").exception("Could not save interview flow")
            raise
        finally:
            db.close()

    def _initialize_flow(self) -> None:
        if self.flow:
            return
        script_items = []
        if self.session_factory:
            db = self.session_factory()
            try:
                from ...infrastructure.persistence.models.jd_interview import JDGenerationJob
                job = db.query(JDGenerationJob).filter_by(session_id=self.session_id).first()
                script_items = job.script.items if job and hasattr(job, "script") and job.script and hasattr(job.script, "items") and job.script.items else []
            finally:
                db.close()
        self.flow = create_snapshot(
            script_items, [stage.id for stage in self.active_stages],
            self.total_duration_minutes, self.language,
        )
        self.current_stage_index = 0
        self.stage_time_limits = self.flow["budgets"]
        if self.session_factory:
            self._save_flow()

    async def _emit_flow_progress(self) -> None:
        if self.flow and self.connection.is_open():
            await self.connection.send_event({"type": "interview_progress", **stage_progress(self.flow)})

    def _record_stage_turn(self, role: str, content: str) -> None:
        stage_id = self.get_current_stage().id
        self.stage_history.setdefault(stage_id, []).append({"role": role, "content": content})

    def get_scoped_conversation_history(self) -> list[dict[str, str]]:
        stage_id = self.get_current_stage().id
        scoped = self.stage_history.get(stage_id, [])
        if scoped:
            return scoped[-6:]
        return []

    def _summarize_warmup_stage(self) -> str:
        warmup_turns = self.stage_history.get(StageId.WARMUP.value, [])
        user_texts = [t["content"] for t in warmup_turns if t["role"] == "user"]
        combined = " ".join(user_texts)[:300]
        if combined:
            return f"Ứng viên ứng tuyển vị trí {self.role_name} ({self.level}). Tinh thần cởi mở, phong thái giao tiếp sẵn sàng."
        return f"Ứng viên sẵn sàng bước vào phần phỏng vấn chuyên môn vị trí {self.role_name}."

    def _summarize_technical_stage(self) -> str:
        return f"Ứng viên đã hoàn thành trao đổi các chủ đề phỏng vấn chuyên môn {self.role_name}."

    def _summarize_stage(self, stage_id: str) -> None:
        if stage_id == StageId.WARMUP.value:
            self.stage_summaries[StageId.WARMUP.value] = self._summarize_warmup_stage()
        elif stage_id == StageId.TECHNICAL.value:
            self.stage_summaries[StageId.TECHNICAL.value] = self._summarize_technical_stage()

    def _calculate_stage_time_limits(self, total_minutes: int) -> dict[str, int]:
        total_sec = max(300, int(total_minutes * 60))
        return {
            StageId.WARMUP.value: max(60, int(total_sec * (1 / 6))),
            StageId.TECHNICAL.value: max(180, int(total_sec * (4 / 6))),
            StageId.CLOSING.value: max(60, int(total_sec * (1 / 6))),
        }

    def get_stage_elapsed_seconds(self, stage_id: str) -> float:
        if self.flow and self.flow["stages"][self.flow["stage_index"]] == stage_id:
            return active_elapsed(self.flow)
        start = self.stage_start_times.get(stage_id)
        if start is None:
            return 0.0
        return max(0.0, time.time() - start)

    def _ensure_stage_timer_started(self, stage_id: str) -> None:
        if stage_id not in self.stage_start_times:
            self.stage_start_times[stage_id] = time.time()

    
    def _save_audio_file(self, turn_id: int, speaker: str, audio_bytes: bytes) -> str | None:
        try:
            from ...config import get_audio_storage_dir
            base_dir = get_audio_storage_dir()
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

            cur_stage_id = self.get_current_stage().id
            self.stage_history[cur_stage_id] = list(self.conversation_history[-8:])

            last_row = rows[-1]
            if last_row.transcribed_text and last_row.transcribed_text.strip():
                self.current_turn_id = last_row.turn_number + 1
                self._has_unvoiced_opening = False
            else:
                self.current_turn_id = last_row.turn_number
                self._has_unvoiced_opening = not bool(last_row.audio_url)
                if last_row.message_text:
                    self._initial_opening_text = last_row.message_text

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
                "question_type": self.current_intent_ctx.question_type,
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
        if self.flow:
            return stage_progress(self.flow)["total"]
        cur = self.get_current_stage()
        if cur.id in self.questions_per_stage:
            return self.questions_per_stage[cur.id]

        if cur.id == StageId.WARMUP.value:
            return 3  # Cho phép small talk 3 lượt tự nhiên

        if cur.id == StageId.TECHNICAL.value:
            total_questions = 4
            if self.session_factory:
                db = self.session_factory()
                try:
                    from ...infrastructure.persistence.models.jd_interview import JDGenerationJob
                    jd_job = db.query(JDGenerationJob).filter_by(session_id=self.session_id).first()
                    if jd_job and jd_job.script and jd_job.script.items:
                        tech_items = [
                            it for it in jd_job.script.items
                            if str(it.get("section_type", "")).lower() in ("technical", "chuyên môn", "coding", "system_design")
                        ]
                        total_questions = len(tech_items) if tech_items else len(jd_job.script.items)
                except Exception:
                    pass
                finally:
                    db.close()
            # Mỗi câu hỏi kỹ thuật có lượt câu hỏi chính + lượt phản biện hóc búa
            return max(6, total_questions * 2)

        return 3

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
                "turn_in_stage": stage_progress(self.flow)["completed"] + 1 if self.flow else self.turns_in_current_stage + 1,
                "target_turns_in_stage": self.get_target_turns_for_current_stage(),
            })

    def set_barge_in_enabled(self, enabled: bool) -> None:
        self.barge_in_enabled = enabled

    def set_browser_tts_preference(self, enabled: bool) -> None:
        if enabled != self._tts_user_browser_preference:
            self._clear_tts_fallback_choice()
        self._tts_user_browser_preference = enabled
        self.browser_tts_fallback = self._tts_browser_forced or enabled

    def _clear_tts_fallback_choice(self) -> None:
        self._tts_locked_fallback = None
        self._tts_consent_offer = None
        self._tts_consecutive_failed_turns = 0

    def set_voice(self, voice: str) -> None:
        if voice != self.voice:
            self._clear_tts_fallback_choice()
        self.voice = voice

    def restore_tts_fallback_choice(self, phase: str | None) -> None:
        if not self._tts_user_browser_preference and (
            phase == "browser" or (phase == "backup" and self.voice.startswith("vieneu:"))
        ):
            self._tts_locked_fallback = phase

    async def handle_tts_fallback_consent(self, generation_id: str | None, accepted: bool) -> None:
        if not self._tts_consent_offer or self._tts_consent_offer[0] != generation_id:
            return
        _, phase = self._tts_consent_offer
        self._tts_consent_offer = None
        self._tts_consecutive_failed_turns = 0
        if accepted:
            self._tts_locked_fallback = phase
        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.TTS_FALLBACK_CONSENT_RESULT.value,
                "generation_id": generation_id,
                "accepted": accepted,
                "phase": phase,
            })

    def _start_tts_generation(self, generation_id: str) -> None:
        self._tts_generation_id = generation_id
        self._tts_backup_active = self._tts_locked_fallback == "backup" and self.voice.startswith("vieneu:")
        self._tts_browser_forced = self._tts_locked_fallback == "browser"
        self.browser_tts_fallback = self._tts_user_browser_preference or self._tts_browser_forced
        self._tts_fallback_notice_sent = False
        self._tts_attempted_synthesis = False
        self._tts_failed_this_turn = False

    async def _finish_tts_generation(self, generation_id: str, *, finishing_session: bool = False) -> None:
        if generation_id != self._tts_generation_id or self.response_mode != "voice":
            return
        if not self._tts_attempted_synthesis or not self._tts_failed_this_turn:
            self._tts_consecutive_failed_turns = 0
            if self._tts_consent_offer:
                offered_generation, _ = self._tts_consent_offer
                self._tts_consent_offer = None
                if self.connection.is_open():
                    await self.connection.send_event({
                        "type": VoiceEventType.TTS_FALLBACK_CONSENT_RESULT.value,
                        "generation_id": offered_generation,
                        "accepted": False,
                        "recovered": True,
                    })
            return
        self._tts_consecutive_failed_turns += 1
        if (self._tts_consecutive_failed_turns < 2 or self._tts_consent_offer
                or self._tts_locked_fallback == "browser" or finishing_session):
            return
        phase = "browser" if self._tts_browser_forced else "backup"
        self._tts_consent_offer = (generation_id, phase)
        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.TTS_FALLBACK_CONSENT.value,
                "generation_id": generation_id,
                "turn_id": self.current_turn_id,
                "phase": phase,
            })

    def set_interview_language(self, language: str) -> None:
        if not isinstance(language, str) or language not in INTERVIEW_LANGUAGE_SETTINGS:
            raise DomainValidationError("Unsupported interview language")
        if language == self.language:
            return
        if self.state not in (VoiceSessionState.IDLE, VoiceSessionState.LISTEN):
            raise DomainValidationError("Change language while the interviewer is waiting for your answer")
        self.language = language
        self.set_voice(INTERVIEW_LANGUAGE_SETTINGS[language][1])
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

        if self.flow:
            item = current_item(self.flow)
            if item:
                return item["question"]
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
        response_mode: str | None = None,
        total_duration_minutes: int | None = None,
        browser_tts_fallback: bool = False,
        tts_fallback_lock: str | None = None,
    ) -> None:
        if self.state == VoiceSessionState.COMPLETED:
            if self.connection.is_open():
                await self.connection.send_event({
                    "type": VoiceEventType.STATE.value,
                    "state": VoiceSessionState.COMPLETED.value,
                    "is_completed": True,
                })
                await self.connection.send_event({
                    "type": VoiceEventType.DONE.value,
                    "turn_id": self.current_turn_id,
                    "is_completed": True,
                })
            return
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
        if response_mode in ("voice", "text"):
            self.response_mode = response_mode
        self.set_browser_tts_preference(browser_tts_fallback)
        if total_duration_minutes and not self.flow:
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
            self.set_voice(voice)
        self.restore_tts_fallback_choice(tts_fallback_lock)
        if pitch is not None:
            self.set_pitch(pitch)
        if barge_in_enabled is not None:
            self.barge_in_enabled = barge_in_enabled
        if questions_per_stage:
            self.questions_per_stage.update(questions_per_stage)
        if selected_stages and not self.flow:
            self.active_stages = self._resolve_stages(selected_stages)
            self.current_stage_index = 0
            self.turns_in_current_stage = 0
        self._initialize_flow()
        if self.flow:
            self.current_stage_index = self.flow["stage_index"]
            resume(self.flow)
            self._save_flow()
            if (not any(message["role"] == "user" for message in self.conversation_history)
                    and self.conversation_history and self.get_current_stage().id == StageId.WARMUP.value
                    and self._has_unvoiced_opening
                    and self.conversation_history[-1]["content"] != self._build_opening_question()):
                self.conversation_history.clear()

        cur_stg = self.get_current_stage()
        self._ensure_stage_timer_started(cur_stg.id)

        # Broadcast initial stage info
        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.STAGE_INFO.value,
                "current_stage": self.get_current_stage_data(),
                "stages": self.get_all_stages_data(),
                "turn_in_stage": stage_progress(self.flow)["completed"] + 1 if self.flow else self.turns_in_current_stage + 1,
                "target_turns_in_stage": self.get_target_turns_for_current_stage(),
                "stage_elapsed_seconds": int(self.get_stage_elapsed_seconds(cur_stg.id)),
                "stage_max_seconds": self.flow["budgets"][cur_stg.id] if self.flow else self.stage_time_limits.get(cur_stg.id, 600),
                "total_duration_minutes": self.total_duration_minutes,
                "mock_mode": self.mock_mode,
                "persona_name": self.persona_name,
                "company_name": self.company_name,
            })

        await self._emit_flow_progress()

        # Resolve intent for current stage if DB session is available
        self._resolve_next_intent()
        await self._emit_question_context()

        # Broadcast conversation history if available
        if self.conversation_history and self.connection.is_open():
            await self._broadcast_conversation_history()

        if self.flow and self.flow.get("pending"):
            await self._emit_pending_proposal()
            await self.set_state(VoiceSessionState.LISTEN)
            return

        if (self.flow and self.flow.get("last_received_turn", 0) > self.flow["last_turn"]
                and self.conversation_history and self.conversation_history[-1]["role"] == "user"):
            self.current_turn_id = self.flow["last_received_turn"]
            await self.set_state(VoiceSessionState.THINK)
            self._judgment_task = asyncio.create_task(self._process_adaptive_answer(
                self.current_turn_id, self.conversation_history[-1]["content"], self.flow["stage_version"],
            ))
            return

        if (self.flow and self.conversation_history and self.conversation_history[-1]["role"] == "user"):
            item = current_item(self.flow)
            if item:
                await self.set_state(VoiceSessionState.THINK)
                if item["status"] == "probing":
                    threshold = 1.0 if self.get_current_stage().id == StageId.WARMUP.value else 1.8
                    self._adaptive_probe_target = next(
                        (signal for signal in item["signals"]
                         if item["evidence"].get(signal, {}).get("score", 0) < threshold), item["signals"][0],
                    )
                    self.current_turn_id -= 1
                    self._active_task = asyncio.create_task(self._run_llm_and_tts_pipeline())
                else:
                    self._active_task = asyncio.create_task(self._run_llm_and_tts_pipeline(next_question_item=item))
                return

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
            item = current_item(self.flow) if self.flow else None
            if item and self.get_current_stage().id != StageId.WARMUP.value:
                self._active_task = asyncio.create_task(
                    self._run_llm_and_tts_pipeline(next_question_item=item, is_stage_opening=True),
                )
            else:
                self._active_task = asyncio.create_task(self._stream_predefined_text(self._build_opening_question()))
        else:
            await self.set_state(VoiceSessionState.LISTEN)

    async def handle_user_speech_start(self, *, force: bool = False) -> None:
        if self._judgment_task and not self._judgment_task.done():
            return
        if not force and not self.barge_in_enabled:
            return

        if self.state in (VoiceSessionState.SPEAK, VoiceSessionState.THINK) or (
            self._active_task and not self._active_task.done()
        ) or (force and self.current_generation_id):
            await self.cancel_current_generation()
            await self.set_state(VoiceSessionState.LISTEN)

    async def handle_interim_transcript(self, text: str) -> None:
        if (not (self._judgment_task and not self._judgment_task.done()) and
                self.barge_in_enabled and len(text.strip()) >= 2 and self.state in (
            VoiceSessionState.SPEAK, VoiceSessionState.THINK,
        )):
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

    async def handle_playback_completed(self, generation_id: str | None) -> None:
        if (generation_id and generation_id == self._awaiting_playback_id and
                generation_id == self.current_generation_id and self.state == VoiceSessionState.SPEAK):
            self._awaiting_playback_id = None
            await self.set_state(VoiceSessionState.LISTEN)

    @staticmethod
    def _is_greeting_only(text: str) -> bool:
        return text.lower().strip(" .,!?:;\n\t") in {
            "xin chào", "chào", "chào bạn", "chào anh", "chào chị", "hello", "hi", "hey",
        }

    @staticmethod
    def _is_transition_agreement(text: str, language: str = "vi") -> bool:
        clean = text.lower().strip(" .,!?:;\n\t")
        if any(word in clean for word in ("không", "chưa", "not yet", "no ", "but", "nhưng")):
            return False
        for filler in ("dạ ", "vâng ", "em ", "tôi ", "mình ", "ạ", " rồi", " nhé"):
            if clean.startswith(filler) or clean.endswith(filler):
                clean = clean.removeprefix(filler).removesuffix(filler).strip(" ,.!?")
        phrases = (
            {"đồng ý", "tôi đồng ý", "sẵn sàng", "tôi sẵn sàng", "dạ vâng", "vâng",
             "dạ được", "dạ ok", "ok", "okay", "chuyển chặng", "qua phần tiếp theo",
             "chuyển sang phần tiếp theo", "kết thúc phỏng vấn"}
            if language == "vi" else
            {"yes", "i agree", "ready", "i am ready", "next stage", "move on",
             "let's go", "sure", "proceed", "finish the interview"}
        )
        return clean in phrases

    async def handle_final_transcript(
        self, text: str, duration_seconds: float = 0.0, turn_id: int | None = None,
    ) -> None:
        if self.state == VoiceSessionState.COMPLETED:
            if self.connection.is_open():
                await self.connection.send_event({
                    "type": "error",
                    "message": "Phiên phỏng vấn đã kết thúc, không thể gửi câu trả lời mới.",
                    "is_completed": True,
                })
            return
        if not self.flow:
            self._initialize_flow()
        if self.flow and (self.state != VoiceSessionState.LISTEN or
                          (self._judgment_task and not self._judgment_task.done())):
            return
        clean_text = text.strip()
        if not clean_text:
            return

        if self.flow and (self.flow.get("last_received_turn", 0) >= self.current_turn_id or
                          (turn_id is not None and turn_id != self.current_turn_id)):
            return

        # Ensure any leftover generation is stopped
        await self.cancel_current_generation(emit_event=False)

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
        self._record_stage_turn("user", clean_text)
        self._persist_user_transcript(self.current_turn_id, clean_text)

        if self.flow:
            self.flow["last_received_turn"] = self.current_turn_id
            self._save_flow()
            pending = self.flow.get("pending")
            if pending:
                agrees = self._is_transition_agreement(clean_text, self.language)
                explicitly_skips = any(phrase in clean_text.lower() for phrase in (
                    "bỏ qua", "skip", "kết thúc phỏng vấn", "end the interview",
                )) and not any(phrase in clean_text.lower() for phrase in (
                    "không bỏ qua", "đừng bỏ qua", "don't skip", "do not skip",
                ))
                if (agrees and pending["reason"] != "overtime") or (explicitly_skips and len(clean_text) < 80):
                    await self.handle_stage_transition_confirm(pending["id"], pending["stage_version"])
                    return
                self.flow["pending"] = None
                self.flow["deferred"] = pending["reason"] == "ready"
                self.is_waiting_stage_confirmation = False
                self.pending_transition_next_stage = None
                self._save_flow()
                if self.connection.is_open():
                    await self.connection.send_event({"type": "stage_transition_deferred"})
            elif stage_progress(self.flow)["ready"] and self._is_transition_agreement(clean_text, self.language):
                await self._offer_adaptive_transition()
                return
            await self.set_state(VoiceSessionState.THINK)
            if self.get_current_stage().id == StageId.TECHNICAL.value:
                self._schedule_answer_evaluation(self.current_turn_id, clean_text)
            self._judgment_task = asyncio.create_task(
                self._process_adaptive_answer(self.current_turn_id, clean_text, self.flow["stage_version"])
            )
            return

    def pause_flow(self) -> None:
        if self.flow:
            pause(self.flow)
            self._save_flow()

    async def request_stage_transition(self) -> None:
        if not self.flow or self.flow.get("pending"):
            return
        if self.state not in (VoiceSessionState.LISTEN, VoiceSessionState.IDLE):
            return
        progress = stage_progress(self.flow)
        if not progress["ready"] and progress["elapsed_seconds"] < progress["target_seconds"]:
            await self._emit_flow_progress()
            return
        await self._offer_adaptive_transition()

    async def _emit_pending_proposal(self) -> None:
        if not self.flow or not self.flow.get("pending") or not self.connection.is_open():
            return
        pending = self.flow["pending"]
        progress = stage_progress(self.flow)
        common = {
            "proposal_id": pending["id"], "stage_version": pending["stage_version"],
            "reason": pending["reason"], "remaining_required": progress["remaining_required"],
            "turn_id": pending.get("turn_id", self.current_turn_id),
            "summary_message": pending.get("summary_message", ""),
        }
        if pending["kind"] == "end":
            await self.connection.send_event({"type": "session_end_proposed", **common})
            return
        next_stage = self.active_stages[self.current_stage_index + 1]
        current_stage = self.get_current_stage()
        await self.connection.send_event({
            "type": VoiceEventType.STAGE_TRANSITION_PROPOSED.value,
            **common, "current_stage": current_stage.id, "next_stage": next_stage.id,
            "stage_index": self.current_stage_index + 2,
            "total_stages": len(self.active_stages),
            "stage_name": next_stage.name_vi if self.language == "vi" else next_stage.name_en,
            "elapsed_seconds": progress["elapsed_seconds"], "stage_max_seconds": progress["target_seconds"],
        })

    async def _offer_adaptive_transition(self, closing_no_more: bool = False) -> None:
        if not self.flow or self.flow.get("pending"):
            return
        progress = stage_progress(self.flow)
        if not progress["ready"] and progress["elapsed_seconds"] < progress["target_seconds"]:
            return
        is_last = self.flow["stage_index"] == len(self.flow["stages"]) - 1
        reason = "ready" if progress["ready"] else "overtime"
        self.flow["pending"] = {
            "id": uuid.uuid4().hex, "stage_version": self.flow["stage_version"],
            "kind": "end" if is_last else "stage",
            "reason": reason, "turn_id": self.current_turn_id + 1,
        }
        self._save_flow()
        await self._emit_flow_progress()
        await self.set_state(VoiceSessionState.THINK)
        if reason == "overtime":
            text = (
                f"Mình còn {progress['remaining_required']} nội dung cần trao đổi. "
                "Bạn muốn tiếp tục để hoàn thành, hay bỏ qua các mục còn lại và chuyển phần?"
                if self.language == "vi" else
                f"We have {progress['remaining_required']} topics left. Would you like to continue, "
                "or skip them and move on?"
            )
            self.current_turn_id += 1
            self._active_task = asyncio.create_task(self._stream_predefined_text(text))
        elif is_last:
            self.current_turn_id += 1
            text = (
                ("Nếu đã sẵn sàng, bạn có thể xác nhận kết thúc buổi phỏng vấn."
                 if closing_no_more else
                 "Các nội dung chính đã được trao đổi đầy đủ. Bạn còn thắc mắc nào về công việc hoặc phần trao đổi "
                 "vừa rồi không? Nếu đã đủ, bạn có thể xác nhận kết thúc buổi phỏng vấn.")
                if self.language == "vi" else
                ("You can confirm the end of the interview whenever you're ready."
                 if closing_no_more else
                 "We have covered all main topics. Do you have questions about the role or our discussion? "
                 "If not, you can confirm the end of the interview.")
            )
            self._active_task = asyncio.create_task(self._stream_predefined_text(text))
        else:
            self.is_waiting_stage_confirmation = True
            self.pending_transition_next_stage = self.active_stages[self.current_stage_index + 1]
            self._active_task = asyncio.create_task(self._run_llm_and_tts_pipeline(is_transitioning=True))

    async def _process_adaptive_answer(self, turn_id: int, answer: str, version: int) -> None:
        if not self.flow or self.flow["stage_version"] != version:
            return
        item = current_item(self.flow)
        if item:
            if (self.get_current_stage().id == StageId.WARMUP.value and
                    (self._is_greeting_only(answer) or not item.get("last_asked_question"))):
                self.flow["last_turn"] = turn_id
                self._save_flow()
                await self._emit_flow_progress()
                self.current_turn_id += 1
                self._active_task = asyncio.create_task(
                    self._run_llm_and_tts_pipeline(next_question_item=item, disposition="greeting"),
                )
                return
            judgment = TurnJudgment()
            if self.turn_judge:
                judgment = await asyncio.to_thread(
                    self.turn_judge.judge, item.get("last_asked_question") or item["question"],
                    item["signals"],
                    item["evidence"], answer,
                    [{"role": "candidate", "content": previous["text"]} for previous in item.get("answers", [])[-4:]],
                )
            if (self.state == VoiceSessionState.COMPLETED or not self.flow or
                    self.flow["stage_version"] != version or self.flow.get("current_item") != item["id"]):
                return
            if self.get_current_stage().id == StageId.CLOSING.value:
                self.flow["last_turn"] = turn_id
                item.setdefault("answers", []).append({"turn_id": turn_id, "text": answer[:2000]})
                no_questions = any(phrase in answer.lower() for phrase in (
                    "không còn câu hỏi", "không có câu hỏi", "không còn thắc mắc",
                    "không còn gì", "no more questions", "no questions", "nothing else to ask", "that's all",
                ))
                if judgment.explicitly_no_more or no_questions:
                    skip_remaining(self.flow, "candidate_has_no_more_questions")
                    self._save_flow()
                    await self._emit_flow_progress()
                    await self._offer_adaptive_transition(closing_no_more=True)
                else:
                    self._save_flow()
                    await self._emit_flow_progress()
                    self._adaptive_probe_target = (
                        "Answer the candidate's latest question naturally and accurately. "
                        "Then ask whether they have any other questions. Do not end the interview."
                    )
                    self.current_turn_id += 1
                    self._active_task = asyncio.create_task(self._run_llm_and_tts_pipeline())
                return
            action, target = apply_judgment(self.flow, judgment, turn_id, answer)
            self._save_flow()
            await self._emit_flow_progress()
            if action in ("probe", "probe_warmup"):
                self._adaptive_probe_target = target
                self.current_turn_id += 1
                self._active_task = asyncio.create_task(self._run_llm_and_tts_pipeline())
                return
            if action == "ignore":
                return
        if self.flow.pop("deferred", False) and stage_progress(self.flow)["ready"]:
            self._save_flow()
            self._adaptive_probe_target = "Respond to the candidate's latest point and remain in this stage; do not propose a transition yet."
            self.current_turn_id += 1
            self._active_task = asyncio.create_task(self._run_llm_and_tts_pipeline())
            return
        progress = stage_progress(self.flow)
        if progress["elapsed_seconds"] >= progress["target_seconds"]:
            await self._offer_adaptive_transition()
            return
        if progress["ready"]:
            await self.set_state(VoiceSessionState.THINK)
            if item is None:
                self._adaptive_probe_target = "Answer the candidate's latest point naturally; do not begin a new topic or change stages."
                self.current_turn_id += 1
                self._active_task = asyncio.create_task(self._run_llm_and_tts_pipeline())
            else:
                self.current_turn_id += 1
                text = (
                    "Các nội dung của phần này đã được trao đổi đầy đủ. Nếu muốn chia sẻ thêm, "
                    "mình vẫn đang lắng nghe; khi sẵn sàng, bạn có thể đề nghị chuyển phần."
                    if self.language == "vi" else
                    "We have covered the planned topics for this section. You can add anything else, "
                    "or ask to move on when you are ready."
                )
                self._active_task = asyncio.create_task(self._stream_predefined_text(text))
            return
        self._resolve_next_intent(exclude_used=True)
        await self._emit_question_context()
        next_item = current_item(self.flow)
        if next_item:
            self.current_turn_id += 1
            await self.set_state(VoiceSessionState.THINK)
            is_cannot = (
                judgment.disposition == "cannot_answer"
                or (item and item.get("reason") in ("candidate_cannot_answer", "probe_limit_or_candidate_cannot_answer"))
                or is_candidate_cannot_answer(answer)
            )
            disposition_val = "cannot_answer" if is_cannot else judgment.disposition
            self._active_task = asyncio.create_task(
                self._run_llm_and_tts_pipeline(
                    next_question_item=next_item,
                    previous_item=item,
                    disposition=disposition_val,
                )
            )

    async def handle_stage_transition_confirm(self, proposal_id: str | None = None, stage_version: int | None = None) -> None:
        if self.flow:
            pending = self.flow.get("pending")
            if (not pending or not proposal_id or stage_version is None or
                    self.state != VoiceSessionState.LISTEN or
                    pending["stage_version"] != self.flow["stage_version"] or
                    pending["id"] != proposal_id or stage_version != self.flow["stage_version"]):
                return
            if pending["kind"] == "end":
                if pending["reason"] == "overtime":
                    skip_remaining(self.flow, "candidate_confirmed_overtime_skip")
                await self.handle_stop_session()
                return
            await self.cancel_current_generation()
            if pending["reason"] == "overtime":
                skip_remaining(self.flow, "candidate_confirmed_overtime_skip")
            prev_stage = self.get_current_stage()
            self._summarize_stage(prev_stage.id)
            advance_stage(self.flow)
            self._save_flow()
            self.current_stage_index = self.flow["stage_index"]
            self.turns_in_current_stage = 0
            self.current_turn_id += 1
            self.is_waiting_stage_confirmation = False
            self.pending_transition_next_stage = None
            next_stage = self.get_current_stage()
            if self.connection.is_open():
                await self.connection.send_event({
                    "type": VoiceEventType.STAGE_CHANGE.value, "stage_id": next_stage.id,
                    "stage_index": self.current_stage_index + 1,
                    "current_stage": self.get_current_stage_data(),
                    "stages": self.get_all_stages_data(), "turn_id": self.current_turn_id,
                    "stage_max_seconds": self.flow["budgets"][next_stage.id],
                    "stage_elapsed_seconds": 0,
                })
            await self._emit_flow_progress()
            await self.set_state(VoiceSessionState.THINK)
            self._resolve_next_intent()
            await self._emit_question_context()
            first_item = current_item(self.flow)
            if first_item:
                self._active_task = asyncio.create_task(
                    self._run_llm_and_tts_pipeline(
                        next_question_item=first_item,
                        is_stage_opening=True,
                    )
                )
            else:
                self._active_task = asyncio.create_task(self._stream_predefined_text(self._build_opening_question()))
            return
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

    async def handle_stage_transition_defer(
        self, continue_message: str | None = None,
        proposal_id: str | None = None, stage_version: int | None = None,
    ) -> None:
        if self.flow:
            pending = self.flow.get("pending")
            if (not pending or pending["id"] != proposal_id or
                    pending["stage_version"] != stage_version or self.state != VoiceSessionState.LISTEN):
                return
            self.flow["pending"] = None
            self.flow["deferred"] = pending["reason"] == "ready"
            self._save_flow()
            await self._emit_flow_progress()
        self.is_waiting_stage_confirmation = False
        self.pending_transition_next_stage = None
        await self.set_state(VoiceSessionState.LISTEN)
        if self.connection.is_open():
            await self.connection.send_event({"type": "stage_transition_deferred"})

    async def handle_request_hint(self, question_id: int | None = None) -> None:
        if self.mock_mode == "strict":
            if self.connection.is_open():
                await self.connection.send_event({
                    "type": VoiceEventType.HINT_RESPONSE.value,
                    "hint_text": "Chế độ phỏng vấn thực chiến (Strict Mock) yêu cầu ứng viên tự lực giải quyết, không hỗ trợ gợi ý.",
                    "is_supported": False,
                    "hint_kind": "none",
                    "turn_id": self.current_turn_id,
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

        from ...domain.answer_framework import answer_framework, hint_fallback

        framework = answer_framework(self.current_intent_ctx.question_type if self.current_intent_ctx else None)
        hint_prompt = build_hint_prompt(
            question=question or "Câu hỏi phỏng vấn kỹ thuật",
            role=self.role_name,
            level=self.level,
            language=self.language,
            framework=framework,
        )
        hint_text = hint_fallback(framework, self.language)
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
                "hint_kind": framework,
                "is_supported": True,
                "turn_id": self.current_turn_id,
            })

    async def handle_next_stage(self) -> None:
        if self.flow:
            await self.request_stage_transition()
            return
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

    async def cancel_current_generation(self, emit_event: bool = True) -> None:
        if self.current_generation_id:
            old_gen_id = self.current_generation_id
            self._cancelled_generation_ids.add(old_gen_id)
            self.current_generation_id = None
            was_playing = self._awaiting_playback_id == old_gen_id
            self._awaiting_playback_id = None

            had_task = self._active_task is not None
            if self._active_task and not self._active_task.done():
                self._active_task.cancel()
                try:
                    await asyncio.wait_for(self._active_task, timeout=0.2)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                self._active_task = None

            if emit_event and self.connection.is_open() and (was_playing or had_task):
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
            is_follow_up = (self.turns_in_current_stage % 2 == 1)
            strict_note = (
                " Ở chế độ Thực chiến, hãy đào sâu bắt bẻ các lỗ hổng kỹ thuật và hỏi xoáy trade-offs."
                if self.mock_mode == "strict"
                else " Ở chế độ Hướng dẫn, chỉ gợi mở theo loại câu hỏi hiện tại khi ứng viên xin gợi ý."
            )
            follow_up_note = (
                (" Chỉ phản hồi tự nhiên; không tự chuyển câu hoặc chặng." if not current_item(self.flow) else
                 " Chỉ phản hồi ngắn và hỏi sâu đúng điểm còn thiếu; không tự chuyển câu hoặc chặng.")
                if self.flow else
                f" ĐÂY LÀ LƯỢT PHẢN BIỆN: Phân tích ngắn gọn câu trả lời vừa rồi của ứng viên (1 câu) và đặt một câu hỏi đào sâu hóc búa, thử thách phản biện về trade-offs, edge cases hoặc đánh đố giải pháp phù hợp với level {self.level}."
                if is_follow_up
                else " ĐÂY LÀ CÂU HỎI KỸ THUẬT MỚI: Dẫn dắt ngắn gọn và đặt câu hỏi chuyên môn tiếp theo."
            )
            stage_desc = (
                f"Bạn đang ở chặng: Phỏng vấn chuyên môn (Technical Interview).{strict_note}{follow_up_note} "
                f"Vị trí: {self.role_name} ({self.level}). "
                "Mục tiêu: Đào sâu vào kinh nghiệm thực tế, kiến trúc hệ thống, trade-offs kỹ thuật hoặc cách kiểm chứng giải pháp. "
                "Phản hồi súc tích, chuyên nghiệp (2-3 câu)."
                if is_vi
                else f"You are in the Technical Interview stage for {self.role_name} ({self.level}). "
                "Focus on engineering challenges, architecture decisions, trade-offs, and verification."
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
        next_question_item: dict[str, Any] | None = None,
        previous_item: dict[str, Any] | None = None,
        disposition: str | None = None,
        is_stage_opening: bool = False,
    ) -> None:
        self._generation_counter += 1
        turn_id = self.current_turn_id if question_text is not None else self.current_turn_id + 1
        self.current_turn_id = turn_id
        gen_id = f"gen_{self.session_id}_{turn_id}_{self._generation_counter}"
        self.current_generation_id = gen_id
        self._start_tts_generation(gen_id)
        turn_intent = self.current_intent_ctx

        splitter = StreamingSentenceSplitter(min_sentence_chars=12)
        full_ai_response: list[str] = []

        try:
            cur_stage = self.get_current_stage()
            messages: list[dict[str, str]] = []
            if cur_stage.id == StageId.WARMUP.value and not self._custom_system_prompt:
                messages.append({"role": "system", "content": (
                    f"Bạn là {self.persona_name}, người phỏng vấn vị trí {self.role_name} ({self.level}). "
                    "Ở chặng khởi động, chỉ trò chuyện thân thiện về kinh nghiệm và định hướng tổng quan. "
                    "Mỗi lượt chỉ hỏi một ý nhẹ nhàng, không kiểm tra kiến thức kỹ thuật, "
                    "không yêu cầu chi tiết kiến trúc, số liệu hay giải pháp. "
                    "CẤM TUYỆT ĐỐI mở đầu bằng 'Cảm ơn bạn đã chia sẻ' hoặc các câu cảm ơn máy móc. "
                    "Hãy mở lời tự nhiên như người thật ('Tôi hiểu rồi...', 'À ra vậy...', 'Được rồi...', hoặc đi thẳng vào ý tiếp theo). "
                    "Chỉ nói văn bản thuần túy."
                )})
            elif self.system_prompt:
                messages.append({"role": "system", "content": self.system_prompt})

            cur_stage_name = cur_stage.name_vi if self.language == "vi" else cur_stage.name_en
            stage_ctx = f"Giai đoạn hiện tại: {cur_stage_name}."
            if cur_stage.id != StageId.WARMUP.value and self.stage_summaries.get(StageId.WARMUP.value):
                stage_ctx += f"\nThông tin ứng viên từ vòng Khởi động: {self.stage_summaries[StageId.WARMUP.value]}"
            if cur_stage.id == StageId.CLOSING.value and self.stage_summaries.get(StageId.TECHNICAL.value):
                stage_ctx += f"\nTóm tắt vòng Kỹ thuật: {self.stage_summaries[StageId.TECHNICAL.value]}"
            messages.append({"role": "system", "content": stage_ctx})

            language_name = INTERVIEW_LANGUAGE_SETTINGS[self.language][0]
            terminology_note = (
                "Chỉ dùng thuật ngữ công việc khi ứng viên tự đề cập; không đặt câu hỏi chuyên môn. "
                if cur_stage.id == StageId.WARMUP.value else
                "Giữ nguyên các thuật ngữ kỹ thuật chuyên ngành phù hợp (ví dụ: Collections, Thread, Stream API, OOP, interface, v.v.). "
            )
            convo_rules = (
                "Nói năng tự nhiên, hòa nhã, có ngữ điệu đàm thoại thực tế như một người phỏng vấn công nghệ cao cấp. "
                "CẤM TUYỆT ĐỐI mở đầu câu bằng 'Cảm ơn bạn đã chia sẻ' hoặc các câu cảm ơn lặp đi lặp lại. "
                "Thay vào đó hãy tiếp nối tự nhiên bằng các câu đệm như 'Tôi hiểu rồi', 'À ra vậy', 'Thú vị đấy', 'Được rồi', hoặc hỏi thẳng vào vấn đề."
                if self.language == "vi" else
                "Converse naturally and professionally. NEVER start turns with repetitive robotic fillers like 'Thank you for sharing'. "
                "Use natural transitions like 'I see', 'Got it', 'Alright', or ask directly."
            )
            messages.append({
                "role": "system",
                "content": (
                    f"Thực hiện phỏng vấn và trao đổi tự nhiên bằng {language_name}. "
                    f"{terminology_note}"
                    f"{convo_rules}"
                ),
            })

            scoped_history = self.get_scoped_conversation_history()
            if cur_stage.id == StageId.WARMUP.value:
                messages.extend([turn for turn in scoped_history if turn["role"] == "user"][-1:])
            else:
                messages.extend(scoped_history[-6:])

            if next_question_item:
                bridge = (
                    "Mở đầu chặng mới thật ngắn rồi hỏi một ý." if is_stage_opening else
                    "Ứng viên chưa trả lời được ý vừa rồi; ghi nhận nhẹ nhàng rồi chuyển chủ đề, không cảm ơn khách sáo." if disposition == "cannot_answer" else
                    "Đáp lời ứng viên thân thiện không rập khuôn, rồi hỏi tiếp." if disposition == "greeting" else
                    "Nối tiếp tự nhiên từ ý của ứng viên (CẤM dùng 'Cảm ơn bạn đã chia sẻ') rồi chuyển chủ đề." if previous_item else
                    "Bắt đầu trao đổi tự nhiên."
                )
                if cur_stage.id == StageId.WARMUP.value:
                    messages.append({"role": "system", "content": (
                        f"{bridge} Nội dung khởi động: {warmup_topic(next_question_item, self.language)} "
                        "Chỉ hỏi một câu ngắn để hiểu sơ qua, không đòi dự án cụ thể, "
                        "công nghệ chi tiết, kết quả đo lường hay cách triển khai. "
                        "Nếu ứng viên nhắc tới kỹ thuật, chỉ ghi nhận và quay lại trò chuyện tổng quan."
                    )})
                elif cur_stage.id == StageId.CLOSING.value:
                    messages.append({"role": "system", "content": (
                        f"{bridge} Hỏi ứng viên một cách tự nhiên: {next_question_item['question']} "
                        "Đây là phần hỏi đáp, không đặt thêm câu hỏi đánh giá kỹ thuật."
                    )})
                else:
                    context = json.dumps({
                        "reference_question": next_question_item["question"],
                        "expected_signals": next_question_item["signals"],
                    }, ensure_ascii=False)
                    messages.append({"role": "system", "content": (
                        f"{bridge} Đây là nội dung tham chiếu từ kịch bản JD, không đọc nguyên văn "
                        "một câu dài gồm nhiều vế. Đặt MỘT câu hỏi mở đầu ngắn về trọng tâm phù hợp nhất; "
                        "expected_signals chỉ để định hướng đánh giá, không hỏi hết các ý cùng lúc. "
                        "Chờ ứng viên trả lời; lượt đào sâu tiếp theo do bộ đánh giá quyết định.\n" + context
                    )})
            elif question_text is not None:
                messages.append({
                    "role": "system",
                    "content": (
                        f"Hãy trình bày câu hỏi sau một cách tự nhiên, rõ ràng, giữ trọn vẹn yêu cầu chuyên môn:\n"
                        f"\"{question_text}\""
                    ),
                })
            elif self.flow and self._adaptive_probe_target and not is_transitioning:
                instruction = self._adaptive_probe_target
                self._adaptive_probe_target = None
                if cur_stage.id == StageId.WARMUP.value:
                    messages.append({"role": "system", "content": (
                        "Ứng viên vừa trả lời, nhưng nội dung sau vẫn chưa rõ: "
                        f"{instruction}. Tiếp lời tự nhiên dựa trên điều họ thực sự vừa nói (CẤM dùng 'Cảm ơn bạn đã chia sẻ'), "
                        "rồi hỏi MỘT câu ngắn để họ giải thích thêm ở mức tổng quan. Nếu họ chỉ nói 'không' hoặc trả lời ngắn, "
                        "hỏi lại nhẹ nhàng, không cảm ơn như thể đã trả lời xong. Không đòi ví dụ dự án, cách triển khai, số liệu "
                        "hay kiến thức kỹ thuật; không tự chuyển sang nội dung hoặc chặng khác."
                    )})
                else:
                    messages.append({
                        "role": "system",
                        "content": (
                            "Ứng viên vừa trả lời ý hiện tại của câu hỏi.\n"
                            f"Khía cạnh kỹ thuật cần đào sâu/làm rõ: {instruction}.\n"
                            f"Chỉ dẫn:\n"
                            f"1. Phản hồi tự nhiên hoặc ghi nhận nhanh điểm đáng chú ý trong câu trả lời (1 mệnh đề ngắn, CẤM mở đầu bằng 'Cảm ơn bạn đã chia sẻ').\n"
                            f"2. Đặt đúng một câu hỏi đào sâu tự nhiên, xoáy thẳng vào khía cạnh còn thiếu ({instruction}) để kiểm tra chiều sâu hiểu biết của ứng viên. Không hỏi sang các ý khác.\n"
                            "3. Giữ phong thái thân thiện, sắc sảo, không lặp lại nguyên văn câu hỏi gốc."
                        ),
                    })
            elif is_transitioning:
                messages.append({
                    "role": "system",
                    "content": (
                        f"Phần {cur_stage_name} đã trao đổi đầy đủ các nội dung.\n"
                        f"Đánh giá tích cực ngắn gọn (1 câu) và hỏi ứng viên xem họ đã sẵn sàng chuyển sang phần tiếp theo chưa."
                    ),
                })
            elif is_session_finishing:
                messages.append({
                    "role": "system",
                    "content": (
                        "Buổi phỏng vấn đã hoàn tất tất cả các phần. Cảm ơn ứng viên chân thành, chúc may mắn và thông báo kết thúc một cách ấm áp, chuyên nghiệp."
                    ),
                })
            elif cur_stage.id == StageId.WARMUP.value:
                messages.append({
                    "role": "system",
                    "content": (
                        "Bạn đang trò chuyện khởi động (small talk) với ứng viên. "
                        "Hãy lắng nghe và phản hồi câu trả lời của ứng viên một cách vui vẻ, ấm áp, tự nhiên như hai người bạn đồng nghiệp (1-2 câu). "
                        "Tiếp tục cuộc trò chuyện phá băng nhẹ nhàng. Tuyệt đối không hỏi câu hỏi kỹ thuật hay chuyên môn ở vòng này."
                    ),
                })
            elif cur_stage.id == StageId.CLOSING.value:
                messages.append({
                    "role": "system",
                    "content": (
                        "Ứng viên đang đặt câu hỏi trong phần Chào kết & Hỏi đáp. "
                        "Hãy giải đáp câu hỏi của ứng viên một cách tự nhiên, chân thành, cởi mở về văn hóa, dự án hoặc quy trình làm việc (2-3 câu). "
                        "Sau đó hỏi ứng viên xem họ còn câu hỏi hay thắc mắc nào khác nữa không."
                    ),
                })

            turn_audio_collector: dict[int, bytes] = {}
            missing_audio_sentences: list[str] = []

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

                full_audio = await self._synthesize_sentence_audio(clean_s, idx, gen_id, turn_id)
                if self.is_generation_cancelled(gen_id):
                    return
                if full_audio is None:
                    missing_audio_sentences.append(clean_s)
                    return

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

            async def worker_synth(idx: int, s_text: str, previous: asyncio.Task[None] | None):
                if previous:
                    await previous
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
                        if self.response_mode == "voice":
                            previous = synth_tasks[-1] if synth_tasks else None
                            synth_tasks.append(asyncio.create_task(worker_synth(idx, s_text, previous)))

                if not self.is_generation_cancelled(gen_id):
                    for sentence in splitter.flush():
                        idx, s_text = sentence
                        if self.response_mode == "voice":
                            previous = synth_tasks[-1] if synth_tasks else None
                            synth_tasks.append(asyncio.create_task(worker_synth(idx, s_text, previous)))

            await produce_sentences()
            if synth_tasks and not self.is_generation_cancelled(gen_id):
                await asyncio.gather(*synth_tasks)

            # If not cancelled, record AI message in history and finalize turn
            if not self.is_generation_cancelled(gen_id):
                await self._finish_tts_generation(gen_id, finishing_session=is_session_finishing)
                final_text = sanitize_spoken_text("".join(full_ai_response))
                ai_audio_url = None
                if turn_audio_collector and not missing_audio_sentences:
                    full_turn_audio = b"".join(
                        turn_audio_collector[k] for k in sorted(turn_audio_collector.keys())
                    )
                    ai_audio_url = self._save_audio_file(turn_id, "ai", full_turn_audio)

                if final_text:
                    self.conversation_history.append({"role": "assistant", "content": final_text})
                    self._record_stage_turn("assistant", final_text)
                    self._persist_ai_turn(turn_id, final_text, turn_intent, audio_url=ai_audio_url)
                    if self.flow and not is_transitioning:
                        spoken_item = current_item(self.flow)
                        if spoken_item and spoken_item["stage"] == cur_stage.id:
                            spoken_item["last_asked_question"] = final_text
                            self._save_flow()

                if is_session_finishing:
                    persisted = await asyncio.to_thread(self._persist_session_completion)
                    if persisted:
                        await self.set_state(VoiceSessionState.COMPLETED)
                        self._schedule_session_tracking_sync()
                        self._schedule_audio_cleanup(delay_seconds=120)
                        if self.connection.is_open():
                            await self.connection.send_event({
                                "type": VoiceEventType.DONE.value,
                                "turn_id": turn_id,
                                "generation_id": gen_id,
                                "full_text": final_text,
                                "audio_url": ai_audio_url,
                                "missing_audio_sentences": missing_audio_sentences,
                                "is_completed": True,
                            })
                    else:
                        if self.connection.is_open():
                            await self.connection.send_event({
                                "type": "error",
                                "message": "Lỗi lưu trạng thái hoàn thành phiên phỏng vấn vào cơ sở dữ liệu.",
                            })
                else:
                    if self.response_mode == "voice" and (turn_audio_collector or missing_audio_sentences):
                        self._awaiting_playback_id = gen_id
                    if self.connection.is_open():
                        await self.connection.send_event({
                            "type": VoiceEventType.DONE.value,
                            "turn_id": turn_id,
                            "generation_id": gen_id,
                            "full_text": final_text,
                            "audio_url": ai_audio_url,
                            "missing_audio_sentences": missing_audio_sentences,
                            "total_sentences": splitter.sentence_index,
                            "is_completed": False,
                        })

                    if is_transitioning and self.flow and self.flow.get("pending"):
                        self.flow["pending"]["summary_message"] = final_text
                        self._save_flow()
                        await self._emit_pending_proposal()
                    if not self._awaiting_playback_id:
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

    async def _synthesize_sentence_audio(
        self, text: str, sentence_idx: int, generation_id: str, turn_id: int,
    ) -> bytes | None:
        async def notify(phase: str) -> None:
            if self.connection.is_open():
                await self.connection.send_event({
                    "type": VoiceEventType.TTS_FALLBACK.value,
                    "phase": phase,
                    "sentence": text,
                    "sentence_index": sentence_idx,
                    "generation_id": generation_id,
                    "turn_id": turn_id,
                })

        if self.browser_tts_fallback:
            if self._tts_browser_forced and not self._tts_fallback_notice_sent:
                self._tts_fallback_notice_sent = True
                await notify("browser")
            return None

        self._tts_attempted_synthesis = True
        chunks: list[bytes] = []
        try:
            voice = "vi-VN-HoaiMyNeural" if self._tts_backup_active and self.voice.startswith("vieneu:") else self.voice
            if self._tts_backup_active and not self._tts_fallback_notice_sent:
                self._tts_fallback_notice_sent = True
                await notify("backup")
            async for chunk in self.tts.synthesize_stream(text, voice=voice, pitch=self.pitch):
                if self.is_generation_cancelled(generation_id):
                    return None
                if isinstance(chunk, TTSFallbackNotice):
                    self._tts_failed_this_turn = True
                    if chunk.phase == "backup":
                        self._tts_backup_active = True
                        self._tts_fallback_notice_sent = True
                    else:
                        self._tts_browser_forced = True
                        self.browser_tts_fallback = True
                    await notify(chunk.phase)
                    if chunk.phase == "browser":
                        return None
                elif chunk:
                    chunks.append(chunk)
        except Exception as exc:
            logging.getLogger("VoiceOrchestrator").warning(
                "TTS failed for session %s turn %s sentence %s: %s",
                self.session_id, turn_id, sentence_idx, exc,
            )
            if self.is_generation_cancelled(generation_id):
                return None
            self._tts_failed_this_turn = True
            self._tts_browser_forced = True
            self.browser_tts_fallback = True
            await notify("browser")
            return None

        if chunks:
            return b"".join(chunks)
        if not self.is_generation_cancelled(generation_id):
            self._tts_failed_this_turn = True
            self._tts_browser_forced = True
            self.browser_tts_fallback = True
            await notify("browser")
        return None

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
        full_sentence_audio = await self._synthesize_sentence_audio(
            clean_text, sentence_idx, generation_id, turn_id,
        )
        if full_sentence_audio and not self.is_generation_cancelled(generation_id):
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
        self._generation_counter += 1
        gen_id = f"gen_{self.session_id}_{self.current_turn_id}_{self._generation_counter}"
        self.current_generation_id = gen_id
        self._start_tts_generation(gen_id)
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
            missing_audio_sentences: list[str] = []
            for sentence_idx, sentence_text in (sentences if self.response_mode == "voice" else []):
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

                full_audio = await self._synthesize_sentence_audio(clean_sentence, sentence_idx, gen_id, turn_id)
                if self.is_generation_cancelled(gen_id):
                    return
                if full_audio:
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
                else:
                    missing_audio_sentences.append(clean_sentence)

            if not self.is_generation_cancelled(gen_id):
                await self._finish_tts_generation(gen_id)
                ai_audio_url = None
                if turn_audio_collector and not missing_audio_sentences:
                    full_turn_audio = b"".join(
                        turn_audio_collector[k] for k in sorted(turn_audio_collector.keys())
                    )
                    ai_audio_url = self._save_audio_file(turn_id, "ai", full_turn_audio)

                self.conversation_history.append({"role": "assistant", "content": clean_text})
                self._record_stage_turn("assistant", clean_text)
                self._persist_ai_turn(turn_id, clean_text, turn_intent, audio_url=ai_audio_url)
                if self.response_mode == "voice" and (turn_audio_collector or missing_audio_sentences):
                    self._awaiting_playback_id = gen_id
                if self.connection.is_open():
                    await self.connection.send_event({
                        "type": VoiceEventType.DONE.value,
                        "turn_id": turn_id,
                        "generation_id": gen_id,
                        "full_text": clean_text,
                        "audio_url": ai_audio_url,
                        "missing_audio_sentences": missing_audio_sentences,
                        "total_sentences": len(sentences),
                        "is_completed": False,
                    })
                if self.flow and self.flow.get("pending"):
                    self.flow["pending"]["summary_message"] = clean_text
                    self._save_flow()
                    await self._emit_pending_proposal()
                if not self._awaiting_playback_id:
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
        if self.flow:
            item = current_item(self.flow)
            self.current_intent_ctx = QuestionIntentContext(
                question_id=None,
                intent=warmup_topic(item, self.language) if item["stage"] == StageId.WARMUP.value else item["question"],
                stage_key=item["stage"],
                difficulty=3, question_type=item["type"], topic_label=item["type"],
            ) if item else None
            if item and item["status"] == "not_asked":
                item["status"] = "asked"
                self._save_flow()
            return
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
                        idx = min(self.turns_in_current_stage // 2, len(stage_matched) - 1)
                        chosen = stage_matched[idx]
                    elif items:
                        idx = (self.turns_in_current_stage // 2) % len(items)
                        chosen = items[idx]

                    if chosen:
                        # Câu hỏi sinh từ kịch bản JD, KHÔNG thuộc ngân hàng câu hỏi
                        # -> không gắn question_id để tránh gán kỹ năng sai.
                        self.current_intent_ctx = QuestionIntentContext(
                            question_id=None,
                            intent=chosen.get("question_text", ""),
                            stage_key=cur_stage.id,
                            difficulty=int(chosen.get("difficulty", 3)),
                            question_type=chosen.get("question_type") or {
                                "behavioral": "behavioral", "scenario": "situational",
                                "technical": "technical", "system_design": "technical",
                                "role_specific": "technical",
                            }.get(chosen.get("section_type"), "generic"),
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
        if self.flow:
            if self.state != VoiceSessionState.LISTEN or self.flow.get("pending"):
                return
            item = current_item(self.flow)
            if not item:
                return
            item["status"] = "skipped_with_reason"
            item["reason"] = "candidate_requested_new_question"
            self.flow["current_item"] = None
            self._save_flow()
            await self._emit_flow_progress()
            next_item = current_item(self.flow)
            if next_item:
                self._resolve_next_intent()
                await self._emit_question_context()
                self.current_turn_id += 1
                await self.set_state(VoiceSessionState.THINK)
                self._active_task = asyncio.create_task(
                    self._run_llm_and_tts_pipeline(
                        next_question_item=next_item,
                        disposition="cannot_answer",
                    )
                )
            else:
                if active_elapsed(self.flow) >= self.flow["budgets"][self.get_current_stage().id]:
                    await self._offer_adaptive_transition()
                else:
                    self.current_turn_id += 1
                    await self.set_state(VoiceSessionState.THINK)
                    text = ("Mình đã hỏi hết các nội dung của phần này. Bạn có thể chia sẻ thêm "
                            "hoặc đề nghị chuyển phần khi sẵn sàng.") if self.language == "vi" else (
                            "We have covered the planned questions. Add anything else or ask to move on when ready.")
                    self._active_task = asyncio.create_task(self._stream_predefined_text(text))
            return
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
                        "question_type": new_intent.question_type,
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
            from ...infrastructure.persistence.models.catalog import QuestionBank
            question_row = db.get(QuestionBank, turn_rec.question_id) if turn_rec.question_id else None
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
                    question_type=question_row.question_type if question_row else None,
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

    def _schedule_audio_cleanup(self, delay_seconds: int = 180) -> None:
        async def _cleanup():
            try:
                await asyncio.sleep(delay_seconds)
                # Chỉ xóa nếu phiên đã hoàn toàn kết thúc (COMPLETED).
                # Trong khi cuộc trò chuyện đang diễn ra, giữ nguyên toàn bộ cache audio để ứng viên nghe lại!
                if self.state != VoiceSessionState.COMPLETED:
                    return
                import shutil
                from ...config import get_audio_storage_dir
                base_dir = get_audio_storage_dir().resolve()
                session_dir = (base_dir / str(self.session_id)).resolve()
                if session_dir.is_symlink():
                    return
                if not session_dir.is_relative_to(base_dir) or session_dir == base_dir:
                    return
                if session_dir.exists() and session_dir.is_dir():
                    shutil.rmtree(session_dir, ignore_errors=True)
                    logging.getLogger("VoiceOrchestrator").info(
                        "Cleaned up audio cache for completed session #%s", self.session_id
                    )
            except Exception as exc:
                logging.getLogger("VoiceOrchestrator").warning(
                    "Failed to cleanup audio files for session #%s: %s", self.session_id, exc
                )

        task = asyncio.create_task(_cleanup())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    def _persist_session_completion(self) -> bool:
        if not self.session_factory:
            return True
        from datetime import datetime, timezone
        from ...infrastructure.persistence.models.session import InterviewSession as DbInterviewSession
        from ...infrastructure.persistence.models.enums import SessionStatus
        db = self.session_factory()
        try:
            row = db.get(DbInterviewSession, self.session_id)
            if row is not None:
                if row.status != SessionStatus.completed:
                    row.status = SessionStatus.completed
                    if not row.completed_at:
                        row.completed_at = datetime.now(timezone.utc)
                elif not row.completed_at:
                    row.completed_at = datetime.now(timezone.utc)
                db.commit()
                return True
            return False
        except Exception as exc:
            db.rollback()
            logging.getLogger("VoiceOrchestrator").exception(
                "Failed to persist completion for session #%s: %s", self.session_id, exc
            )
            return False
        finally:
            db.close()

    async def handle_stop_session(self) -> None:
        if self._judgment_task and not self._judgment_task.done():
            self._judgment_task.cancel()
        if self.flow:
            self.flow["pending"] = None
            pause(self.flow)
            self._save_flow()
        await self.cancel_current_generation()
        persisted = await asyncio.to_thread(self._persist_session_completion)
        if not persisted:
            if self.connection.is_open():
                await self.connection.send_event({
                    "type": "error",
                    "message": "Không thể lưu trạng thái kết thúc phỏng vấn vào cơ sở dữ liệu. Vui lòng thử lại.",
                })
            return

        self._schedule_session_tracking_sync()
        self._schedule_audio_cleanup(delay_seconds=120)
        await self.set_state(VoiceSessionState.COMPLETED)
        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.DONE.value,
                "turn_id": self.current_turn_id,
                "generation_id": self.current_generation_id or "",
                "is_completed": True,
            })

