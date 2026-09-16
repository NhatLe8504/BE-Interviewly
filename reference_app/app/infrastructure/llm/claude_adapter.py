from __future__ import annotations

from typing import AsyncIterator

from ...application.evaluation.ports import RubricEvaluationData, RubricEvaluatorPort
from ...application.interview.ports import LLMInterviewerPort
from .openai_adapter import OpenAILLMAdapter


class ClaudeLLMAdapter(LLMInterviewerPort, RubricEvaluatorPort):
    def __init__(self, api_key: str = "", model: str = "claude-3-5-sonnet-20241022") -> None:
        self.api_key = api_key
        self.model = model
        self._fallback = OpenAILLMAdapter(api_key="")

    def generate_first_question(self, role: str, level: str, language: str = "vi") -> str:
        return self._fallback.generate_first_question(role, level, language)

    def generate_follow_up(
        self,
        history: list[dict[str, str]],
        last_question: str,
        last_answer: str,
        turn_number: int,
        role: str,
        level: str,
        language: str = "vi",
        is_final_turn: bool = False,
    ) -> str:
        return self._fallback.generate_follow_up(
            history, last_question, last_answer, turn_number, role, level, language, is_final_turn,
        )

    async def stream_question(self, prompt: str, system_prompt: str | None = None) -> AsyncIterator[str]:
        async for token in self._fallback.stream_question(prompt, system_prompt):
            yield token

    def evaluate(
        self,
        question: str,
        answer: str,
        role: str = "Software Engineer",
        level: str = "fresher",
        language: str = "vi",
    ) -> RubricEvaluationData:
        return self._fallback.evaluate(question, answer, role, level, language)
