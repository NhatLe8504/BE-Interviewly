from __future__ import annotations

from dataclasses import dataclass

from ...domain.speech import SpeechQualityMetrics
from .ports import SpeechQualityPort


@dataclass
class SpeechQualityService:
    analyzer: SpeechQualityPort

    def analyze_answer(
        self,
        text: str,
        duration_seconds: float,
        pause_duration_seconds: float = 0.0,
    ) -> SpeechQualityMetrics:
        return self.analyzer.analyze(
            text=text,
            duration_seconds=duration_seconds,
            pause_duration_seconds=pause_duration_seconds,
        )
