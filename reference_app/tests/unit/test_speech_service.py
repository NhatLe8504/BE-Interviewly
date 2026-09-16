from __future__ import annotations

from app.application.speech.service import SpeechQualityService
from app.infrastructure.speech.text_analyzer import RegexSpeechTextAnalyzer


def test_speech_analyzer_vietnamese_fillers() -> None:
    analyzer = RegexSpeechTextAnalyzer()
    service = SpeechQualityService(analyzer=analyzer)

    sample_vn = "Dạ ừm em nghĩ là kiểu như là dự án này thì là mà gặp lỗi à."
    metrics = service.analyze_answer(sample_vn, duration_seconds=10.0, pause_duration_seconds=2.0)

    assert metrics.wpm_metrics.filler_count >= 3
    assert "ừm" in metrics.wpm_metrics.filler_words
    assert "kiểu như là" in metrics.wpm_metrics.filler_words
    assert metrics.wpm_metrics.wpm > 0


def test_speech_analyzer_english_fillers() -> None:
    analyzer = RegexSpeechTextAnalyzer()
    sample_en = "Um, I basically resolved the bug, you know, like very quickly."
    metrics = analyzer.analyze(sample_en, duration_seconds=12.0)

    assert metrics.wpm_metrics.filler_count >= 3
    assert "um" in metrics.wpm_metrics.filler_words
    assert "basically" in metrics.wpm_metrics.filler_words
    assert "you know" in metrics.wpm_metrics.filler_words
