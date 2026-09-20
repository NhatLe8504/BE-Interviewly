from __future__ import annotations

import asyncio
import json
import re
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



def _extract_json_data(text: str) -> dict:
    if not text:
        return {}
    clean = text.strip()
    try:
        return json.loads(clean)
    except Exception:
        pass
    m = re.search(r"`(?:json)?\s*(\{.*?\})\s*`", clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"(\{.*\})", clean, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    return {}
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
            "HTTP-Referer": "https://interviewly.ai",
            "X-Title": "Interviewly AI Coach",
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
            "HTTP-Referer": "https://interviewly.ai",
            "X-Title": "Interviewly AI Coach",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.7,
        }
        if response_format and "openrouter.ai" not in self.base_url:
            payload["response_format"] = response_format

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            if resp.status_code == 400 and "response_format" in payload:
                del payload["response_format"]
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


    def evaluate_voice_delivery(
        self,
        question: str,
        transcript: str,
        delivery_metrics: dict[str, Any],
        language: str = "vi",
    ) -> dict[str, Any]:
        duration_sec = delivery_metrics.get("durationMs", 0) / 1000.0
        wpm = delivery_metrics.get("activeSpeechWpm", 0)
        filler_count = delivery_metrics.get("fillerCount", 0)
        fillers = [f["text"] for f in delivery_metrics.get("fillers", []) if not f.get("isPossibleFiller")]
        pauses = delivery_metrics.get("longPauseCount", 0)
        reps = delivery_metrics.get("repetitionCount", 0)
        clean_tr = (transcript or "").strip().lower()
        word_count = len(clean_tr.split())

        # Check for non-answers (candidate states they don't know, tests mic, or gives trivial text)
        is_non_answer = bool(
            re.search(r"\b(không biết|chưa biết|không hiểu|chịu|chịu thôi|không có kinh nghiệm|alo|thử mic|test|1 2 3|i don't know|no idea)\b", clean_tr)
            or word_count < 6
        )

        if is_non_answer:
            return {
                "voice_score": round(min(5.0, max(1.0, word_count * 0.4)), 1),
                "voice_max": 50.0,
                "pace_label": f"{int(wpm)} WPM",
                "feedback": "Ứng viên chưa trả lời vào trọng tâm câu hỏi (phát biểu không biết cách trả lời hoặc thử mic). Cần tự tin chia sẻ trải nghiệm thực tế hoặc suy luận giải pháp.",
                "strengths": [],
                "improvements": ["Hãy chủ động đưa ra hướng tiếp cận hoặc suy luận kỹ thuật cho câu hỏi thay vì từ chối trả lời."],
            }

        # Quantitative Delivery Score (max 25 points)
        delivery_points = 12.0
        if 110 <= wpm <= 165:
            delivery_points += 8.0
        elif 85 <= wpm < 110:
            delivery_points += 5.0
        elif wpm > 165:
            delivery_points += 3.0

        if pauses <= 1:
            delivery_points += 3.0
        elif pauses > 3:
            delivery_points -= 2.0

        if filler_count <= 2:
            delivery_points += 2.0
        elif filler_count > 4:
            delivery_points -= min(4.0, filler_count * 0.8)

        # Baseline Content Score (max 25 points)
        content_points = min(25.0, 10.0 + (word_count / 80.0) * 15.0)
        calc_score = round(max(5.0, min(50.0, delivery_points + content_points)), 1)

        if not self.api_key:
            return {
                "voice_score": calc_score,
                "voice_max": 50.0,
                "pace_label": f"{int(wpm)} WPM (" + ("Chuẩn" if 110 <= wpm <= 165 else ("Nói nhanh" if wpm > 165 else "Cần lưu loát hơn")) + ")",
                "feedback": f"Phát biểu {int(duration_sec)}s với tốc độ {int(wpm)} WPM. Phát hiện {filler_count} từ đệm.",
                "strengths": [f"Tốc độ phát âm {int(wpm)} WPM tự nhiên."],
                "improvements": ["Nên hạn chế các từ đệm khi chuyển ý."] if filler_count > 2 else ["Duy trì phong thái đĩnh đạc."],
            }

        prompt = f"""Bạn là giám khảo phỏng vấn chuyên gia. Đánh giá phần thi NÓI & PHÁT ÂM của ứng viên (Thang điểm 50đ):
Câu hỏi: {question}
Nội dung ứng viên đã phát biểu (STT Transcript): "{transcript}"
Chỉ số phát âm: Tốc độ={wpm} WPM, Số từ đệm={filler_count} (Từ đệm: {', '.join(fillers[:4]) if fillers else 'Không có'}), Dừng lâu={pauses}, Lặp từ={reps}.

TIÊU CHÍ CHẤM ĐIỂM (50đ):
1. Nội dung câu trả lời (0 - 25đ):
   - ĐẶC BIỆT: Nếu ứng viên nói không biết, từ chối trả lời, hoặc nói lạc đề -> Điểm nội dung = 0đ! Tổng điểm không được vượt quá 5/50đ!
   - Nếu trả lời có nội dung chuyên môn thực tế -> 12 - 25đ.
2. Kỹ năng phát âm & Ngữ điệu (0 - 25đ): Tốc độ 110-165 WPM là chuẩn (10đ); ít từ đệm (10đ); ngắt quãng tự nhiên (5đ).

Trả về DUY NHẤT một JSON hợp lệ:
{{
  "voice_score": {calc_score},
  "voice_max": 50.0,
  "pace_label": "{int(wpm)} WPM",
  "feedback": "Nhận xét khách quan về nội dung phát biểu và phong thái nói...",
  "strengths": ["Điểm mạnh phát âm 1"],
  "improvements": ["Điểm cần cải thiện 1"]
}}"""

        try:
            resp = self._chat_completion([{"role": "user", "content": prompt}])
            data = _extract_json_data(resp)
            if data and "voice_score" in data:
                return data
        except Exception:
            pass

        return {
            "voice_score": calc_score,
            "voice_max": 50.0,
            "pace_label": f"{int(wpm)} WPM",
            "feedback": f"Phát biểu {int(duration_sec)}s với tốc độ {int(wpm)} WPM.",
            "strengths": [f"Tốc độ phát âm {int(wpm)} WPM tự nhiên."],
            "improvements": ["Duy trì nhịp thở và hạn chế từ đệm."],
        }

    def synthesize_overall_performance(
        self,
        session_title: str,
        evaluated_questions: list[dict[str, Any]],
        language: str = "vi",
    ) -> dict[str, Any]:
        scores = [float(q.get("total_score") or q.get("score") or 0.0) for q in evaluated_questions]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

        if not self.api_key:
            return {
                "session_title": session_title,
                "average_score": avg_score,
                "overall_feedback": f"Bạn đã hoàn thành tốt bài luyện tập '{session_title}' với điểm trung bình {avg_score}/100đ. Phong thái trả lời tự tin, nắm chắc kiến thức chuyên môn.",
                "strengths": ["Tư duy logic theo cấu trúc STAR mạch lạc.", "Hoàn thành đầy đủ các hình thức kiểm tra."],
                "improvements": ["Bổ sung thêm số liệu định lượng về tác động dự án.", "Rèn luyện phát âm lưu loát hơn."],
                "career_readiness_verdict": "Sẵn sàng phỏng vấn (Interview Ready)" if avg_score >= 70 else "Cần rèn luyện thêm",
            }

        summary_lines = []
        for idx, q in enumerate(evaluated_questions, 1):
            summary_lines.append(
                f"Câu {idx}: {q.get('question_text', '')} | Điểm: {q.get('total_score', q.get('score', 0))}/100 "
                f"(Quiz: {q.get('quiz_score', 0)}, Text: {q.get('text_score', 0)}, Voice: {q.get('voice_score', 0)})"
            )

        prompt = f"""Bạn là Huấn luyện viên Phỏng vấn AI cao cấp (Interview Coach). Hãy tổng kết bài thi phỏng vấn:
Bài thi: {session_title}
Điểm trung bình: {avg_score}/100
Chi tiết từng câu:
{chr(10).join(summary_lines)}

Trả về DUY NHẤT một JSON hợp lệ:
{{
  "session_title": "{session_title}",
  "average_score": {avg_score},
  "overall_feedback": "Nhận xét tổng thể 2-3 câu về năng lực chuyên môn, phong thái và độ sẵn sàng nhận việc...",
  "strengths": ["Điểm mạnh nổi bật 1", "Điểm mạnh nổi bật 2"],
  "improvements": ["Điểm cần rèn luyện thêm 1", "Điểm cần rèn luyện thêm 2"],
  "career_readiness_verdict": "Sẵn sàng nhận việc (Job Ready)"
}}"""

        try:
            resp = self._chat_completion([{"role": "user", "content": prompt}])
            data = _extract_json_data(resp)
            if data and "overall_feedback" in data:
                return data
        except Exception:
            pass

        return {
            "session_title": session_title,
            "average_score": avg_score,
            "overall_feedback": f"Bạn đã hoàn thành bài luyện tập '{session_title}' với điểm trung bình {avg_score}/100đ.",
            "strengths": ["Cấu trúc trả lời mạch lạc."],
            "improvements": ["Bổ sung số liệu định lượng vào kết quả."],
            "career_readiness_verdict": "Đạt chuẩn phỏng vấn" if avg_score >= 70 else "Cần rèn luyện thêm",
        }
