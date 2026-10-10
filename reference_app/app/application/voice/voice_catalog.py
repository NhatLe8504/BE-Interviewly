from __future__ import annotations

from typing import Any

# Default Edge TTS Voices (Included in Free tier, organized by language - Native, High Quality)
DEFAULT_EDGE_VOICES = [
    # Tiếng Việt (VI)
    {
        "id": "vi-VN-HoaiMyNeural",
        "name": "Hoài My (Nữ - Tiếng Việt Chuẩn)",
        "provider": "edge",
        "language": "vi",
        "gender": "female",
        "description": "Giọng nữ miền Bắc tự nhiên, truyền cảm, phát âm tiếng Việt chuẩn xác",
        "is_default": True,
        "is_premium": False,
    },
    {
        "id": "vi-VN-NamMinhNeural",
        "name": "Nam Minh (Nam - Tiếng Việt Chuẩn)",
        "provider": "edge",
        "language": "vi",
        "gender": "male",
        "description": "Giọng nam miền Bắc lịch thiệp, đĩnh đạc, rõ ràng, phong thái chuyên gia",
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
        "name": "Xiaoxiao (Nữ - 中文)",
        "provider": "edge",
        "language": "zh",
        "gender": "female",
        "description": "Giọng nữ tiếng Trung phổ thông tiêu chuẩn, tự nhiên",
        "is_default": True,
        "is_premium": False,
    },
    {
        "id": "zh-CN-YunxiNeural",
        "name": "Yunxi (Nam - 中文)",
        "provider": "edge",
        "language": "zh",
        "gender": "male",
        "description": "Giọng nam tiếng Trung đĩnh đạc, rõ ràng",
        "is_default": False,
        "is_premium": False,
    },
    # 日本語 (JA)
    {
        "id": "ja-JP-NanamiNeural",
        "name": "Nanami (Nữ - 日本語)",
        "provider": "edge",
        "language": "ja",
        "gender": "female",
        "description": "Giọng nữ tiếng Nhật lịch thiệp, phong thái doanh nghiệp",
        "is_default": True,
        "is_premium": False,
    },
    {
        "id": "ja-JP-KeitaNeural",
        "name": "Keita (Nam - 日本語)",
        "provider": "edge",
        "language": "ja",
        "gender": "male",
        "description": "Giọng nam tiếng Nhật chuẩn mực, điềm đạm",
        "is_default": False,
        "is_premium": False,
    },
    # 한국어 (KO)
    {
        "id": "ko-KR-SunHiNeural",
        "name": "Sun-Hi (Nữ - 한국어)",
        "provider": "edge",
        "language": "ko",
        "gender": "female",
        "description": "Giọng nữ tiếng Hàn chuẩn mực, rõ ràng",
        "is_default": True,
        "is_premium": False,
    },
    {
        "id": "ko-KR-InJoonNeural",
        "name": "InJoon (Nam - 한국어)",
        "provider": "edge",
        "language": "ko",
        "gender": "male",
        "description": "Giọng nam tiếng Hàn lịch sự, phong thái công sở",
        "is_default": False,
        "is_premium": False,
    },
    # Français (FR)
    {
        "id": "fr-FR-DeniseNeural",
        "name": "Denise (Nữ - Français)",
        "provider": "edge",
        "language": "fr",
        "gender": "female",
        "description": "Giọng nữ tiếng Pháp thanh lịch, chuyên nghiệp",
        "is_default": True,
        "is_premium": False,
    },
    {
        "id": "fr-FR-HenriNeural",
        "name": "Henri (Nam - Français)",
        "provider": "edge",
        "language": "fr",
        "gender": "male",
        "description": "Giọng nam tiếng Pháp trang nhã, đĩnh đạc",
        "is_default": False,
        "is_premium": False,
    },
    # Deutsch (DE)
    {
        "id": "de-DE-KatjaNeural",
        "name": "Katja (Nữ - Deutsch)",
        "provider": "edge",
        "language": "de",
        "gender": "female",
        "description": "Giọng nữ tiếng Đức chuẩn xác, bản lĩnh",
        "is_default": True,
        "is_premium": False,
    },
    {
        "id": "de-DE-ConradNeural",
        "name": "Conrad (Nam - Deutsch)",
        "provider": "edge",
        "language": "de",
        "gender": "male",
        "description": "Giọng nam tiếng Đức chuyên nghiệp",
        "is_default": False,
        "is_premium": False,
    },
    # Español (ES)
    {
        "id": "es-ES-ElviraNeural",
        "name": "Elvira (Nữ - Español)",
        "provider": "edge",
        "language": "es",
        "gender": "female",
        "description": "Giọng nữ tiếng Tây Ban Nha ấm áp, tự tin",
        "is_default": True,
        "is_premium": False,
    },
    {
        "id": "es-ES-AlvaroNeural",
        "name": "Alvaro (Nam - Español)",
        "provider": "edge",
        "language": "es",
        "gender": "male",
        "description": "Giọng nam tiếng Tây Ban Nha trầm ấm, tự nhiên",
        "is_default": False,
        "is_premium": False,
    },
]

# Premium Premade ElevenLabs Voices (Active for English / International)
# Premium Voices (Tối ưu tài khoản Free - toàn bộ sử dụng Edge TTS chất lượng cao)
PREMIUM_ELEVEN_VOICES: list[dict[str, Any]] = []

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


def get_voice_catalog_options(
    is_premium_user: bool,
    language: str | None = None,
    api_key: str = "",
) -> dict[str, Any]:
    """
    Returns full voice and STT catalog decorated with lock status.
    Optionally filters or prioritizes voices strictly compatible with the requested language.
    """
    voices: list[dict[str, Any]] = []

    for v in DEFAULT_EDGE_VOICES:
        item = dict(v)
        item["is_locked"] = False
        item["lock_reason"] = None
        voices.append(item)

    for v in PREMIUM_ELEVEN_VOICES:
        item = dict(v)
        item["is_locked"] = False
        item["lock_reason"] = None
        voices.append(item)

    # Lọc nghiêm ngặt: chỉ giữ giọng của ngôn ngữ được chọn HOẶC giọng đa ngôn ngữ (multi)
    if language:
        lang_clean = language.lower().strip()
        voices = [v for v in voices if v.get("language") == lang_clean or v.get("language") == "multi"]

    stt: list[dict[str, Any]] = []
    for s in STT_ENGINES:
        item = dict(s)
        item["is_locked"] = False
        item["lock_reason"] = None
        stt.append(item)

    return {
        "is_premium_user": is_premium_user,
        "voices": voices,
        "stt_engines": stt,
    }