from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Protocol

from ...domain.voice import VoiceSessionState  # noqa: F401


@dataclass(frozen=True)
class TTSFallbackNotice:
    phase: Literal["backup", "browser"]


class TTSPort(Protocol):
    async def synthesize_stream(
        self, text: str, voice: str = "vi-VN-HoaiMyNeural", pitch: str = "+0Hz",
    ) -> AsyncIterator[bytes | TTSFallbackNotice]:
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
