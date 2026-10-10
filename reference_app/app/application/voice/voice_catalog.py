from __future__ import annotations

import logging
import time
from typing import Any
import httpx

logger = logging.getLogger("VoiceCatalog")

# In-memory dynamic ElevenLabs cache
_dynamic_eleven_cache: list[dict[str, Any]] | None = None
_dynamic_eleven_cache_time: float = 0.0
DYNAMIC_CACHE_TTL_SECONDS = 180.0

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

# Curated Premium ElevenLabs Voices (Vietnamese Native, Japanese, and Multilingual Premade)
CURATED_ELEVEN_VOICES = [
    # --- Tiếng Việt Native & Professional Voices (Added on ElevenLabs) ---
    {
        "id": "9EE00wK5qV6tPtpQIxvy",
        "name": "Tuấn (Nam - Giọng Chuẩn Truyền Cảm • ElevenLabs)",
        "provider": "elevenlabs",
        "language": "vi",
        "gender": "male",
        "description": "Giọng nam tiếng Việt tự nhiên, điềm đạm, phong thái phỏng vấn chuyên nghiệp",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "K7ewtjKRNtwwt3lKQ6M0",
        "name": "Tony Hoàng (Nam - Miền Bắc Tự Tin • ElevenLabs)",
        "provider": "elevenlabs",
        "language": "vi",
        "gender": "male",
        "description": "Giọng nam miền Bắc đĩnh đạc, rõ nét, phản xạ phỏng vấn sắc sảo",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "w2KTJ6MO4SIK6nWK4YH8",
        "name": "Đức Huy (Nam - Miền Nam Tự Nhiên • ElevenLabs)",
        "provider": "elevenlabs",
        "language": "vi",
        "gender": "male",
        "description": "Giọng nam miền Nam gần gũi, trẻ trung, tự nhiên",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "mgBpvrNosWzExdPuRbXP",
        "name": "Phan Anh (Nam - Miền Nam Trầm Ấm • ElevenLabs)",
        "provider": "elevenlabs",
        "language": "vi",
        "gender": "male",
        "description": "Giọng nam miền Nam ấm áp, điềm đạm, phù hợp các vòng phỏng vấn chuyên sâu",
        "is_default": False,
        "is_premium": True,
    },

    # --- 日本語 Voices (ElevenLabs) ---
    {
        "id": "j210dv0vWm7fCknyQpbA",
        "name": "Hinata (Nam - 日本語 • ElevenLabs)",
        "provider": "elevenlabs",
        "language": "ja",
        "gender": "male",
        "description": "Giọng nam tiếng Nhật tự nhiên, tự tin, phong thái doanh nghiệp",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "WQz3clzUdMqvBf0jswZQ",
        "name": "Shizuka (Nữ - 日本語 • ElevenLabs)",
        "provider": "elevenlabs",
        "language": "ja",
        "gender": "female",
        "description": "Giọng nữ tiếng Nhật nhẹ nhàng, thanh lịch, chuẩn mực",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "3JDquces8E8bkmvbh6Bc",
        "name": "Otani (Nam - 日本語 • ElevenLabs)",
        "provider": "elevenlabs",
        "language": "ja",
        "gender": "male",
        "description": "Giọng nam tiếng Nhật điềm đạm, dày dạn kinh nghiệm",
        "is_default": False,
        "is_premium": True,
    },

    # --- Multilingual Premade Voices (Active for English / International) ---
    {
        "id": "JBFqnCBsd6RMkjVDRZzb",
        "name": "George (Tech Leader • Đa ngôn ngữ)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "male",
        "description": "Giọng nam trầm ấm, phát âm tự nhiên mọi ngôn ngữ và thuật ngữ quốc tế",
        "is_default": False,
        "is_premium": True,
    },
    {
        "id": "EXAVITQu4vr4xnSDxMaL",
        "name": "Sarah (Chuyên gia • Đa ngôn ngữ)",
        "provider": "elevenlabs",
        "language": "multi",
        "gender": "female",
        "description": "Giọng nữ trưởng thành, xử lý mượt mà mọi ngôn ngữ và tình huống song ngữ",
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


def fetch_account_elevenlabs_voices(api_key: str) -> list[dict[str, Any]]:
    """
    Dynamically fetch voices from user's ElevenLabs account using xi-api-key.
    Uses in-memory cache with 180s TTL to prevent redundant network calls.
    """
    global _dynamic_eleven_cache, _dynamic_eleven_cache_time
    now = time.time()
    if _dynamic_eleven_cache is not None and (now - _dynamic_eleven_cache_time) < DYNAMIC_CACHE_TTL_SECONDS:
        return _dynamic_eleven_cache

    if not api_key or not api_key.strip():
        return []

    try:
        res = httpx.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": api_key.strip()},
            timeout=4.0,
        )
        if res.status_code != 200:
            return []

        voices_data = res.json().get("voices", [])
        curated_ids = {v["id"] for v in CURATED_ELEVEN_VOICES}
        dynamic_items: list[dict[str, Any]] = []

        for v in voices_data:
            vid = v.get("voice_id")
            if not vid or vid in curated_ids:
                continue

            name = v.get("name", "ElevenLabs Voice")
            cat = v.get("category", "")
            labels = v.get("labels") or {}

            # Determine language
            v_lang = labels.get("language", "").lower()
            locale = labels.get("locale", "").lower()
            if v_lang == "vi" or "vi-vn" in locale or "vietnam" in name.lower():
                lang = "vi"
            elif v_lang == "ja" or "japan" in name.lower():
                lang = "ja"
            elif v_lang == "zh" or "chinese" in name.lower():
                lang = "zh"
            elif cat == "premade":
                lang = "multi"
            else:
                lang = v_lang or "multi"

            gender = labels.get("gender") or "neutral"
            desc = labels.get("descriptive") or labels.get("use_case") or f"Giọng đọc {name} trên ElevenLabs"
            accent = labels.get("accent") or ""
            if accent:
                desc = f"Giọng {accent}, {desc}"

            dynamic_items.append({
                "id": vid,
                "name": f"{name} (ElevenLabs)",
                "provider": "elevenlabs",
                "language": lang,
                "gender": gender,
                "description": desc,
                "is_default": False,
                "is_premium": True,
            })

        _dynamic_eleven_cache = dynamic_items
        _dynamic_eleven_cache_time = now
        return dynamic_items
    except Exception as exc:
        logger.debug("Dynamic ElevenLabs voices fetch skipped: %s", exc)
        return []


def get_voice_catalog_options(
    is_premium_user: bool,
    language: str | None = None,
    api_key: str = "",
) -> dict[str, Any]:
    """
    Returns full voice and STT catalog decorated with lock status.
    Merges native Edge voices, curated ElevenLabs voices, and dynamically fetched ElevenLabs voices.
    Optionally filters or prioritizes voices strictly compatible with the requested language.
    """
    voices: list[dict[str, Any]] = []

    # 1. Edge TTS voices (Free tier)
    for v in DEFAULT_EDGE_VOICES:
        item = dict(v)
        item["is_locked"] = False
        item["lock_reason"] = None
        voices.append(item)

    # 2. Curated ElevenLabs voices
    for v in CURATED_ELEVEN_VOICES:
        item = dict(v)
        item["is_locked"] = not is_premium_user
        item["lock_reason"] = (
            None if is_premium_user else "Dành riêng cho các gói Sprint hoặc Pro"
        )
        voices.append(item)

    # 3. Dynamically fetched ElevenLabs voices from user's account
    dynamic_eleven = fetch_account_elevenlabs_voices(api_key)
    for v in dynamic_eleven:
        item = dict(v)
        item["is_locked"] = not is_premium_user
        item["lock_reason"] = (
            None if is_premium_user else "Dành riêng cho các gói Sprint hoặc Pro"
        )
        voices.append(item)

    # Strict language filtering: keep matching language OR multilingual
    if language:
        lang_clean = language.lower().strip()
        voices = [v for v in voices if v.get("language") == lang_clean or v.get("language") == "multi"]

    # STT Engines
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