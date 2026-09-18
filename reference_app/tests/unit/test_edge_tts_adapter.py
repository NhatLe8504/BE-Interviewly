from __future__ import annotations

import pytest
from app.infrastructure.tts.edge_tts_adapter import EdgeTTSAdapter


def test_edge_tts_voice_resolution() -> None:
    adapter = EdgeTTSAdapter()
    assert adapter.resolve_voice("vi") == "vi-VN-HoaiMyNeural"
    assert adapter.resolve_voice("vi-male") == "vi-VN-NamMinhNeural"
    assert adapter.resolve_voice("en") == "en-US-JennyNeural"
    assert adapter.resolve_voice("en-male") == "en-US-GuyNeural"
    assert adapter.resolve_voice("custom-voice") == "custom-voice"


@pytest.mark.anyio
async def test_edge_tts_synthesize_empty_text() -> None:
    adapter = EdgeTTSAdapter()
    chunks = []
    async for chunk in adapter.synthesize_stream("   "):
        chunks.append(chunk)
    assert len(chunks) == 0


@pytest.mark.anyio
async def test_edge_tts_synthesize_valid_fallback() -> None:
    adapter = EdgeTTSAdapter()
    chunks = []
    async for chunk in adapter.synthesize_stream("Xin chào bạn"):
        chunks.append(chunk)
    assert len(chunks) > 0
    assert len(chunks[0]) > 0
