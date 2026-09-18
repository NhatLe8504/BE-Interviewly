from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QuestionIntentContext:
    question_id: int
    intent: str
    stage_key: str
    difficulty: int = 3
    question_type: str = "technical"
    raw_question_text: str = ""
    topic_label: str = ""


class QuestionIntentComposer:
    """
    Builds situational interviewer system instructions from seed intents.
    ENFORCES STRICT RULE: AI MUST NOT repeat or read the seed question verbatim.
    The AI must formulate a natural, situational/scenario-based interview question.
    """

    @staticmethod
    def build_situational_system_prompt(
        role: str,
        level: str,
        stage_key: str,
        intent_ctx: QuestionIntentContext | None,
        language: str = "vi",
    ) -> str:
        is_vi = language == "vi"
        
        base_guardrail = (
            "QUY TẮC BẮT BUỘC: Bạn TUYỆT ĐỐI KHÔNG ĐƯỢC đọc nguyên văn câu hỏi hạt giống (seed question). "
            "Hãy chuyển hóa ý định kiểm tra (intent) thành một tình huống thực tế, cụ thể, giàu ngữ cảnh "
            "và phù hợp với kinh nghiệm ứng viên vừa chia sẻ trong cuộc trò chuyện."
            if is_vi
            else
            "STRICT GUARDRAIL: You MUST NOT read or ask the seed question verbatim. "
            "Transform the underlying intent/competency into a realistic, situation-based scenario "
            "tailored to the ongoing dialogue and the candidate's background."
        )

        if not intent_ctx:
            return base_guardrail

        target_intent = intent_ctx.intent or intent_ctx.raw_question_text or "Đánh giá năng lực chuyên môn"
        
        stage_hints = {
            "warmup": (
                "Chặng Khởi động: Hỏi tình huống nhẹ nhàng, kết hợp với bối cảnh / giới thiệu."
                if is_vi
                else "Warm-up Stage: Inquire with a light, welcoming icebreaker scenario."
            ),
            "technical": (
                "Chặng Chuyên môn: Đặt ra bài toán kỹ thuật thực tế (production issue, architecture trade-off, system failure)."
                if is_vi
                else "Technical Stage: Pose a realistic production engineering dilemma or architecture trade-off."
            ),
            "closing": (
                "Chặng Chào kết: Trao đổi về văn hóa làm việc, kỳ vọng cá nhân, định hướng dự án."
                if is_vi
                else "Closing Stage: Discuss team dynamics, expectations, and role scope."
            ),
        }

        stage_instruction = stage_hints.get(stage_key, "")

        prompt = (
            f"Vị trí: {role} ({level}). {stage_instruction}\n"
            f"Năng lực/Chủ đề cần kiểm tra (Intent): \"{target_intent}\".\n"
            f"Độ khó: {intent_ctx.difficulty}/5 • Thể loại: {intent_ctx.question_type}.\n"
            f"{base_guardrail}"
        )
        return prompt
