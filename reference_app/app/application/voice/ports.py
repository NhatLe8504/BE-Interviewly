from __future__ import annotations

from typing import Any, AsyncIterator, Protocol


class TTSPort(Protocol):
    async def synthesize_stream(
        self, text: str, voice: str = "vi-VN-HoaiMyNeural",
    ) -> AsyncIterator[bytes]:
        ...


class VoiceConnectionPort(Protocol):
    async def send_event(self, event: dict[str, Any]) -> None:
        ...

    def is_open(self) -> bool:
        ...


class LLMVoiceStreamPort(Protocol):
    async def stream_ai_tokens(
        self, messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        ...
