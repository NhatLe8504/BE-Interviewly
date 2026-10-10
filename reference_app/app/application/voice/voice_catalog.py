from __future__ import annotations

from typing import Any

# Default Edge TTS Voices (Included in Free tier, organized by language)
DEFAULT_EDGE_VOICES = [
    # Tiếng Việt (VI)
    {
        "id": "vi-VN-HoaiMyNeural",
        "name": "Hoài My (Nữ - Tiếng Việt)",
        "provider": "edge",
        "language": "vi",
        "gender": "female",
        "description": "Giọng nữ miền Bắc tự nhiên, truyền cảm, phát âm tiếng Việt chuẩn",
        "is_default": True,
        "is_premium": False,
    },
    {
        "id": "vi-VN-NamMinhNeural",
        "name": "Nam Minh (Nam - Tiếng Việt)",
        "provider": "edge",
        "language": "vi",
        "gender": "male",
        "description": "Giọng nam miền Bắc lịch thiệp, đĩnh đạc, rõ ràng",
        "is_default": False,
        "is_premium": False,
    },
    # English (EN)
    {
        "id": "en-US-JennyNeural",
        "name": "Jenny (Female - English)",
        "provider": "edge",
        "language": "en",
        "gender": "female",
        "description": "Natural, clear professional American English voice",
        "is_default": True,
        "is_premium": False,
    },
    {
        "id": "en-US-GuyNeural",
        "name": "Guy (Male - English)",
        "provider": "edge",
        "language": "en",
        "gender": "male",
        "description": "Confident, friendly corporate English voice",
        "is_default": False,
        "is_premium": False,
    },
    # 中文 (ZH)
    {
        "id": "zh-CN-XiaoxiaoNeural",
        "name": "Xiaoxiao (Female - 中文)",
        "provider": "edge",
        "language": "zh",
        "gender": "female",
        "description": "Giọng nữ tiếng Trung phổ thông tiêu chuẩn, tự nhiên",
        "is_default": True,
        "is_premium": False,
    },
    # 日本語 (JA)
    {
        "id": "ja-JP-NanamiNeural",
        "name": "Nanami (Female - 日本語)",
        "provider": "edge",
        "language": "ja",
        "gender": "female",
        "description": "Giọng nữ tiếng Nhật lịch thiệp, phong thái doanh nghiệp",
        "is_default": True,
        "is_premium": False,
    },
    # 한국어 (KO)
    {
        "id": "ko-KR-SunHiNeural",
        "name": "Sun-Hi (Female - 한국어)",
        "provider": "edge",
        "language": "ko",
        "gender": "female",
        "description": "Giọng nữ tiếng Hàn chuẩn mực, rõ ràng",
        "is_default": True,
        "is_premium": False,
    },
    # Français (FR)
    {
        "id": "fr-FR-DeniseNeural",
        "name": "Denise (Female - Français)",
        "provider": "edge",
        "language": "fr",
        "gender": "female",
        "description": "Giọng nữ tiếng Pháp thanh lịch, chuyên nghiệp",
        "is_default": True,
        "is_premium": False,
    },
    # Deutsch (DE)
    {
        "id": "de-DE-KatjaNeural",
        "name": "Katja (Female - Deutsch)",
        "provider": "edge",
        "language": "de",
        "gender": "female",
        "description": "Giọng nữ tiếng Đức chuẩn xác, bản lĩnh",
        "is_default": True,
        "is_premium": False,
    },
    # Español (ES)
    {
        "id": "es-ES-ElviraNeural",
        "name": "Elvira (Female - Español)",
        "provider": "edge",
        "language": "es",
        "gender": "female",
        "description": "Giọng nữ tiếng Tây Ban Nha ấm áp, tự tin",
        "is_default": True,
        "is_premium": False,
    },
]

# Premium ElevenLabs Voices (Active Multilingual Foundation Model - Supports Mixed Languages)
PREMIUM_ELEVEN_VOICES = [
    {
        "id": "JBFqnCBsd6RMkjVDRZzb",
        "name": "George (Tech Leader • Song ngữ Anh - Việt)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "male",
        "description": "Giọng nam trầm ấm, phát âm tự nhiên câu hỏi có chêm thuật ngữ tiếng Anh",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "EXAVITQu4vr4xnSDxMaL",
        "name": "Sarah (Chuyên gia • Song ngữ Anh - Việt)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "female",
        "description": "Giọng nữ trưởng thành, xử lý mượt mà câu trả lời đa ngôn ngữ",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "pNInz6obpgDQGcFmaJgB",
        "name": "Adam (Executive • Đa ngôn ngữ)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "male",
        "description": "Giọng nam truyền cảm, bản lĩnh lãnh đạo công nghệ, phát âm chuẩn quốc tế",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "TX3LPaxmHKxFdv7VOQHJ",
        "name": "Liam (Startup • Đa ngôn ngữ)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "male",
        "description": "Giọng nam năng động, hiện đại, thích hợp phỏng vấn công nghệ mới",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "pFZP5JQG7iQjIQuC4Bku",
        "name": "Lily (Warm • Đa ngôn ngữ)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "female",
        "description": "Giọng nữ ấm áp, giao tiếp gần gũi và tự nhiên",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "Xb7hH8MSUJpSbSDYk0k2",
        "name": "Alice (Professional • Đa ngôn ngữ)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "female",
        "description": "Giọng nữ tự tin, phát âm chuẩn xác mọi ngôn ngữ",
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


def get_voice_catalog_options(is_premium_user: bool, language: str | None = None) -> dict[str, Any]:
    """
    Returns full voice and STT catalog decorated with lock status.
    Optionally filters or prioritizes voices compatible with the requested language.
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

    if language:
        lang_clean = language.lower().strip()
        voices = [v for v in voices if v.get("language") in (lang_clean, "multi")]

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
