from __future__ import annotations

import logging
from typing import AsyncIterator

import httpx

from ...application.voice.ports import TTSFallbackNotice, TTSPort


logger = logging.getLogger("VieNeuTTSAdapter")
VIENEU_VOICES = {"vieneu:Ngọc Lan": "Ngọc Lan", "vieneu:Kim Chi": "Kim Chi"}


class VieNeuTTSAdapter(TTSPort):
    def __init__(self, api_key: str, fallback: TTSPort) -> None:
        self.api_key = api_key.strip()
        self.fallback = fallback
        self._cache: dict[tuple[str, str], bytes] = {}

    async def synthesize_stream(
        self, text: str, voice: str = "vi-VN-HoaiMyNeural", pitch: str = "+0Hz",
    ) -> AsyncIterator[bytes | TTSFallbackNotice]:
        cleaned = text.strip()
        if not cleaned:
            return

        if voice not in VIENEU_VOICES or not self.api_key:
            edge_voice = "vi-VN-HoaiMyNeural" if voice.startswith("vieneu:") else voice
            if voice.startswith("vieneu:"):
                yield TTSFallbackNotice("backup")
            async for chunk in self.fallback.synthesize_stream(cleaned, voice=edge_voice, pitch=pitch):
                yield chunk
            return

        cache_key = (cleaned, voice)
        if cache_key in self._cache:
            yield self._cache[cache_key]
            return

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.vieneu.io/api/v1/audio/speech",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": "vieneu-v4",
                        "input": cleaned,
                        "voice": VIENEU_VOICES[voice],
                        "response_format": "mp3",
                    },
                )
            if response.status_code != 200:
                raise RuntimeError(f"VieNeu returned HTTP {response.status_code}")
            audio = response.content
            has_mp3_header = audio.startswith(b"ID3") or (
                len(audio) >= 2 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0
            )
            if len(audio) < 128 or not has_mp3_header:
                raise RuntimeError("VieNeu returned invalid MP3 audio")
        except (httpx.HTTPError, RuntimeError) as exc:
            logger.warning("VieNeu synthesis unavailable (%s); falling back to Edge TTS", exc)
            yield TTSFallbackNotice("backup")
            try:
                async for chunk in self.fallback.synthesize_stream(
                    cleaned, voice="vi-VN-HoaiMyNeural", pitch="+0Hz",
                ):
                    yield chunk
            except Exception as fallback_exc:
                logger.warning("Edge TTS backup unavailable (%s); using browser TTS", fallback_exc)
                yield TTSFallbackNotice("browser")
            return

        if len(self._cache) >= 200:
            self._cache.clear()
        self._cache[cache_key] = audio
        yield audio
