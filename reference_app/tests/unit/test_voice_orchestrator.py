from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
import pytest

from app.application.voice.orchestrator import VoiceInterviewOrchestrator
from app.application.voice.adaptive_flow import create_snapshot, stage_progress
from app.application.voice.turn_judge import TurnJudgment
from app.application.voice.ports import (
    LLMVoiceStreamPort,
    TTSFallbackNotice,
    TTSPort,
    VoiceConnectionPort,
)
from app.domain.voice import VoiceEventType, VoiceSessionState


class FakeVoiceConnection(VoiceConnectionPort):
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self._open = True

    def is_open(self) -> bool:
        return self._open

    async def send_event(self, event: dict[str, Any]) -> None:
        self.events.append(event)


class FakeTTS(TTSPort):
    def __init__(self) -> None:
        self.synthesized_sentences: list[str] = []

    async def synthesize_stream(
        self, text: str, voice: str = "vi-VN-HoaiMyNeural", pitch: str = "+0Hz",
    ) -> AsyncIterator[bytes]:
        self.synthesized_sentences.append(text)
        yield b"fake_mp3_chunk_1"
        await asyncio.sleep(0.01)
        yield b"fake_mp3_chunk_2"


class FakeLLM(LLMVoiceStreamPort):
    def __init__(self, response_text: str = "Tuyệt vời. Bạn làm thế nào để tối ưu hoá cơ sở dữ liệu?") -> None:
        self.response_text = response_text

    async def stream_ai_tokens(
        self, messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        for word in self.response_text.split(" "):
            yield word + " "
            await asyncio.sleep(0.01)


@pytest.mark.anyio
async def test_runtime_llm_uses_jd_question_without_a_separate_focus_planning_call() -> None:
    class CapturingLLM(FakeLLM):
        def __init__(self) -> None:
            super().__init__()
            self.spoken_prompts: list[dict[str, str]] = []
            self.calls = 0

        async def stream_ai_tokens(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
            self.calls += 1
            self.spoken_prompts = messages
            yield "Trước hết, bạn đã áp dụng OOP thế nào trong dự án?"

    question = "Hãy nói về OOP, Collections và Stream API trong dự án Java."
    llm = CapturingLLM()
    orch = VoiceInterviewOrchestrator(
        session_id=111, connection=FakeVoiceConnection(), tts=FakeTTS(), llm=llm,
        selected_stages=["technical"],
    )
    orch.flow = create_snapshot([{"section_type": "technical", "question_text": question}], ["technical"], 30)
    await orch.handle_client_ready(response_mode="text")
    await orch._active_task

    item = orch.flow["items"][0]
    assert item["question"] == question
    assert item["last_asked_question"] == "Trước hết, bạn đã áp dụng OOP thế nào trong dự án?"
    assert "focuses" not in item
    assert llm.calls == 1
    assert "reference_question" in llm.spoken_prompts[-1]["content"]
    assert question in llm.spoken_prompts[-1]["content"]


async def _ready_to_answer(orch: VoiceInterviewOrchestrator) -> None:
    await orch.handle_client_ready()
    await orch._active_task
    await orch.handle_playback_completed(orch.current_generation_id)


@pytest.mark.anyio
async def test_orchestrator_initial_greeting() -> None:
    conn = FakeVoiceConnection()
    tts = FakeTTS()
    llm = FakeLLM()
    orch = VoiceInterviewOrchestrator(
        session_id=10,
        connection=conn,
        tts=tts,
        llm=llm,
        role_name="Backend Engineer",
        level="junior",
    )

    await orch.handle_client_ready()
    # Wait for background task to complete
    if orch._active_task:
        await orch._active_task
    await orch.handle_playback_completed(orch.current_generation_id)

    # Check state transitions: THINK -> SPEAK -> LISTEN
    states = [e["state"] for e in conn.events if e["type"] == VoiceEventType.STATE.value]
    assert VoiceSessionState.THINK.value in states
    assert VoiceSessionState.SPEAK.value in states
    assert states[-1] == VoiceSessionState.LISTEN.value
    assert len(tts.synthesized_sentences) >= 1
    assert any(e["type"] == VoiceEventType.DONE.value for e in conn.events)


@pytest.mark.anyio
async def test_greeting_does_not_finish_warmup_or_reuse_turn_number() -> None:
    conn = FakeVoiceConnection()
    orch = VoiceInterviewOrchestrator(
        session_id=109, connection=conn, tts=FakeTTS(),
        llm=FakeLLM("Rất vui được gặp bạn. Bạn có thể giới thiệu ngắn gọn về bản thân không?"),
    )
    await orch.handle_client_ready(response_mode="text")
    await orch._active_task

    await orch.handle_final_transcript("Xin chào", turn_id=1)
    await orch._judgment_task
    await orch._active_task

    assert orch.get_current_stage().id == "warmup"
    assert orch.current_turn_id == 3
    assert orch.flow["last_turn"] == 1
    assert orch.flow["items"][0]["status"] == "asked"
    assert stage_progress(orch.flow)["discussed"] == 0
    assert not any(event["type"] == VoiceEventType.STAGE_CHANGE.value for event in conn.events)
    assert "giới thiệu" in orch.conversation_history[-1]["content"].lower()


@pytest.mark.anyio
async def test_icebreaker_then_brief_experience_advances_warmup_without_technical_questions() -> None:
    class CapturingLLM(FakeLLM):
        def __init__(self) -> None:
            super().__init__("Cảm ơn bạn. Bạn có thể giới thiệu sơ qua về kinh nghiệm của mình không?")
            self.prompts: list[list[dict[str, str]]] = []

        async def stream_ai_tokens(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
            self.prompts.append(messages)
            yield self.response_text

    class ResponsiveJudge:
        def __init__(self) -> None:
            self.calls = 0

        def judge(self, question: str, signals: list[str], evidence: dict,
                  answer: str, context: list[dict[str, str]]) -> TurnJudgment:
            self.calls += 1
            if answer.strip().lower() == "không":
                return TurnJudgment(disposition="cannot_answer", source="jev")
            if "hơi run" in answer:
                return TurnJudgment({signals[-1]: 1.0}, disposition="needs_clarification", source="jev")
            return TurnJudgment({signal: 1.0 for signal in signals}, disposition="responsive", source="jev")

    llm = CapturingLLM()
    judge = ResponsiveJudge()
    orch = VoiceInterviewOrchestrator(
        session_id=110, connection=FakeVoiceConnection(), tts=FakeTTS(), llm=llm,
        turn_judge=judge, selected_stages=["warmup", "technical"],
    )
    orch.flow = create_snapshot([{
        "section_type": "introduction",
        "question_text": "Giới thiệu dự án microservice và tối ưu latency trong load test?",
        "expected_signals": ["CI/CD", "Redis"],
    }], ["warmup", "technical"], 30)
    await orch.handle_client_ready(response_mode="text")
    await orch._active_task

    await orch.handle_final_transcript("Trời đang mưa, em đã chuẩn bị phòng yên tĩnh.", turn_id=orch.current_turn_id)
    await orch._judgment_task
    await orch._active_task
    assert judge.calls == 0
    assert stage_progress(orch.flow)["discussed"] == 0
    assert len(llm.prompts) == 1
    assert "Nội dung khởi động" in llm.prompts[-1][-1]["content"]
    assert "microservice" not in " ".join(message["content"] for message in llm.prompts[-1])

    await orch.handle_final_transcript(
        "Em làm Software Engineer hai năm, dùng Java và tham gia kiểm thử.", turn_id=orch.current_turn_id,
    )
    await orch._judgment_task
    await orch._active_task
    assert judge.calls == 1
    assert stage_progress(orch.flow)["completed"] == 1
    assert stage_progress(orch.flow)["discussed"] == 1
    assert "điểm mạnh" in llm.prompts[-1][-1]["content"]
    assert orch.get_current_stage().id == "warmup"

    await orch.handle_final_transcript("Không", turn_id=orch.current_turn_id)
    await orch._judgment_task
    await orch._active_task
    assert stage_progress(orch.flow)["completed"] == 1
    assert "Lý do quan tâm" in llm.prompts[-1][-1]["content"]

    await orch.handle_final_transcript("Điểm yếu của em là em hơi run.", turn_id=orch.current_turn_id)
    await orch._judgment_task
    await orch._active_task
    assert stage_progress(orch.flow)["completed"] == 1
    assert not stage_progress(orch.flow)["ready"]
    assert "Lý do quan tâm" in llm.prompts[-1][-1]["content"]
    assert "Các nội dung của phần này" not in orch.conversation_history[-1]["content"]


@pytest.mark.anyio
async def test_orchestrator_turn_generation_flow() -> None:
    conn = FakeVoiceConnection()
    tts = FakeTTS()
    llm = FakeLLM("Câu trả lời của bạn rất hay. Hãy kể về dự án gần nhất của bạn.")
    orch = VoiceInterviewOrchestrator(
        session_id=11,
        connection=conn,
        tts=tts,
        llm=llm,
    )
    await _ready_to_answer(orch)

    await orch.handle_final_transcript("Em từng thiết kế kiến trúc microservices.", duration_seconds=10.0)
    await orch._judgment_task
    assert orch._active_task is not None
    await orch._active_task
    await orch.handle_playback_completed(orch.current_generation_id)

    # Events emitted: transcript, state, ai_token, subtitle, audio, done
    event_types = [e["type"] for e in conn.events]
    assert VoiceEventType.TRANSCRIPT.value in event_types
    assert VoiceEventType.AI_TOKEN.value in event_types
    assert VoiceEventType.SUBTITLE.value in event_types
    assert VoiceEventType.AUDIO.value in event_types
    assert VoiceEventType.DONE.value in event_types
    assert orch.state == VoiceSessionState.LISTEN


@pytest.mark.anyio
async def test_tts_failure_switches_to_browser_without_retrying_later_sentences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FlakyTTS(FakeTTS):
        def __init__(self) -> None:
            super().__init__()
            self.failed_attempts = 0

        async def synthesize_stream(
            self, text: str, voice: str = "vi-VN-HoaiMyNeural", pitch: str = "+0Hz",
        ) -> AsyncIterator[bytes]:
            if text.startswith("Bạn có thể"):
                self.failed_attempts += 1
                raise RuntimeError("TTS unavailable")
            async for chunk in super().synthesize_stream(text, voice=voice, pitch=pitch):
                yield chunk

    conn = FakeVoiceConnection()
    tts = FlakyTTS()
    llm = FakeLLM(
        "Cảm ơn bạn, cách bạn chuẩn bị thật chuyên nghiệp. "
        "Bạn có thể chia sẻ một dự án gần đây không? "
        "Và bạn đã giải quyết thử thách nào trong dự án?"
    )
    orch = VoiceInterviewOrchestrator(session_id=201, connection=conn, tts=tts, llm=llm)
    monkeypatch.setattr(orch, "_save_audio_file", lambda *_args: "/audio/test.mp3")
    await _ready_to_answer(orch)
    start = len(conn.events)

    await orch.handle_final_transcript("Em đã chuẩn bị và sẵn sàng.", duration_seconds=5.0)
    await orch._judgment_task
    await orch._active_task

    events = conn.events[start:]
    audio = [event for event in events if event["type"] == VoiceEventType.AUDIO.value]
    done = next(event for event in events if event["type"] == VoiceEventType.DONE.value)
    assert [event["sentence_index"] for event in audio] == [0]
    assert tts.failed_attempts == 1
    assert not any(sentence.startswith("Và bạn") for sentence in tts.synthesized_sentences)
    assert done["missing_audio_sentences"] == [
        "Bạn có thể chia sẻ một dự án gần đây không?",
        "Và bạn đã giải quyết thử thách nào trong dự án?",
    ]
    assert done["audio_url"] is None
    assert orch.browser_tts_fallback is True
    assert orch._awaiting_playback_id == orch.current_generation_id
    fallback = next(event for event in events if event["type"] == VoiceEventType.TTS_FALLBACK.value)
    assert fallback["phase"] == "browser"
    assert fallback["sentence_index"] == 1


@pytest.mark.anyio
async def test_primary_tts_failure_announces_backup_before_audio() -> None:
    class BackupTTS(FakeTTS):
        def __init__(self) -> None:
            super().__init__()
            self.voices: list[str] = []

        async def synthesize_stream(
            self, text: str, voice: str = "vi-VN-HoaiMyNeural", pitch: str = "+0Hz",
        ) -> AsyncIterator[bytes | TTSFallbackNotice]:
            self.voices.append(voice)
            if text.startswith("Cảm ơn bạn"):
                yield TTSFallbackNotice("backup")
            async for chunk in super().synthesize_stream(text, voice=voice, pitch=pitch):
                yield chunk

    conn = FakeVoiceConnection()
    tts = BackupTTS()
    orch = VoiceInterviewOrchestrator(
        session_id=202, connection=conn, tts=tts,
        llm=FakeLLM("Cảm ơn bạn đã chia sẻ. Bạn có thể kể thêm về dự án không?"),
        voice="vieneu:Ngọc Lan",
    )
    await _ready_to_answer(orch)
    start = len(conn.events)

    await orch.handle_final_transcript("Em đã chuẩn bị và sẵn sàng.", duration_seconds=5.0)
    await orch._judgment_task
    await orch._active_task

    events = conn.events[start:]
    fallback_index = next(index for index, event in enumerate(events)
                          if event["type"] == VoiceEventType.TTS_FALLBACK.value)
    first_audio_index = next(index for index, event in enumerate(events)
                             if event["type"] == VoiceEventType.AUDIO.value)
    assert events[fallback_index]["phase"] == "backup"
    assert fallback_index < first_audio_index
    assert tts.voices[-2:] == ["vieneu:Ngọc Lan", "vi-VN-HoaiMyNeural"]
    assert orch.browser_tts_fallback is False


@pytest.mark.anyio
async def test_tts_backup_retries_primary_next_turn_and_only_locks_with_consent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingPrimaryTTS(FakeTTS):
        def __init__(self) -> None:
            super().__init__()
            self.voices: list[str] = []

        async def synthesize_stream(
            self, text: str, voice: str = "vi-VN-HoaiMyNeural", pitch: str = "+0Hz",
        ) -> AsyncIterator[bytes | TTSFallbackNotice]:
            self.voices.append(voice)
            if voice.startswith("vieneu:"):
                yield TTSFallbackNotice("backup")
            yield b"fake_mp3_audio"

    connection = FakeVoiceConnection()
    tts = FailingPrimaryTTS()
    orch = VoiceInterviewOrchestrator(
        session_id=203, connection=connection, tts=tts, llm=FakeLLM(), voice="vieneu:Ngọc Lan",
    )
    monkeypatch.setattr(orch, "_save_audio_file", lambda *_args: "/audio/test.mp3")

    await orch._stream_predefined_text("Đây là câu thứ nhất rất rõ. Đây là câu thứ hai cũng rất rõ.")
    assert tts.voices == ["vieneu:Ngọc Lan", "vi-VN-HoaiMyNeural"]
    assert not any(event["type"] == VoiceEventType.TTS_FALLBACK_CONSENT.value for event in connection.events)

    await orch._stream_predefined_text("Lượt mới cần thử lại giọng được chọn.")
    assert tts.voices[-1] == "vieneu:Ngọc Lan"
    offers = [event for event in connection.events if event["type"] == VoiceEventType.TTS_FALLBACK_CONSENT.value]
    assert len(offers) == 1
    assert offers[0]["phase"] == "backup"

    await orch.handle_tts_fallback_consent(offers[0]["generation_id"], True)
    await orch._stream_predefined_text("Sau khi đồng ý thì sử dụng Edge.")
    assert tts.voices[-1] == "vi-VN-HoaiMyNeural"
    assert len([event for event in connection.events if event["type"] == VoiceEventType.TTS_FALLBACK_CONSENT.value]) == 1


@pytest.mark.anyio
async def test_browser_fallback_is_per_turn_and_refusal_retries_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingEdgeTTS(FakeTTS):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        async def synthesize_stream(
            self, text: str, voice: str = "vi-VN-HoaiMyNeural", pitch: str = "+0Hz",
        ) -> AsyncIterator[bytes]:
            self.attempts += 1
            if self.attempts <= 3:
                raise RuntimeError("Edge unavailable")
            yield b"fake_mp3_audio"

    connection = FakeVoiceConnection()
    tts = FailingEdgeTTS()
    orch = VoiceInterviewOrchestrator(session_id=204, connection=connection, tts=tts, llm=FakeLLM())
    monkeypatch.setattr(orch, "_save_audio_file", lambda *_args: "/audio/test.mp3")

    await orch._stream_predefined_text("Câu thứ nhất dài vừa đủ. Câu thứ hai dài vừa đủ.")
    assert tts.attempts == 1
    await orch._stream_predefined_text("Lượt khác bắt đầu thử lại Edge.")
    assert tts.attempts == 2
    offer = next(event for event in connection.events if event["type"] == VoiceEventType.TTS_FALLBACK_CONSENT.value)
    assert offer["phase"] == "browser"

    await orch.handle_tts_fallback_consent(offer["generation_id"], False)
    await orch._stream_predefined_text("Từ chối vẫn thử Edge ở lượt sau.")
    assert tts.attempts == 3
    assert orch._tts_locked_fallback is None
    await orch._stream_predefined_text("Giọng Edge đã hoạt động bình thường trở lại.")
    assert tts.attempts == 4
    assert orch._tts_consecutive_failed_turns == 0


@pytest.mark.anyio
async def test_consented_browser_fallback_skips_server_tts_on_later_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableTTS(FakeTTS):
        def __init__(self) -> None:
            super().__init__()
            self.attempts = 0

        async def synthesize_stream(
            self, text: str, voice: str = "vi-VN-HoaiMyNeural", pitch: str = "+0Hz",
        ) -> AsyncIterator[bytes]:
            self.attempts += 1
            if self.attempts <= 2:
                raise RuntimeError("TTS unavailable")
            yield b"fake_mp3_audio"

    connection = FakeVoiceConnection()
    tts = UnavailableTTS()
    orch = VoiceInterviewOrchestrator(session_id=205, connection=connection, tts=tts, llm=FakeLLM())
    monkeypatch.setattr(orch, "_save_audio_file", lambda *_args: "/audio/test.mp3")
    await orch._stream_predefined_text("Lượt thứ nhất đã lỗi giọng đọc.")
    await orch._stream_predefined_text("Lượt thứ hai vẫn lỗi giọng đọc.")
    offer = next(event for event in connection.events if event["type"] == VoiceEventType.TTS_FALLBACK_CONSENT.value)
    await orch.handle_tts_fallback_consent(offer["generation_id"], True)

    start = len(connection.events)
    await orch._stream_predefined_text("Lượt này phát trực tiếp bằng trình duyệt.")
    events = connection.events[start:]
    assert tts.attempts == 2
    assert [event["phase"] for event in events if event["type"] == VoiceEventType.TTS_FALLBACK.value] == ["browser"]
    assert next(event for event in events if event["type"] == VoiceEventType.DONE.value)["missing_audio_sentences"]


@pytest.mark.anyio
async def test_orchestrator_barge_in_interruption() -> None:
    conn = FakeVoiceConnection()
    tts = FakeTTS()
    llm = FakeLLM("Một câu trả lời rất dài và cần thời gian tổng hợp nhiều thông tin...")
    orch = VoiceInterviewOrchestrator(
        session_id=12,
        connection=conn,
        tts=tts,
        llm=llm,
    )
    await _ready_to_answer(orch)

    # Trigger final transcript to begin generation
    await orch.handle_final_transcript("Em có câu hỏi.")
    await orch._judgment_task
    assert orch._active_task is not None

    # User interrupts AI (Barge-in)
    await asyncio.sleep(0.01)
    await orch.handle_user_speech_start()

    # Generation must be cancelled and interrupted event emitted
    interrupted_events = [e for e in conn.events if e["type"] == VoiceEventType.INTERRUPTED.value]
    assert len(interrupted_events) == 1
    assert orch.state == VoiceSessionState.LISTEN
    assert orch.current_generation_id is None


@pytest.mark.anyio
async def test_orchestrator_barge_in_disabled() -> None:
    conn = FakeVoiceConnection()
    tts = FakeTTS()
    llm = FakeLLM("AI đang nói và không bị ngắt lời...")
    orch = VoiceInterviewOrchestrator(
        session_id=13,
        connection=conn,
        tts=tts,
        llm=llm,
        barge_in_enabled=False,
    )
    await _ready_to_answer(orch)

    # Trigger final transcript to begin generation
    await orch.handle_final_transcript("Câu hỏi là gì?")
    await orch._judgment_task
    assert orch._active_task is not None

    # User speaks while barge_in is disabled
    await asyncio.sleep(0.01)
    await orch.handle_user_speech_start()
    await orch.handle_interim_transcript("Người dùng đang nói xen vào")

    # Generation must NOT be cancelled
    interrupted_events = [e for e in conn.events if e["type"] == VoiceEventType.INTERRUPTED.value]
    assert len(interrupted_events) == 0
    assert orch.current_generation_id is not None
    await orch._active_task

@pytest.mark.anyio
async def test_orchestrator_custom_single_stage_technical_only() -> None:
    conn = FakeVoiceConnection()
    tts = FakeTTS()
    llm = FakeLLM("Câu trả lời kỹ thuật của bạn rất tốt.")
    orch = VoiceInterviewOrchestrator(
        session_id=14,
        connection=conn,
        tts=tts,
        llm=llm,
        selected_stages=["technical"],
    )

    assert len(orch.active_stages) == 1
    assert orch.active_stages[0].id == "technical"

    await orch.handle_client_ready()
    if orch._active_task:
        await orch._active_task

    # First question is technical
    stage_data = orch.get_current_stage_data()
    assert stage_data["id"] == "technical"
    assert stage_data["total"] == 1
    assert stage_data["is_last"] is True


@pytest.mark.anyio
async def test_orchestrator_custom_stages_warmup_and_closing() -> None:
    conn = FakeVoiceConnection()
    tts = FakeTTS()
    llm = FakeLLM("Tôi đã ghi nhận câu trả lời của bạn.")
    orch = VoiceInterviewOrchestrator(
        session_id=15,
        connection=conn,
        tts=tts,
        llm=llm,
        selected_stages=["warmup", "closing"],
        questions_per_stage={"warmup": 1, "closing": 1},
    )

    assert len(orch.active_stages) == 2
    assert orch.active_stages[0].id == "warmup"
    assert orch.active_stages[1].id == "closing"

    await orch.handle_client_ready()
    if orch._active_task:
        await orch._active_task

    await orch.handle_playback_completed(orch.current_generation_id)
    await orch.handle_final_transcript("Hôm nay trời rất đẹp, em rất sẵn sàng.")
    await orch._judgment_task
    if orch._active_task:
        await orch._active_task

    assert orch.current_stage_index == 0
    assert orch.get_current_stage().id == "warmup"

    stage_changes = [e for e in conn.events if e.get("type") == VoiceEventType.STAGE_CHANGE.value]
    assert stage_changes == []


@pytest.mark.anyio
async def test_orchestrator_reconnect_does_not_repeat_voiced_question() -> None:
    class FakeTurnRow:
        def __init__(self, turn_number: int, speaker: Any, message_text: str, transcribed_text: str | None = None, audio_url: str | None = None) -> None:
            self.turn_number = turn_number
            self.speaker = speaker
            self.message_text = message_text
            self.transcribed_text = transcribed_text
            self.audio_url = audio_url

    class FakeQuery:
        def __init__(self, rows: list[Any]) -> None:
            self._rows = rows
        def filter_by(self, **kwargs):
            return self
        def order_by(self, *args):
            return self
        def all(self):
            return list(self._rows)
        def first(self):
            return self._rows[0] if self._rows else None

    class FakeDbSession:
        def __init__(self, rows: list[Any]) -> None:
            self.rows = rows
        def query(self, model):
            return FakeQuery(self.rows)
        def add(self, item):
            self.rows.append(item)
        def commit(self):
            pass
        def rollback(self):
            pass
        def close(self):
            pass

    existing_rows = [
        FakeTurnRow(turn_number=1, speaker="ai", message_text="Chào bạn, hôm nay thời tiết thế nào?", audio_url="voice_streamed")
    ]
    def fake_session_factory():
        return FakeDbSession(existing_rows)

    conn = FakeVoiceConnection()
    tts = FakeTTS()
    llm = FakeLLM()
    orch = VoiceInterviewOrchestrator(
        session_id=99,
        connection=conn,
        tts=tts,
        llm=llm,
        session_factory=fake_session_factory,
    )

    assert orch._has_unvoiced_opening is False
    assert len(orch.conversation_history) == 1

    await orch.handle_client_ready()
    assert orch.state == VoiceSessionState.LISTEN
    assert len(tts.synthesized_sentences) == 0

    history_events = [e for e in conn.events if e.get("type") == "conversation_history"]
    assert len(history_events) == 1
    assert len(history_events[0]["turns"]) == 1
    assert history_events[0]["turns"][0]["turnNumber"] == 1


@pytest.mark.anyio
async def test_orchestrator_markdown_sanitization_and_interviewer_prompt() -> None:
    conn = FakeVoiceConnection()
    tts = FakeTTS()
    raw_markdown_output = "**Tôi hiểu rồi**, cách tiếp cận đó rất hợp lý. Bạn hãy nêu cách triển khai `Redis Cache` để tránh thắt cổ chai?"
    llm = FakeLLM(raw_markdown_output)

    orch = VoiceInterviewOrchestrator(
        session_id=105,
        connection=conn,
        tts=tts,
        llm=llm,
        role_name="Backend Engineer",
        level="Senior",
        language="vi",
    )

    # 1. System prompt is initialized with Senior Tech Lead persona and zero markdown policy
    assert orch.system_prompt is not None
    assert "Trưởng nhóm Kỹ thuật cấp cao" in orch.system_prompt
    assert "ZERO MARKDOWN POLICY" in orch.system_prompt
    assert "QUY TẮC 1 CÂU HỎI DUY NHẤT" in orch.system_prompt

    # 2. Simulate user response
    await _ready_to_answer(orch)
    conn.events.clear()
    tts.synthesized_sentences.clear()
    await orch.handle_final_transcript("Tôi thường dùng Redis làm caching layer.", duration_seconds=5.0)
    await orch._judgment_task
    if orch._active_task:
        await orch._active_task

    # 3. Verify no markdown in synthesized sentences
    assert len(tts.synthesized_sentences) > 0
    for s in tts.synthesized_sentences:
        assert "**" not in s
        assert "`" not in s

    # 4. Verify no markdown in DONE event full_text
    done_events = [e for e in conn.events if e["type"] == VoiceEventType.DONE.value]
    assert len(done_events) == 1
    done_text = done_events[0]["full_text"]
    assert "**" not in done_text
    assert "`" not in done_text
    assert "Tôi hiểu rồi" in done_text
    assert "Redis Cache" in done_text

@pytest.mark.anyio
async def test_orchestrator_voice_pitch_configuration() -> None:
    conn = FakeVoiceConnection()
    tts = FakeTTS()
    llm = FakeLLM("Xin chào, tôi là AI.")

    orch = VoiceInterviewOrchestrator(
        session_id=106,
        connection=conn,
        tts=tts,
        llm=llm,
    )
    assert orch.pitch == "+0Hz"

    # Set custom pitch
    orch.set_pitch("-5Hz")
    assert orch.pitch == "-5Hz"

    orch.set_pitch(8)
    assert orch.pitch == "+8Hz"

    orch.set_pitch(-25)  # Should clamp to -15Hz
    assert orch.pitch == "-15Hz"

@pytest.mark.anyio
async def test_orchestrator_stop_session_flow() -> None:
    conn = FakeVoiceConnection()
    tts = FakeTTS()
    llm = FakeLLM("Xin chào.")

    orch = VoiceInterviewOrchestrator(
        session_id=107,
        connection=conn,
        tts=tts,
        llm=llm,
    )
    await orch.handle_stop_session()

    assert orch.state == VoiceSessionState.COMPLETED
    done_events = [e for e in conn.events if e.get("type") == VoiceEventType.DONE.value]
    assert len(done_events) == 1
    assert done_events[0]["is_completed"] is True


@pytest.mark.anyio
async def test_orchestrator_refuses_turns_when_completed() -> None:
    conn = FakeVoiceConnection()
    tts = FakeTTS()
    llm = FakeLLM("Xin chào.")

    orch = VoiceInterviewOrchestrator(
        session_id=108,
        connection=conn,
        tts=tts,
        llm=llm,
    )
    orch.state = VoiceSessionState.COMPLETED

    # Client ready on completed session receives completed state
    await orch.handle_client_ready()
    states = [e for e in conn.events if e.get("type") == VoiceEventType.STATE.value]
    assert any(s.get("state") == VoiceSessionState.COMPLETED.value for s in states)

    # Submitting transcript when completed returns error
    conn.events.clear()
    await orch.handle_final_transcript("Câu trả lời muộn.")
    error_events = [e for e in conn.events if e.get("type") == "error"]
    assert len(error_events) == 1
    assert error_events[0]["is_completed"] is True
