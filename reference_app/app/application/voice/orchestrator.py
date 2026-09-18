from __future__ import annotations

import asyncio
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
from .ports import LLMVoiceStreamPort, TTSPort, VoiceConnectionPort
from .sentence_splitter import StreamingSentenceSplitter
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
        system_prompt: str | None = None,
        barge_in_enabled: bool = True,
        selected_stages: list[str] | None = None,
        questions_per_stage: dict[str, int] | None = None,
        session_factory: Any = None,
    ) -> None:
        self.session_factory = session_factory
        self.current_intent_ctx: QuestionIntentContext | None = None
        self.session_id = session_id
        self.connection = connection
        self.tts = tts
        self.llm = llm
        self.role_name = role_name
        self.level = level
        self.language = language
        self.voice = voice
        self.system_prompt = system_prompt
        self.barge_in_enabled = barge_in_enabled

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

    def _build_opening_question(self) -> str:
        cur_stage = self.get_current_stage()
        is_vi = self.language == "vi"

        if cur_stage.id == StageId.WARMUP.value:
            if is_vi:
                return (
                    f"Chào bạn, rất vui được đón tiếp bạn trong buổi phỏng vấn vị trí {self.role_name} ({self.level}). "
                    "Trước khi bắt đầu phần chuyên môn, hôm nay thời tiết và tâm trạng của bạn thế nào? "
                    "Hãy chia sẻ đôi chút và giới thiệu ngắn gọn về bản thân nhé!"
                )
            return (
                f"Welcome to your interview for the {self.role_name} ({self.level}) position. "
                "Before diving into technical details, how is your day going? "
                "Please share a quick icebreaker and briefly introduce yourself!"
            )

        if cur_stage.id == StageId.TECHNICAL.value:
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
        barge_in_enabled: bool | None = None,
        selected_stages: list[str] | None = None,
        questions_per_stage: dict[str, int] | None = None,
    ) -> None:
        if role_name:
            self.role_name = role_name
        if level:
            self.level = level
        if language:
            self.language = language
        if voice:
            self.voice = voice
        if barge_in_enabled is not None:
            self.barge_in_enabled = barge_in_enabled
        if questions_per_stage:
            self.questions_per_stage.update(questions_per_stage)
        if selected_stages:
            self.active_stages = self._resolve_stages(selected_stages)
            self.current_stage_index = 0
            self.turns_in_current_stage = 0

        # Broadcast initial stage info
        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.STAGE_INFO.value,
                "current_stage": self.get_current_stage_data(),
                "stages": self.get_all_stages_data(),
                "turn_in_stage": self.turns_in_current_stage + 1,
                "target_turns_in_stage": self.get_target_turns_for_current_stage(),
            })

        # Resolve intent for current stage if DB session is available
        self._resolve_next_intent()
        if self.current_intent_ctx and self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.QUESTION_CONTEXT.value,
                "question_id": self.current_intent_ctx.question_id,
                "topic_label": self.current_intent_ctx.topic_label,
                "stage_key": self.current_intent_ctx.stage_key,
                "difficulty": self.current_intent_ctx.difficulty,
            })

        # If voice session has no history yet, initiate greeting and stage opening question
        if not self.conversation_history and self.state == VoiceSessionState.IDLE:
            await self.set_state(VoiceSessionState.THINK)
            prompt = self._build_opening_question()
            self._active_task = asyncio.create_task(
                self._stream_predefined_text(prompt),
            )
        else:
            await self.set_state(VoiceSessionState.LISTEN)

    async def handle_user_speech_start(self) -> None:
        if not self.barge_in_enabled:
            return

        if self.state in (VoiceSessionState.SPEAK, VoiceSessionState.THINK) or (
            self._active_task and not self._active_task.done()
        ):
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
        self.turns_in_current_stage += 1

        # Transition state to THINK first
        await self.set_state(VoiceSessionState.THINK)

        # Check stage completion conditions
        target_turns = self.get_target_turns_for_current_stage()
        is_stage_completed = self.turns_in_current_stage >= target_turns
        is_last_stage = self.current_stage_index >= len(self.active_stages) - 1

        is_transitioning = False
        is_session_finishing = False

        if is_stage_completed:
            if not is_last_stage:
                # Advance to next stage!
                self.current_stage_index += 1
                self.turns_in_current_stage = 0
                is_transitioning = True
                next_stage = self.get_current_stage()

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
                    })
            else:
                is_session_finishing = True

        # Spawn background LLM streaming + sentence TTS pipeline
        self._active_task = asyncio.create_task(
            self._run_llm_and_tts_pipeline(
                is_transitioning=is_transitioning,
                is_session_finishing=is_session_finishing,
            ),
        )

    async def handle_next_stage(self) -> None:
        if self.current_stage_index < len(self.active_stages) - 1:
            await self.cancel_current_generation()
            self.current_stage_index += 1
            self.turns_in_current_stage = 0
            next_stage = self.get_current_stage()

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
                })

            await self.set_state(VoiceSessionState.THINK)
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

        situational_guard = QuestionIntentComposer.build_situational_system_prompt(
            role=self.role_name,
            level=self.level,
            stage_key=cur_stage.id,
            intent_ctx=self.current_intent_ctx,
            language=self.language,
        )

        if is_session_finishing:
            if is_vi:
                return (
                    "Buổi phỏng vấn đã hoàn tất tất cả các chặng. "
                    "Hãy đưa ra nhận xét tổng quát tích cực, gửi lời cảm ơn chân thành tới ứng viên và "
                    "thông báo kết thúc buổi phỏng vấn."
                )
            return (
                "All interview stages are now complete. "
                "Provide a brief warm closing remark, thank the candidate sincerely, and conclude the interview session."
            )

        if cur_stage.id == StageId.WARMUP.value:
            if is_vi:
                return (
                    "Bạn đang ở chặng 1: Khởi động & Chào hỏi (Warm-up). "
                    "Mục tiêu: tạo không khí thoải mái, chào hỏi, lắng nghe câu trả lời về bối cảnh/thời tiết và giới thiệu bản thân. "
                    "Hãy phản hồi tự nhiên (1-2 câu ngắn) và hỏi tiếp một câu mở đầu nhẹ nhàng."
                )
            return (
                "You are in Stage 1: Warm-up & Greeting. "
                "Goal: establish a welcoming atmosphere, acknowledge small talk/icebreaker, and transition naturally."
            )

        if cur_stage.id == StageId.TECHNICAL.value:
            transition_text = (
                " Chúng ta vừa bước sang phần Phỏng vấn chuyên môn kỹ thuật. Hãy chúc mừng ứng viên và bắt đầu câu hỏi kỹ thuật sâu."
                if is_transitioning
                else ""
            )
            if is_vi:
                return (
                    f"Bạn đang ở chặng: Phỏng vấn chuyên môn (Technical Interview).{transition_text} "
                    f"Vị trí: {self.role_name} ({self.level}). "
                    "Mục tiêu: Đào sâu vào kinh nghiệm thực tế, kiến trúc hệ thống, trade-offs kỹ thuật hoặc phương pháp STAR. "
                    "Phản hồi súc tích, chuyên nghiệp (2-3 câu)."
                )
            return (
                f"You are in the Technical Interview stage for {self.role_name} ({self.level}).{transition_text} "
                "Focus on engineering challenges, architecture decisions, trade-offs, and STAR methodology."
            )

        # StageId.CLOSING
        transition_text = (
            " Chúng ta vừa bước sang chặng Thỏa thuận & Chào kết."
            if is_transitioning
            else ""
        )
        if is_vi:
            return (
                f"Bạn đang ở chặng: Thỏa thuận & Chào kết (Closing & Negotiation).{transition_text} "
                "Mục tiêu: Trả lời câu hỏi ứng viên đặt ra về doanh nghiệp, trao đổi về nguyện vọng nghề nghiệp, mức lương hoặc phúc lợi kỳ vọng."
            )
        return (
            f"You are in the Closing & Negotiation stage.{transition_text} "
            "Address candidate questions regarding the team, career growth, or compensation expectations."
        )

    async def _run_llm_and_tts_pipeline(
        self,
        is_transitioning: bool = False,
        is_session_finishing: bool = False,
    ) -> None:
        self._generation_counter += 1
        gen_id = f"gen_{self.session_id}_{self.current_turn_id}_{self._generation_counter}"
        self.current_generation_id = gen_id
        turn_id = self.current_turn_id

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
            messages.extend(self.conversation_history[-8:])

            # Stream tokens from LLM
            async for token in self.llm.stream_ai_tokens(messages):
                if self.is_generation_cancelled(gen_id):
                    return

                full_ai_response.append(token)
                if self.connection.is_open():
                    await self.connection.send_event({
                        "type": VoiceEventType.AI_TOKEN.value,
                        "token": token,
                        "turn_id": turn_id,
                        "generation_id": gen_id,
                    })

                # Feed to sentence splitter
                for sentence_idx, sentence_text in splitter.feed(token):
                    if self.is_generation_cancelled(gen_id):
                        return
                    await self._stream_sentence_tts(
                        sentence_idx=sentence_idx,
                        sentence_text=sentence_text,
                        generation_id=gen_id,
                        turn_id=turn_id,
                    )

            # Flush any remaining text in splitter
            for sentence_idx, sentence_text in splitter.flush():
                if self.is_generation_cancelled(gen_id):
                    return
                await self._stream_sentence_tts(
                    sentence_idx=sentence_idx,
                    sentence_text=sentence_text,
                    generation_id=gen_id,
                    turn_id=turn_id,
                )

            # If not cancelled, record AI message in history and finalize turn
            if not self.is_generation_cancelled(gen_id):
                final_text = "".join(full_ai_response).strip()
                if final_text:
                    self.conversation_history.append({"role": "assistant", "content": final_text})

                if is_session_finishing:
                    await self.set_state(VoiceSessionState.COMPLETED)
                    if self.connection.is_open():
                        await self.connection.send_event({
                            "type": VoiceEventType.DONE.value,
                            "turn_id": turn_id,
                            "generation_id": gen_id,
                            "full_text": final_text,
                            "is_completed": True,
                        })
                else:
                    if self.connection.is_open():
                        await self.connection.send_event({
                            "type": VoiceEventType.DONE.value,
                            "turn_id": turn_id,
                            "generation_id": gen_id,
                            "full_text": final_text,
                            "is_completed": False,
                        })

                    self.current_turn_id += 1
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

        # Transition state to SPEAK on the first sentence
        if self.state != VoiceSessionState.SPEAK:
            await self.set_state(VoiceSessionState.SPEAK)

        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.SUBTITLE.value,
                "sentence": sentence_text,
                "sentence_index": sentence_idx,
                "generation_id": generation_id,
                "turn_id": turn_id,
            })

        # Synthesize with Edge TTS and stream chunks immediately
        async for audio_chunk in self.tts.synthesize_stream(sentence_text, voice=self.voice):
            if self.is_generation_cancelled(generation_id):
                break

            if self.connection.is_open() and audio_chunk:
                await self.connection.send_event({
                    "type": VoiceEventType.AUDIO.value,
                    "audio_chunk": audio_chunk,
                    "mime_type": "audio/mpeg",
                    "sentence_index": sentence_idx,
                    "generation_id": generation_id,
                    "turn_id": turn_id,
                })

    async def _stream_predefined_text(self, text: str) -> None:
        self._generation_counter += 1
        gen_id = f"gen_{self.session_id}_{self.current_turn_id}_{self._generation_counter}"
        self.current_generation_id = gen_id
        turn_id = self.current_turn_id

        try:
            splitter = StreamingSentenceSplitter(min_sentence_chars=12)
            if self.connection.is_open():
                await self.connection.send_event({
                    "type": VoiceEventType.AI_TOKEN.value,
                    "token": text,
                    "turn_id": turn_id,
                    "generation_id": gen_id,
                })

            for s_idx, s_text in splitter.feed(text):
                if self.is_generation_cancelled(gen_id):
                    return
                await self._stream_sentence_tts(s_idx, s_text, gen_id, turn_id)

            for s_idx, s_text in splitter.flush():
                if self.is_generation_cancelled(gen_id):
                    return
                await self._stream_sentence_tts(s_idx, s_text, gen_id, turn_id)

            if not self.is_generation_cancelled(gen_id):
                self.conversation_history.append({"role": "assistant", "content": text})
                if self.connection.is_open():
                    await self.connection.send_event({
                        "type": VoiceEventType.DONE.value,
                        "turn_id": turn_id,
                        "generation_id": gen_id,
                        "full_text": text,
                        "is_completed": False,
                    })
                self.current_turn_id += 1
                await self.set_state(VoiceSessionState.LISTEN)
        except asyncio.CancelledError:
            return

    def _resolve_next_intent(self) -> None:
        if not self.session_factory:
            return
        cur_stage = self.get_current_stage()
        db = self.session_factory()
        try:
            intents = QuestionSelectionService.sample_questions_for_stage(
                session=db,
                session_id=self.session_id,
                stage_key=cur_stage.id,
                source_mode="auto_random",
                target_count=1,
            )
            if intents:
                self.current_intent_ctx = intents[0]
                db.commit()
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
        if not self.session_factory or not self.current_intent_ctx:
            return

        db = self.session_factory()
        try:
            cur_stage = self.get_current_stage()
            new_intent = QuestionSelectionService.reroll_question(
                session=db,
                session_id=self.session_id,
                stage_key=cur_stage.id,
                current_question_id=self.current_intent_ctx.question_id,
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

    async def handle_stop_session(self) -> None:
        await self.cancel_current_generation()
        await self.set_state(VoiceSessionState.COMPLETED)
        if self.connection.is_open():
            await self.connection.send_event({
                "type": VoiceEventType.DONE.value,
                "turn_id": self.current_turn_id,
                "generation_id": self.current_generation_id or "",
                "is_completed": True,
            })
