from __future__ import annotations

import asyncio
import re
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
    "zh": "zh-CN-XiaoxiaoNeural",
    "zh-CN": "zh-CN-XiaoxiaoNeural",
    "ja": "ja-JP-NanamiNeural",
    "ja-JP": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "ko-KR": "ko-KR-SunHiNeural",
    "fr": "fr-FR-DeniseNeural",
    "fr-FR": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "de-DE": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "es-ES": "es-ES-ElviraNeural",
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
    Supports voice pitch adjustment (+/-Hz) and in-memory caching.
    """

    def __init__(self, default_voice: str = "vi-VN-HoaiMyNeural") -> None:
        self.default_voice = default_voice
        self._cache: dict[tuple[str, str, str], bytes] = {}

    @staticmethod
    def _sanitize_pitch(pitch: str | int | float | None) -> str:
        """
        Sanitizes and bounds pitch to between -15Hz and +15Hz formatted as +XHz / -XHz.
        """
        if pitch is None:
            return "+0Hz"
        if isinstance(pitch, (int, float)):
            val = int(pitch)
            val = max(-15, min(15, val))
            return f"+{val}Hz" if val >= 0 else f"{val}Hz"
        clean = str(pitch).strip()
        m = re.match(r"^([+-]?\d+)(?:Hz)?$", clean, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            val = max(-15, min(15, val))
            return f"+{val}Hz" if val >= 0 else f"{val}Hz"
        return "+0Hz"

    def resolve_voice(self, voice: str | None) -> str:
        if not voice:
            return self.default_voice
        return VOICE_MAP.get(voice, voice)

    async def synthesize_stream(
        self, text: str, voice: str = "vi-VN-HoaiMyNeural", pitch: str = "+0Hz",
    ) -> AsyncIterator[bytes]:
        cleaned = text.strip()
        if not cleaned:
            return

        target_voice = self.resolve_voice(voice)
        target_pitch = self._sanitize_pitch(pitch)
        cache_key = (cleaned, target_voice, target_pitch)

        # Check in-memory audio cache for instant response
        if cache_key in self._cache:
            yield self._cache[cache_key]
            return

        try:
            if edge_tts is None:
                yield SILENT_MP3_FRAME
                return

            communicate = edge_tts.Communicate(cleaned, target_voice, pitch=target_pitch)
            chunks_collected: list[bytes] = []

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    data = chunk.get("data")
                    if data:
                        chunks_collected.append(data)
                        yield data

            # If no audio was received and pitch was non-zero, retry with default +0Hz
            if not chunks_collected and target_pitch != "+0Hz":
                comm_fallback = edge_tts.Communicate(cleaned, target_voice, pitch="+0Hz")
                async for chunk in comm_fallback.stream():
                    if chunk["type"] == "audio":
                        data = chunk.get("data")
                        if data:
                            chunks_collected.append(data)
                            yield data

            if not chunks_collected:
                yield SILENT_MP3_FRAME
            else:
                if len(self._cache) > 200:
                    self._cache.clear()
                self._cache[cache_key] = b"".join(chunks_collected)

        except Exception:
            # Fallback for network timeouts or parameter mismatch
            if target_pitch != "+0Hz":
                try:
                    comm_retry = edge_tts.Communicate(cleaned, target_voice, pitch="+0Hz")
                    async for chunk in comm_retry.stream():
                        if chunk["type"] == "audio":
                            data = chunk.get("data")
                            if data:
                                yield data
                    return
                except Exception:
                    pass
            yield SILENT_MP3_FRAME