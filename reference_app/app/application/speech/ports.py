from __future__ import annotations

from typing import Protocol

from ...domain.speech import SpeechQualityMetrics


class SpeechQualityPort(Protocol):
    def analyze(
        self,
        text: str,
        duration_seconds: float,
        pause_duration_seconds: float = 0.0,
    ) -> SpeechQualityMetrics:
        ...
