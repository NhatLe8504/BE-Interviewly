from __future__ import annotations

from dataclasses import dataclass

from .errors import DomainValidationError


@dataclass(frozen=True)
class WpmCalculation:
    total_words: int
    duration_seconds: float
    pause_duration_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.total_words < 0:
            raise DomainValidationError("total_words cannot be negative")
        if self.duration_seconds < 0.0:
            raise DomainValidationError("duration_seconds cannot be negative")
        if self.pause_duration_seconds < 0.0:
            raise DomainValidationError("pause_duration_seconds cannot be negative")
        if self.pause_duration_seconds > self.duration_seconds and self.duration_seconds > 0:
            raise DomainValidationError("pause duration cannot exceed total duration")

    def calculate_effective_wpm(self) -> float:
        effective_time = self.duration_seconds - self.pause_duration_seconds
        if effective_time <= 0.0 or self.total_words == 0:
            return 0.0
        return round((self.total_words / effective_time) * 60.0, 2)


@dataclass(frozen=True)
class FillerWordRecord:
    word: str
    count: int

    def __post_init__(self) -> None:
        if not self.word.strip():
            raise DomainValidationError("filler word must not be blank")
        if self.count < 0:
            raise DomainValidationError("count cannot be negative")


@dataclass(frozen=True)
class WpmMetrics:
    wpm: float
    pause_duration: float
    filler_count: int
    filler_words: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.wpm < 0.0:
            raise DomainValidationError("wpm cannot be negative")
        if self.pause_duration < 0.0:
            raise DomainValidationError("pause_duration cannot be negative")
        if self.filler_count < 0:
            raise DomainValidationError("filler_count cannot be negative")


def assess_speaking_pace(wpm: float) -> str:
    if wpm <= 0.0:
        return "No speech detected"
    if wpm < 110.0:
        return "Too slow"
    if wpm <= 160.0:
        return "Optimal"
    return "Too fast"


@dataclass(frozen=True)
class SpeechQualityMetrics:
    wpm_metrics: WpmMetrics
    pace_assessment: str = ""
    tips: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.pace_assessment:
            assessment = assess_speaking_pace(self.wpm_metrics.wpm)
            object.__setattr__(self, "pace_assessment", assessment)
