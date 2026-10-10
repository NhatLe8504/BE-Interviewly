from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator
import httpx

from ...application.voice.ports import TTSPort
from .edge_tts_adapter import EdgeTTSAdapter, SILENT_MP3_FRAME

logger = logging.getLogger("ElevenLabsTTSAdapter")

# Curated ElevenLabs Voice aliases mapping (matching account premade voices)
ELEVEN_VOICE_MAP = {
    "george": "JBFqnCBsd6RMkjVDRZzb",
    "sarah": "EXAVITQu4vr4xnSDxMaL",
    "adam": "pNInz6obpgDQGcFmaJgB",
    "liam": "TX3LPaxmHKxFdv7VOQHJ",
    "lily": "pFZP5JQG7iQjIQuC4Bku",
    "alice": "Xb7hH8MSUJpSbSDYk0k2",
    "rachel": "EXAVITQu4vr4xnSDxMaL",  # Alias to Sarah if requested
    "charlie": "IKne3meq5aSn9XLyUdCD",
    "roger": "CwhRBWXzGAHq8TQ4Fs17",
    "laura": "FGY2WhTYpPnrIDTdsKH5",
}


class ElevenLabsTTSAdapter(TTSPort):
    """
    Adapter implementing TTSPort using ElevenLabs Text-to-Speech API.
    Gracefully falls back to EdgeTTSAdapter if ElevenLabs is unavailable,
    quota exceeded, or for native Edge voices.
    """

    def __init__(
        self,
        api_key: str = "",
        fallback_adapter: TTSPort | None = None,
        default_model: str = "eleven_multilingual_v2",
    ) -> None:
        self.api_key = api_key.strip()
        self.fallback = fallback_adapter or EdgeTTSAdapter()
        self.default_model = default_model
        self._cache: dict[tuple[str, str], bytes] = {}

    def is_eleven_voice(self, voice: str) -> bool:
        if not voice:
            return False
        clean = voice.lower().strip()
        if clean.startswith("elevenlabs-"):
            clean = clean.replace("elevenlabs-", "")
        if clean in ELEVEN_VOICE_MAP or clean in ELEVEN_VOICE_MAP.values():
            return True
        # If it's a 20-character ElevenLabs ID
        if len(clean) == 20 and not clean.startswith(("vi-", "en-", "zh-", "ja-", "ko-")):
            return True
        return False

    def resolve_voice_id(self, voice: str) -> str:
        clean = voice.lower().strip()
        if clean.startswith("elevenlabs-"):
            clean = clean.replace("elevenlabs-", "")
        return ELEVEN_VOICE_MAP.get(clean, voice)

    async def synthesize_stream(
        self, text: str, voice: str = "vi-VN-HoaiMyNeural",
    ) -> AsyncIterator[bytes]:
        cleaned = text.strip()
        if not cleaned:
            return

        is_eleven = self.is_eleven_voice(voice)

        # If it's an Edge voice or ElevenLabs API key is missing, delegate to fallback safely
        if not is_eleven or not self.api_key:
            safe_edge_voice = voice if not is_eleven else "vi-VN-HoaiMyNeural"
            async for chunk in self.fallback.synthesize_stream(cleaned, safe_edge_voice):
                yield chunk
            return

        voice_id = self.resolve_voice_id(voice)
        cache_key = (cleaned, voice_id)

        # Check in-memory audio cache
        if cache_key in self._cache:
            yield self._cache[cache_key]
            return

        # Call ElevenLabs Stream endpoint
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        payload = {
            "text": cleaned,
            "model_id": self.default_model,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        }

        chunks_collected: list[bytes] = []
        try:
            async with httpx.AsyncClient(timeout=18.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        err_body = await response.aread()
                        logger.warning(
                            "ElevenLabs TTS failed with status %d: %s. Falling back to EdgeTTS.",
                            response.status_code,
                            err_body[:200],
                        )
                        # Fallback to EdgeTTS with safe voice
                        async for chunk in self.fallback.synthesize_stream(cleaned, "vi-VN-HoaiMyNeural"):
                            yield chunk
                        return

                    async for raw_chunk in response.aiter_bytes():
                        if raw_chunk:
                            chunks_collected.append(raw_chunk)
                            yield raw_chunk

            if chunks_collected:
                full_mp3 = b"".join(chunks_collected)
                if len(self._cache) > 200:
                    self._cache.clear()
                self._cache[cache_key] = full_mp3
            else:
                async for chunk in self.fallback.synthesize_stream(cleaned, "vi-VN-HoaiMyNeural"):
                    yield chunk

        except Exception as exc:
            logger.warning("ElevenLabs request error: %s. Falling back to EdgeTTS.", exc)
            async for chunk in self.fallback.synthesize_stream(cleaned, "vi-VN-HoaiMyNeural"):
                yield chunk
