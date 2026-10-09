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

# Premium ElevenLabs Voices (Available for Paid tiers, locked on Free)
PREMIUM_ELEVEN_VOICES = [
    {
        "id": "21m00Tcm4TlvDq8ikWAM",
        "name": "Rachel (Studio Female)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "female",
        "description": "Giọng chuẩn quốc tế, điềm đạm, cực kỳ tự nhiên",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "pNInz6obpgDQGcFmaJgB",
        "name": "Adam (Executive Male)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "male",
        "description": "Giọng nam trầm ấm, bản lĩnh lãnh đạo công nghệ",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "AZnzlk1XvdvUeBnXmlld",
        "name": "Domi (Confident Female)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "female",
        "description": "Giọng nữ năng động, rõ ràng, phong thái startup",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "ErXwobaYiN019PkySvjV",
        "name": "Antoni (Calm Male)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "male",
        "description": "Giọng nam điềm tĩnh, chuyên gia phỏng vấn",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "EXAVITQu4vr4xnSDxMaL",
        "name": "Bella (Warm Female)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "female",
        "description": "Giọng nữ biểu cảm cao, gần gũi, thấu cảm",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "JBFqnCBsd6RMkjVDRZzb",
        "name": "George (Senior Leader)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "male",
        "description": "Giọng nam già dặn, chuẩn mực giám đốc kỹ thuật",
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
        "id": "elevenlabs_scribe",
        "name": "ElevenLabs Scribe v2",
        "provider": "elevenlabs",
        "description": "Bộ nhận diện AI độ chính xác cao, tự động lọc tạp âm",
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
