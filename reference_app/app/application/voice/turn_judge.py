from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class TurnJudgment:
    signal_scores: dict[str, float] = field(default_factory=dict)
    disposition: str = "uncertain"
    explicitly_no_more: bool = False
    source: str = "fallback"


class InterviewTurnJudge(Protocol):
    def judge(
        self,
        question: str,
        signals: list[str],
        evidence: dict[str, dict],
        answer: str,
        context: list[dict[str, str]],
    ) -> TurnJudgment:
        ...
