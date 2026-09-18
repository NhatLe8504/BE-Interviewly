from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator
import httpx

from ...application.voice.ports import LLMVoiceStreamPort
from ...application.evaluation.ports import RubricEvaluationData, RubricEvaluatorPort
from ...application.interview.ports import LLMInterviewerPort
from .prompt_templates import (
    build_follow_up_user_prompt,
    build_interviewer_system_prompt,
    build_rubric_evaluator_system_prompt,
    build_rubric_evaluator_user_prompt,
)


class OpenAILLMAdapter(LLMInterviewerPort, RubricEvaluatorPort, LLMVoiceStreamPort):
    def __init__(
        self,
        api_key: str = "",
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")

    def generate_first_question(
        self, role: str, level: str, language: str = "vi",
    ) -> str:
        if not self.api_key:
            if language == "vi":
                return f"Chào bạn, rất vui được gặp bạn trong buổi phỏng vấn vị trí {role} ({level}). Bạn có thể giới thiệu ngắn gọn về bản thân và một dự án tiêu biểu mà bạn tự hào nhất không?"
            return f"Hello, welcome to this interview for {role} ({level}). Could you briefly introduce yourself and describe a project you are most proud of?"

        system = build_interviewer_system_prompt(role=role, level=level, language=language)
        user = "Hãy đặt câu hỏi mở đầu buổi phỏng vấn cho ứng viên."
        return self._chat_completion([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])

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
        if not self.api_key:
            if is_final_turn:
                return "Cảm ơn bạn rất nhiều vì đã chia sẻ rất chi tiết. Buổi phỏng vấn đã hoàn tất, bạn có câu hỏi nào dành cho công ty chúng tôi không?"
            return f"Ở câu hỏi trước bạn có nhắc đến '{last_answer[:40]}...'. Bạn có thể giải thích sâu hơn về giải pháp kỹ thuật cụ thể và khó khăn lớn nhất bạn gặp phải khi triển khai phần này không?"

        system = build_interviewer_system_prompt(role=role, level=level, language=language)
        user = build_follow_up_user_prompt(
            history=history,
            last_question=last_question,
            last_answer=last_answer,
            turn_number=turn_number,
            is_final_turn=is_final_turn,
        )
        messages = [{"role": "system", "content": system}]
        messages.extend(history[-6:])
        messages.append({"role": "user", "content": user})
        return self._chat_completion(messages)

    async def stream_question(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if not self.api_key:
            # Emulate token streaming
            tokens = prompt.split(" ")
            for token in tokens:
                yield token + " "
                await asyncio.sleep(0.04)
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue

    def evaluate(
        self,
        question: str,
        answer: str,
        role: str = "Software Engineer",
        level: str = "fresher",
        language: str = "vi",
    ) -> RubricEvaluationData:
        if not self.api_key:
            # Fallback mock rubric calculation based on answer length and keywords
            word_count = len(answer.split())
            clarity = min(95.0, max(45.0, 50.0 + word_count * 0.4))
            structure = min(90.0, max(40.0, 45.0 + word_count * 0.35))
            evidence = min(88.0, max(35.0, 40.0 + word_count * 0.3))
            return RubricEvaluationData(
                clarity_score=round(clarity, 1),
                structure_score=round(structure, 1),
                evidence_score=round(evidence, 1),
                star_analysis={
                    "situation": True,
                    "task": True,
                    "action": word_count > 20,
                    "result": word_count > 40,
                },
                feedback="Câu trả lời phản ánh tư duy logic tốt. Nên bổ sung thêm các số liệu định lượng về kết quả để câu trả lời thuyết phục hơn.",
                sample_better_answer=f"Khi đối mặt với vấn đề trong câu hỏi '{question}', tôi đã phân tích nguyên nhân gốc rễ, áp dụng giải pháp tối ưu và cải thiện 30% hiệu năng hệ thống.",
            )

        system = build_rubric_evaluator_system_prompt(language=language)
        user = build_rubric_evaluator_user_prompt(
            question=question, answer=answer, role=role, level=level,
        )
        resp_text = self._chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
        )
        try:
            data = json.loads(resp_text)
            return RubricEvaluationData(
                clarity_score=float(data.get("clarity_score", 70.0)),
                structure_score=float(data.get("structure_score", 70.0)),
                evidence_score=float(data.get("evidence_score", 70.0)),
                star_analysis=data.get("star_analysis", {}),
                feedback=data.get("feedback", ""),
                sample_better_answer=data.get("sample_better_answer", ""),
            )
        except Exception:
            return RubricEvaluationData(
                clarity_score=75.0,
                structure_score=70.0,
                evidence_score=70.0,
                star_analysis={"situation": True, "task": True, "action": False, "result": False},
                feedback=resp_text,
                sample_better_answer="",
            )

    def _chat_completion(
        self, messages: list[dict[str, str]], response_format: dict | None = None,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
        }
        if response_format:
            payload["response_format"] = response_format

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()

    async def stream_ai_tokens(
        self, messages: list[dict[str, str]],
    ) -> AsyncIterator[str]:
        if not self.api_key:
            sample_text = (
                "Cảm ơn câu trả lời của bạn. Tôi thấy bạn có kinh nghiệm với vấn đề vừa rồi. "
                "Bạn có thể giải thích thêm về cách bạn đo lường hiệu năng thực tế không? "
                "Điều đó sẽ giúp tôi đánh giá rõ hơn năng lực của bạn."
            )
            for word in sample_text.split(" "):
                yield word + " "
                await asyncio.sleep(0.01)
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": 0.7,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk["choices"][0]["delta"].get("content", "")
                            if delta:
                                yield delta
                        except Exception:
                            continue
