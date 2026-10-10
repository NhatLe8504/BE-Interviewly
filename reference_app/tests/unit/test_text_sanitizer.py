from __future__ import annotations

import pytest
from app.application.voice.text_sanitizer import sanitize_spoken_text


def test_sanitize_empty_and_plain() -> None:
    assert sanitize_spoken_text("") == ""
    assert sanitize_spoken_text("Chào bạn, bạn có khỏe không?") == "Chào bạn, bạn có khỏe không?"


def test_sanitize_markdown_bold_and_italics() -> None:
    raw = "Chào bạn! Tôi thấy bạn có kinh nghiệm với **Spring Boot** và *Kafka*, thật tuyệt."
    expected = "Chào bạn! Tôi thấy bạn có kinh nghiệm với Spring Boot và Kafka, thật tuyệt."
    assert sanitize_spoken_text(raw) == expected


def test_sanitize_markdown_headers_and_lists() -> None:
    raw = """### Câu hỏi chuyên môn:
1. Bạn đã thiết kế database ra sao?
2. Hãy nêu cách đánh index trong PostgreSQL."""
    expected = "Câu hỏi chuyên môn: Bạn đã thiết kế database ra sao? Hãy nêu cách đánh index trong PostgreSQL."
    assert sanitize_spoken_text(raw) == expected


def test_sanitize_code_blocks_and_backticks() -> None:
    raw = "Bạn hãy giải thích đoạn code sau: `def test(): pass` và lý do sử dụng ```python print(1) ```"
    expected = "Bạn hãy giải thích đoạn code sau: def test(): pass và lý do sử dụng print(1)"
    assert sanitize_spoken_text(raw) == expected


def test_sanitize_bullet_points_and_quotes() -> None:
    raw = """- Về câu hỏi này:
> Tôi rất đồng tình với bạn.
- Bạn hãy chia sẻ thêm nhé."""
    expected = "Về câu hỏi này: Tôi rất đồng tình với bạn. Bạn hãy chia sẻ thêm nhé."
    assert sanitize_spoken_text(raw) == expected