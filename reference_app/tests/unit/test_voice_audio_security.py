from __future__ import annotations

import pytest
from app.presentation.api.routers.voice_ws import SAFE_AUDIO_FILENAME_REGEX


def test_safe_audio_filename_regex_valid_names():
    valid_names = [
        "turn_1_ai.mp3",
        "turn_2_user.webm",
        "turn_10_user.wav",
        "turn_99_user.ogg",
        "turn_100_user.mp3",
        "turn_101_user.m4a",
        "turn_102_user.mp4",
    ]
    for name in valid_names:
        assert SAFE_AUDIO_FILENAME_REGEX.match(name) is not None, f"Expected {name} to be valid"


def test_safe_audio_filename_regex_rejects_path_traversal_and_malicious_names():
    invalid_names = [
        "../turn_1_ai.mp3",
        "..\\turn_1_ai.mp3",
        "turn_1_ai.mp3/../etc/passwd",
        "turn_1.mp3",
        "turn_user.webm",
        "turn_1_ai.exe",
        "turn_1_user.sh",
        "turn_1_user.php",
        "turn_1_user.js",
        "turn_abc_user.webm",
        "/etc/passwd",
        "C:\\Windows\\System32\\cmd.exe",
    ]
    for name in invalid_names:
        assert SAFE_AUDIO_FILENAME_REGEX.match(name) is None, f"Expected {name} to be rejected"


def test_mime_type_stripping_with_parameters():
    raw_content_types = [
        ("audio/webm;codecs=opus", "audio/webm"),
        ("audio/webm; codecs=opus", "audio/webm"),
        ("audio/ogg; codecs=opus", "audio/ogg"),
        ("audio/mp4; codecs=mp4a.40.2", "audio/mp4"),
        ("audio/webm", "audio/webm"),
    ]
    for raw, expected in raw_content_types:
        base = raw.lower().strip().split(";")[0].strip()
        assert base == expected
