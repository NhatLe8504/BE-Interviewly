from __future__ import annotations

import logging
import math
import time

from ...application.voice.turn_judge import TurnJudgment
from .jev_adapter import JevSystemOneAdapter

logger = logging.getLogger(__name__)

_LEVELS = (
    "No relevant evidence for this criterion.",
    "Mentions the criterion without a concrete explanation.",
    "Explains the criterion with a concrete example or method.",
    "Explains and verifies the criterion with a concrete outcome or trade-off.",
)
_DISPOSITIONS = {
    "responsive": "The answer addresses the interview question.",
    "needs_clarification": "The answer is relevant but ambiguous or incomplete.",
    "cannot_answer": "The candidate explicitly says they cannot answer.",
    "off_topic": "The answer does not address the interview question.",
}


class JevInterviewTurnJudge:
    def __init__(self, api_key: str, api_url: str, model: str) -> None:
        self.client = JevSystemOneAdapter(api_key=api_key, api_url=api_url, model=model, timeout=5.0)

    def judge(
        self,
        question: str,
        signals: list[str],
        evidence: dict[str, dict],
        answer: str,
        context: list[dict[str, str]],
    ) -> TurnJudgment:
        if not self.client.is_available():
            return TurnJudgment()
        bounded_signals = [str(signal).strip()[:160] for signal in signals[:6] if str(signal).strip()]
        questions = {
            f"signal_{index}": {
                "type": "score",
                "instructions": f"Rate accumulated evidence for: {signal}. Consider previous and latest answers together.",
                "criteria": list(_LEVELS),
            }
            for index, signal in enumerate(bounded_signals)
        }
        questions["disposition"] = {
            "type": "choice",
            "instructions": "How does the latest answer respond to the current interview question?",
            "criteria": _DISPOSITIONS,
        }
        questions["no_more"] = {
            "type": "noul",
            "instructions": "Does the candidate explicitly say there is nothing more to add to this question?",
        }
        payload = {
            "model": self.client.model,
            "state": {
                "question": question[:800],
                "signals": bounded_signals,
                "evidence": {key: value for key, value in evidence.items() if key in bounded_signals},
                "previous_answers": context[-4:],
                "latest_answer": answer[:2000],
            },
            "questions": questions,
        }
        started = time.perf_counter()
        try:
            body = self.client._post(payload)
            answers = body["answers"]
            if not isinstance(answers, dict):
                return TurnJudgment()
            disposition = answers["disposition"]
            no_more = answers["no_more"]
            if (not isinstance(disposition, dict) or not isinstance(no_more, dict) or
                    disposition.get("type") != "choice" or
                    disposition.get("choice") not in _DISPOSITIONS or
                    self._probability(disposition.get("confidence")) is None or
                    no_more.get("type") != "noul" or
                    self._probability(no_more.get("noul")) is None):
                return TurnJudgment()
            scores = {}
            for index, signal in enumerate(bounded_signals):
                score_answer = answers[f"signal_{index}"]
                if not isinstance(score_answer, dict):
                    return TurnJudgment()
                score = score_answer.get("score")
                confidence = self._probability(score_answer.get("confidence"))
                if (score_answer.get("type") != "score" or
                        not isinstance(score, (int, float)) or isinstance(score, bool) or
                        not math.isfinite(score) or not 0 <= score <= 3 or confidence is None):
                    return TurnJudgment()
                if confidence >= 0.6:
                    scores[signal] = float(score)
            result = TurnJudgment(
                signal_scores=scores,
                disposition=disposition["choice"] if disposition["confidence"] >= 0.6 else "uncertain",
                explicitly_no_more=no_more["noul"] >= 0.85,
                source="jev",
            )
            logger.info("Interview Jev judgment completed in %.0fms; usage=%s",
                        (time.perf_counter() - started) * 1000, body.get("usage"))
            return result
        except Exception as exc:
            logger.warning("Interview turn judgment unavailable: %s", type(exc).__name__)
            return TurnJudgment()

    @staticmethod
    def _probability(value: object) -> float | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1:
            return float(value)
        return None
