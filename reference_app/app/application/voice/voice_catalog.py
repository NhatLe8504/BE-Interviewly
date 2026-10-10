from __future__ import annotations

from typing import Any

# Default Edge TTS Voices (Included in Free tier)
DEFAULT_EDGE_VOICES = [
    {
        "id": "vi-VN-HoaiMyNeural",
        "name": "Hoài My (Nữ)",
        "provider": "edge",
        "language": "vi",
        "gender": "female",
        "description": "Giọng nữ miền Bắc tự nhiên, truyền cảm",
        "is_default": True,
        "is_premium": False,
    },
    {
        "id": "vi-VN-NamMinhNeural",
        "name": "Nam Minh (Nam)",
        "provider": "edge",
        "language": "vi",
        "gender": "male",
        "description": "Giọng nam miền Bắc lịch thiệp, đĩnh đạc",
        "is_default": False,
        "is_premium": False,
    },
    {
        "id": "en-US-JennyNeural",
        "name": "Jenny (Female - US)",
        "provider": "edge",
        "language": "en",
        "gender": "female",
        "description": "Natural, clear professional English voice",
        "is_default": True,
        "is_premium": False,
    },
    {
        "id": "en-US-GuyNeural",
        "name": "Guy (Male - US)",
        "provider": "edge",
        "language": "en",
        "gender": "male",
        "description": "Confident, friendly corporate English voice",
        "is_default": False,
        "is_premium": False,
    },
]

# Premium ElevenLabs Voices (Active Premade Voices in Workspace)
PREMIUM_ELEVEN_VOICES = [
    {
        "id": "JBFqnCBsd6RMkjVDRZzb",
        "name": "George (Storyteller / Tech Leader)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "male",
        "description": "Giọng nam trầm ấm, già dặn, chuẩn mực giám đốc kỹ thuật",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "EXAVITQu4vr4xnSDxMaL",
        "name": "Sarah (Mature & Confident)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "female",
        "description": "Giọng nữ trưởng thành, điềm đạm, cực kỳ tự nhiên",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "pNInz6obpgDQGcFmaJgB",
        "name": "Adam (Executive Male)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "male",
        "description": "Giọng nam truyền cảm, bản lĩnh lãnh đạo công nghệ",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "TX3LPaxmHKxFdv7VOQHJ",
        "name": "Liam (Energetic Male)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "male",
        "description": "Giọng nam năng động, hiện đại, phong thái startup",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "pFZP5JQG7iQjIQuC4Bku",
        "name": "Lily (Warm Female)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "female",
        "description": "Giọng nữ ấm áp, gần gũi, thấu cảm",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "Xb7hH8MSUJpSbSDYk0k2",
        "name": "Alice (Confident Female)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "female",
        "description": "Giọng nữ tự tin, rõ ràng, phong thái chuyên nghiệp",
        "is_default": False,
        "is_premium": True,
    },
]

# STT Providers
STT_ENGINES = [
    {
        "id": "browser_speech",
        "name": "Web Speech API (Trình duyệt)",
        "provider": "browser",
        "description": "Nhận diện giọng nói trực tiếp qua Microphone trình duyệt (Mặc định)",
        "is_default": True,
        "is_premium": False,
    },
    {
        "id": "whisper_pro",
        "name": "Whisper Cloud AI (Đa âm sắc)",
        "provider": "whisper",
        "description": "Bộ nhận diện AI độ chính xác cao, lọc tạp âm và nhận diện chuẩn xác",
        "is_default": False,
        "is_premium": True,
    },
]


def get_voice_catalog_options(is_premium_user: bool) -> dict[str, Any]:
    """
    Returns full voice and STT catalog decorated with lock status for the current user.
    """
    voices: list[dict[str, Any]] = []

    for v in DEFAULT_EDGE_VOICES:
        item = dict(v)
        item["is_locked"] = False
        item["lock_reason"] = None
        voices.append(item)

    for v in PREMIUM_ELEVEN_VOICES:
        item = dict(v)
        item["is_locked"] = not is_premium_user
        item["lock_reason"] = (
            None if is_premium_user else "Dành riêng cho các gói Sprint hoặc Pro"
        )
        voices.append(item)

    stt: list[dict[str, Any]] = []
    for s in STT_ENGINES:
        item = dict(s)
        item["is_locked"] = not is_premium_user if item["is_premium"] else False
        item["lock_reason"] = (
            None
            if (is_premium_user or not item["is_premium"])
            else "Dành riêng cho các gói Sprint hoặc Pro"
        )
        stt.append(item)

    return {
        "is_premium_user": is_premium_user,
        "voices": voices,
        "stt_engines": stt,
    }
