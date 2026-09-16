from __future__ import annotations

import re

from ...application.speech.ports import SpeechQualityPort
from ...domain.speech import (
    SpeechQualityMetrics,
    WpmCalculation,
    WpmMetrics,
)

FILLER_PATTERNS = [
    # Vietnamese fillers (compound phrases first)
    (r"\bkiểu như là\b", "kiểu như là"),
    (r"\bkiểu là\b", "kiểu là"),
    (r"\bkiểu như\b", "kiểu như"),
    (r"\bthì là mà\b", "thì là mà"),
    (r"\bthì là\b", "thì là"),
    (r"\bnói chung là\b", "nói chung là"),
    (r"\bừm\b", "ừm"),
    (r"\bờ\b", "ờ"),
    (r"\bà\b", "à"),
    # English fillers
    (r"\byou know\b", "you know"),
    (r"\bi mean\b", "i mean"),
    (r"\bsort of\b", "sort of"),
    (r"\bkind of\b", "kind of"),
    (r"\bactually\b", "actually"),
    (r"\bbasically\b", "basically"),
    (r"\bum\b", "um"),
    (r"\buh\b", "uh"),
    (r"\blike\b", "like"),
]


class RegexSpeechTextAnalyzer(SpeechQualityPort):
    def count_words(self, text: str) -> int:
        words = re.findall(r"\b\w+\b", text.strip())
        return len(words)

    def extract_filler_words(self, text: str) -> tuple[int, list[str]]:
        lower_text = text.lower()
        found_fillers: list[str] = []
        total_count = 0

        for pattern, word in FILLER_PATTERNS:
            matches = re.findall(pattern, lower_text, flags=re.IGNORECASE)
            if matches:
                count = len(matches)
                total_count += count
                found_fillers.extend([word] * count)
                lower_text = re.sub(pattern, " ", lower_text, flags=re.IGNORECASE)

        return total_count, found_fillers

    def analyze(
        self,
        text: str,
        duration_seconds: float,
        pause_duration_seconds: float = 0.0,
    ) -> SpeechQualityMetrics:
        total_words = self.count_words(text)
        safe_duration = max(0.0, float(duration_seconds))
        safe_pause = min(safe_duration, max(0.0, float(pause_duration_seconds)))

        calc = WpmCalculation(
            total_words=total_words,
            duration_seconds=safe_duration,
            pause_duration_seconds=safe_pause,
        )
        effective_wpm = calc.calculate_effective_wpm()
        filler_count, filler_list = self.extract_filler_words(text)

        tips: list[str] = []
        if effective_wpm < 110.0 and effective_wpm > 0.0:
            tips.append("Hãy tăng tốc độ nói một chút để câu trả lời mạch lạc và tự tin hơn.")
        elif effective_wpm > 165.0:
            tips.append("Bạn đang nói hơi nhanh, hãy thở sâu và nói chậm lại để người nghe kịp nắm bắt ý.")

        if filler_count > 3:
            tips.append(f"Bạn đã sử dụng {filler_count} từ đệm. Hãy dừng lại 1 giây thay vì dùng từ đệm như 'ừm', 'à', 'like'.")

        metrics = SpeechQualityMetrics(
            wpm_metrics=WpmMetrics(
                wpm=effective_wpm,
                pause_duration=safe_pause,
                filler_count=filler_count,
                filler_words=tuple(sorted(set(filler_list))),
            ),
            tips=tuple(tips),
        )
        return metrics
