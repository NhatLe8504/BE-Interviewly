from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator
import pytest

from app.application.voice.orchestrator import VoiceInterviewOrchestrator
from app.application.voice.ports import (
    LLMVoiceStreamPort,
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
        self, text: str, voice: str = "vi-VN-HoaiMyNeural",
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

    # Check state transitions: THINK -> SPEAK -> LISTEN
    states = [e["state"] for e in conn.events if e["type"] == VoiceEventType.STATE.value]
    assert VoiceSessionState.THINK.value in states
    assert VoiceSessionState.SPEAK.value in states
    assert states[-1] == VoiceSessionState.LISTEN.value
    assert len(tts.synthesized_sentences) >= 1
    assert any(e["type"] == VoiceEventType.DONE.value for e in conn.events)


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
    orch.conversation_history.append({"role": "assistant", "content": "Xin chào!"})

    await orch.handle_final_transcript("Em từng thiết kế kiến trúc microservices.", duration_seconds=10.0)
    assert orch._active_task is not None
    await orch._active_task

    # Events emitted: transcript, state, ai_token, subtitle, audio, done
    event_types = [e["type"] for e in conn.events]
    assert VoiceEventType.TRANSCRIPT.value in event_types
    assert VoiceEventType.AI_TOKEN.value in event_types
    assert VoiceEventType.SUBTITLE.value in event_types
    assert VoiceEventType.AUDIO.value in event_types
    assert VoiceEventType.DONE.value in event_types
    assert orch.state == VoiceSessionState.LISTEN


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
    orch.conversation_history.append({"role": "assistant", "content": "Xin chào"})

    # Trigger final transcript to begin generation
    await orch.handle_final_transcript("Em có câu hỏi.")
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
    orch.conversation_history.append({"role": "assistant", "content": "Xin chào"})

    # Trigger final transcript to begin generation
    await orch.handle_final_transcript("Câu hỏi là gì?")
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

    # Turn 1: Warm-up answer
    await orch.handle_final_transcript("Hôm nay trời rất đẹp, em rất sẵn sàng.")
    if orch._active_task:
        await orch._active_task

    # Since target turns for warmup is 1, it must transition directly to closing!
    assert orch.current_stage_index == 1
    assert orch.get_current_stage().id == "closing"

    stage_changes = [e for e in conn.events if e.get("type") == VoiceEventType.STAGE_CHANGE.value]
    assert len(stage_changes) == 1
    assert stage_changes[0]["stage_id"] == "closing"
    assert stage_changes[0]["stage_index"] == 2
    assert stage_changes[0]["total_stages"] == 2
