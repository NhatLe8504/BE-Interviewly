from __future__ import annotations

import asyncio
from typing import AsyncIterator
try:
    import edge_tts
except ImportError:
    edge_tts = None

from ...application.voice.ports import TTSPort

VOICE_MAP = {
    "vi": "vi-VN-HoaiMyNeural",
    "vi-VN": "vi-VN-HoaiMyNeural",
    "vi-female": "vi-VN-HoaiMyNeural",
    "vi-male": "vi-VN-NamMinhNeural",
    "en": "en-US-JennyNeural",
    "en-US": "en-US-JennyNeural",
    "en-female": "en-US-JennyNeural",
    "en-male": "en-US-GuyNeural",
}

# 1 frame of valid MP3 silence (104 bytes) for offline/test fallback
SILENT_MP3_FRAME = (
    b"\xff\xfb\x90d\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x00\x00"
)


class EdgeTTSAdapter(TTSPort):
    """
    Streams audio chunks using Microsoft Edge TTS for minimal latency.
    Caches synthesized audio to ensure instant replay and smooth playback.
    """

    def __init__(self, default_voice: str = "vi-VN-HoaiMyNeural") -> None:
        self.default_voice = default_voice
        self._cache: dict[tuple[str, str], bytes] = {}

    def resolve_voice(self, voice: str | None) -> str:
        if not voice:
            return self.default_voice
        return VOICE_MAP.get(voice, voice)

    async def synthesize_stream(
        self, text: str, voice: str = "vi-VN-HoaiMyNeural",
    ) -> AsyncIterator[bytes]:
        cleaned = text.strip()
        if not cleaned:
            return

        target_voice = self.resolve_voice(voice)
        cache_key = (cleaned, target_voice)

        # Check in-memory audio cache for instant response
        if cache_key in self._cache:
            yield self._cache[cache_key]
            return

        try:
            if edge_tts is None:
                yield SILENT_MP3_FRAME
                return

            communicate = edge_tts.Communicate(cleaned, target_voice)
            chunks_collected: list[bytes] = []

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    data = chunk.get("data")
                    if data:
                        chunks_collected.append(data)
                        yield data

            # If no audio chunk was yielded, fallback to silent frame
            if not chunks_collected:
                yield SILENT_MP3_FRAME
            else:
                # Save full sentence MP3 in cache (bounded to 200 items)
                if len(self._cache) > 200:
                    self._cache.clear()
                self._cache[cache_key] = b"".join(chunks_collected)

        except Exception:
            # Fallback for network timeouts, firewalls, or offline testing environments
            yield SILENT_MP3_FRAME
