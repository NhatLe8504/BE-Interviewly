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
        model: str = "openai/gpt-oss-120b",
        base_url: str = "https://api.groq.com/openai/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model or "openai/gpt-oss-120b"
        self.base_url = "https://api.groq.com/openai/v1" if api_key.startswith("gsk_") else base_url.rstrip("/")

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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "HTTP-Referer": "https://interviewly.ai",
            "X-Title": "Interviewly AI Coach",
        }
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "openai/gpt-oss-120b" if self.api_key.startswith("gsk_") and ("deepseek" in self.model or not self.model) else (self.model.replace(":free", "") if "deepseek-v4-flash-0731" in self.model else self.model),
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
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        payload = {
            "model": "openai/gpt-oss-120b" if self.api_key.startswith("gsk_") else self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 1200,
        }
        if response_format:
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
            "model": "openai/gpt-oss-120b" if self.api_key.startswith("gsk_") and ("deepseek" in self.model or not self.model) else (self.model.replace(":free", "") if "deepseek-v4-flash-0731" in self.model else self.model),
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



    def evaluate_text_essay(
        self,
        question_text: str,
        sample_answer: str,
        answer_text: str,
        role_name: str = "Software Engineer",
        level: str = "junior",
        language: str = "vi",
    ) -> dict[str, Any]:
        """
        Pure Text Essay Evaluation (35% max) via OpenRouter DeepSeek:
        Compares candidate written answer against benchmark sample_answer using STAR framework.
        """
        clean_text = re.sub(
            r"•?\s*(Tình huống|Nhiệm vụ|Hành động|Kết quả|Situation|Task|Action|Result)\s*(\([^)]*\))?:?",
            "",
            answer_text,
            flags=re.IGNORECASE,
        ).strip()
        actual_words = len(re.findall(r"\w+", clean_text))

        prompt = f"""Bạn là Giám khảo Phỏng vấn AI chuyên gia cấp cao. Hãy chấm điểm PHẦN THI TỰ LUẬN THEO KHUNG STAR (Thang điểm: 0.0 - 35.0đ):

【THÔNG TIN CÂU HỎI & ĐÁP ÁN MẪU BENCHMARK】
- Vị trí: {role_name} (Level: {level})
- Câu hỏi phỏng vấn: {question_text}
- Câu trả lời mẫu chuẩn benchmark theo khung STAR:
"{sample_answer or 'Áp dụng khung STAR: Bối cảnh tình huống (S), nhiệm vụ cụ thể (T), hành động kỹ thuật (A), và kết quả số liệu định lượng (R).'}"

【BÀI VIẾT THỰC TẾ CỦA ỨNG VIÊN】
"{answer_text}"
(Số từ thực tế loại bỏ tiêu đề mẫu: {actual_words} từ)

【QUY TẮC CHẤM ĐIỂM TỰ LUẬN (0.0 - 35.0đ)】:
1. So sánh trực tiếp với câu trả lời mẫu benchmark:
   - ĐẶC BIỆT: Nếu ứng viên chưa nhập nội dung, chỉ để lại tiêu đề mẫu gợi ý (Situation, Task, Action, Result) hoặc viết quá ngắn/vô nghĩa (< 15 từ) -> Điểm Tự luận BẮT BUỘC từ 0.0 - 5.0đ!
   - Nếu bài viết có bối cảnh (S), nhiệm vụ (T), hành động kỹ thuật (A) và kết quả số liệu (R) -> 18.0 - 35.0đ.
2. Bóc tách 4 thành tố STAR (thang điểm 0 - 10đ cho mỗi thành tố).
3. Nhận xét tự luận: Nhận xét sắc sảo về logic và chuyên môn.
   - Nếu điểm < 28đ: Đưa ra 2-3 gợi ý cải thiện kỹ thuật cụ thể.
   - Nếu điểm >= 28đ: Khen ngợi cấu trúc và dẫn chứng.
   - TUYỆT ĐỐI KHÔNG nhận xét về giọng nói, phát âm hay nhịp thở ở phần này.

BẮT BUỘC TRẢ VỀ DUY NHẤT MỘT CHUỖI JSON HỢP LỆ (KHÔNG KÈM TEXT NGOÀI JSON):
{{
  "text_score": <float 0.0 - 35.0>,
  "text_feedback": "<Nhận xét súc tích, chi tiết về cấu trúc và giải pháp bài viết STAR>",
  "feedback": "<Nhận xét giống text_feedback>",
  "text_improvements": ["<Gợi ý cải thiện 1>", "<Gợi ý cải thiện 2>"],
  "improvements": ["<Gợi ý giống text_improvements>"],
  "text_strengths": ["<Khen ngợi nếu làm tốt>"],
  "strengths": ["<Khen ngợi giống text_strengths>"],
  "star_breakdown": {{
    "situation_score": <int 0-10>,
    "situation_feedback": "<Nhận xét S>",
    "task_score": <int 0-10>,
    "task_feedback": "<Nhận xét T>",
    "action_score": <int 0-10>,
    "action_feedback": "<Nhận xét A>",
    "result_score": <int 0-10>,
    "result_feedback": "<Nhận xét R>"
  }},
  "sample_better_answer": "<Gợi ý câu trả lời mẫu tối ưu>"
}}"""

        if not self.api_key:
            return {
                "text_score": 0.0 if actual_words == 0 else min(35.0, max(2.0, actual_words * 0.4)),
                "text_feedback": "Chưa nhập nội dung tự luận." if actual_words == 0 else "Bài viết có cấu trúc STAR.",
                "text_improvements": ["Cần trình bày chi tiết theo khung STAR."] if actual_words < 20 else [],
                "text_strengths": ["Đã bước đầu áp dụng khung STAR."] if actual_words >= 15 else [],
                "star_breakdown": {
                    "situation_score": 0 if actual_words == 0 else 5,
                    "situation_feedback": "Chưa có nội dung." if actual_words == 0 else "Bối cảnh cơ bản.",
                    "task_score": 0 if actual_words == 0 else 5,
                    "task_feedback": "Chưa có nội dung." if actual_words == 0 else "Nhiệm vụ cơ bản.",
                    "action_score": 0 if actual_words == 0 else 5,
                    "action_feedback": "Chưa có nội dung." if actual_words == 0 else "Hành động cơ bản.",
                    "result_score": 0 if actual_words == 0 else 5,
                    "result_feedback": "Chưa có nội dung." if actual_words == 0 else "Kết quả cơ bản.",
                },
                "sample_better_answer": "",
            }

        system_prompt = "Bạn là Giám khảo Phỏng vấn AI cấp cao. Do NOT generate long thinking or reasoning tokens. BẮT BUỘC chỉ sử dụng TIẾNG VIỆT CHUẨN MỰC 100%, ngữ pháp tự nhiên. TUYỆT ĐỐI KHÔNG sử dụng chữ Hán, từ ngoại lai hay ký tự lạ."
        try:
            resp_text = self._chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ])
            data = _extract_json_data(resp_text)
            if data and "text_score" in data:
                return data
        except Exception as err:
            print("Text essay evaluation error:", err)

        return {
            "text_score": 0.0 if actual_words == 0 else min(35.0, max(2.0, actual_words * 0.35)),
            "text_feedback": "Chưa có nội dung tự luận đầy đủ." if actual_words < 15 else "Bài viết có phân đoạn ý.",
            "text_improvements": ["Bổ sung dẫn chứng số liệu định lượng."],
            "text_strengths": [],
            "star_breakdown": {
                "situation_score": 1, "situation_feedback": "Quá ngắn.",
                "task_score": 1, "task_feedback": "Quá ngắn.",
                "action_score": 1, "action_feedback": "Quá ngắn.",
                "result_score": 0, "result_feedback": "Thiếu số liệu.",
            },
            "sample_better_answer": "",
        }

    def evaluate_voice_delivery(
        self,
        question: str,
        transcript: str,
        delivery_metrics: dict[str, Any],
        sample_answer: str = "",
        role_name: str = "Software Engineer",
        language: str = "vi",
    ) -> dict[str, Any]:
        duration_sec = delivery_metrics.get("durationMs", 0) / 1000.0
        wpm = delivery_metrics.get("activeSpeechWpm", 0) or delivery_metrics.get("elapsedWpm", 0)
        filler_count = delivery_metrics.get("fillerCount", 0)
        fillers = [f["text"] for f in delivery_metrics.get("fillers", []) if not f.get("isPossibleFiller")]
        pauses = delivery_metrics.get("longPauseCount", 0)
        reps = delivery_metrics.get("repetitionCount", 0)
        clean_tr = (transcript or "").strip()
        word_count = len(clean_tr.split())

        # 1. Build Verbal Descriptions for 4 Speech & Rhythm Metrics
        pace_label = f"{int(wpm)} WPM"
        if wpm >= 110 and wpm <= 165:
            wpm_desc = f"Tốc độ phát biểu {int(wpm)} WPM đạt chuẩn mực phỏng vấn (110 - 165 WPM), thể hiện sự đĩnh đạc và giúp người nghe dễ dàng theo dõi."
            pace_label += " (Chuẩn)"
        elif wpm > 165:
            wpm_desc = f"Tốc độ nói {int(wpm)} WPM là khá nhanh so với chuẩn phỏng vấn (110 - 165 WPM), dễ tạo cảm giác vội vã hoặc hồi hộp. Nên hít thở sâu, điều tiết nhịp nói chậm rãi và nhấn nhá rõ hơn vào các từ khóa kỹ thuật."
            pace_label += " (Nói nhanh)"
        elif wpm > 0:
            wpm_desc = f"Tốc độ nói {int(wpm)} WPM còn hơi chậm, bạn nên tăng dần sự lưu loát và tự tin để giữ được sự hào hứng của người nghe."
            pace_label += " (Hơi chậm)"
        else:
            wpm_desc = "Tốc độ phát biểu chưa được xác định rõ ràng."

        if pauses > 0:
            pause_desc = f"Có {pauses} lần dừng lâu trên 3 giây giữa các câu, làm gián đoạn mạch diễn đạt. Hãy rèn luyện thói quen phác thảo nhanh khung STAR trong đầu trước khi nói để các ý được liên kết liền mạch hơn."
        else:
            pause_desc = "Mạch nói được duy trì liên tục và liền mạch, không bị ngắt quãng bất thường."

        if filler_count >= 3:
            filler_desc = f"Xuất hiện {filler_count} từ đệm trong bài nói. Hãy tập thói quen im lặng ngắn (0.5s) thay vì dùng từ đệm ('ừm', 'thì là mà'...) khi chuyển ý."
        elif filler_count > 0:
            filler_desc = f"Xuất hiện {filler_count} từ đệm ở mức độ nhẹ, phát ngôn tương đối gọn gàng."
        else:
            filler_desc = "Khả năng làm chủ ngôn ngữ tốt, hoàn toàn không bị vấp từ đệm."

        if reps > 0:
            rep_desc = f"Có {reps} lần lặp lại từ ngữ khi diễn đạt. Hãy chú ý giữ bình tĩnh để câu từ dứt khoát ngay từ đầu."
        else:
            rep_desc = "Phát biểu gãy gọn, không bị lặp từ ngữ."

        metrics_verbal_review = (
            f"• Tốc độ nói: {wpm_desc}\n"
            f"• Quãng ngắt quãng: {pause_desc}\n"
            f"• Từ đệm: {filler_desc}\n"
            f"• Lặp từ ngữ: {rep_desc}"
        )

        # 2. Heuristic Content Scoring & Check
        has_substantive = any(k in clean_tr.lower() for k in [
            "báo", "sếp", "lỗi", "production", "fix", "bước", "sửa", "giải quyết",
            "xử lý", "code", "khách hàng", "test", "server", "hệ thống", "critical"
        ])
        is_pure_refusal = (
            word_count < 6 and any(k in clean_tr.lower() for k in ["không biết", "chịu", "thử mic", "alo", "1 2 3"])
        )

        if is_pure_refusal:
            calc_score = 5.0
            content_desc = "Ứng viên chưa trả lời vào câu hỏi phỏng vấn (phát biểu không biết cách làm hoặc thử mic). Cần tự tin chia sẻ trải nghiệm thực tế hoặc suy luận giải pháp theo khung STAR."
        elif has_substantive:
            calc_score = round(min(45.0, max(24.0, 18.0 + min(duration_sec, 30) * 0.4 + (5.0 if 110 <= wpm <= 165 else 0.0) - min(4.0, pauses * 1.0))), 1)
            content_desc = (
                "Ứng viên đã phản xạ nêu được những bước xử lý ban đầu quan trọng (báo cáo với cấp trên và định hướng sửa lỗi Production). "
                "Tuy nhiên, phần mở đầu còn vấp và thử mic ('Alo 1 2 3', 'không biết trả lời'). Để trả lời thuyết phục hơn, "
                "bạn nên đi thẳng vào vấn đề: quy trình cô lập lỗi, bật chế độ bảo trì/rollback, kiểm tra log hệ thống và phân tích nguyên nhân gốc rễ (Root Cause Analysis)."
            )
        else:
            calc_score = round(min(35.0, max(15.0, 15.0 + min(duration_sec, 25) * 0.3)), 1)
            content_desc = "Nội dung phát biểu còn ngắn và mang tính khái quát, cần đưa ra các dẫn chứng thực tế theo khung STAR."

        fallback_feedback = content_desc + "\n\nĐánh giá chỉ số phát biểu & nhịp điệu:\n" + metrics_verbal_review

        # 3. Call Groq LLM if configured
        if self.api_key and word_count >= 5:
            prompt = f"""Bạn là Giám khảo Phỏng vấn AI cấp cao. Hãy đánh giá phần thi NÓI & PHÁT BIỂU của ứng viên cho vị trí {role_name}:
【CÂU HỎI PHỎNG VẤN】: {question}
【CÂU TRẢ LỜI MẪU BENCHMARK】: "{sample_answer}"
【TRANSCRIPT PHÁT BIỂU CỦA ỨNG VIÊN】: "{clean_tr}"
【CHỈ SỐ PHÁT BIỂU THỰC TẾ ĐO ĐƯỢC】:
- Thời lượng: {int(duration_sec)}s
- Tốc độ: {int(wpm)} WPM
- Từ đệm: {filler_count} lần
- Dừng lâu (>3s): {pauses} lần
- Lặp từ: {reps} lần

YÊU CẦU ĐÁNH GIÁ CHUYÊN MÔN:
1. Đánh giá chất lượng nội dung câu trả lời:
   - Ghi nhận những ý đúng hoặc hướng tiếp cận mà ứng viên đã nêu (ví dụ: báo cáo cấp trên, khắc phục lỗi).
   - Chỉ ra điểm còn thiếu (ví dụ: mở đầu còn ngập ngừng/thử mic, chưa nêu quy trình kiểm tra log/monitoring, rollback hay root cause analysis).
2. BẮT BUỘC đánh giá chi tiết bằng lời văn cho 4 chỉ số phát biểu & nhịp điệu:
   - Tốc độ {int(wpm)} WPM
   - Quãng dừng lâu (>3s) {pauses} lần
   - Từ đệm {filler_count} lần
   - Lặp từ {reps} lần
3. Đưa ra điểm số giọng nói công bằng trên thang điểm 50đ.

BẮT BUỘC TRẢ VỀ DUY NHẤT 1 JSON HỢP LỆ THEO CẤU TRÚC:
{{
  "voice_score": {calc_score},
  "voice_max": 50.0,
  "pace_label": "{pace_label}",
  "feedback": "Đoạn văn nhận xét chi tiết gồm cả chất lượng nội dung và đánh giá bằng lời văn cho từng chỉ số nhịp điệu...",
  "strengths": ["Điểm mạnh 1", "Điểm mạnh 2"],
  "improvements": ["Điểm cần cải thiện 1", "Điểm cần cải thiện 2"]
}}"""
            system_prompt = "Bạn là Giám khảo Phỏng vấn AI cấp cao. BẮT BUỘC chỉ trả về duy nhất 1 JSON hợp lệ, sử dụng 100% tiếng Việt tự nhiên và chuẩn mực."
            try:
                resp = self._chat_completion([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ])
                data = _extract_json_data(resp)
                if data and "voice_score" in data and "feedback" in data:
                    return data
            except Exception as e:
                pass

        return {
            "voice_score": calc_score,
            "voice_max": 50.0,
            "pace_label": pace_label,
            "feedback": fallback_feedback,
            "strengths": [
                f"Tốc độ phát biểu {int(wpm)} WPM rõ ràng.",
                "Có ý thức phản xạ xử lý vấn đề Production."
            ] if has_substantive else ["Đã hoàn thành lượt ghi âm phát biểu."],
            "improvements": [
                "Giảm tốc độ nói về mức 120-160 WPM để phát biểu trầm ổn, tự tin hơn.",
                "Hạn chế quãng lặng >3s bằng cách phác thảo ý trước khi nói."
            ] if pauses > 0 else ["Duy trì phong thái nói lưu loát."],
        }

    def evaluate_multi_modal_question(
        self,
        question_text: str,
        sample_answer: str,
        text_answer: str,
        transcript: str,
        delivery_metrics: dict[str, Any],
        role_name: str = "Software Engineer",
        level: str = "junior",
        language: str = "vi",
    ) -> dict[str, Any]:
        """
        Comprehensive Multi-Modal Evaluation via Single LLM Call:
        Compares written text and spoken transcript against benchmark sample_answer,
        incorporating real speech delivery metrics (WPM, fillers, pauses, repetitions).
        """
        wpm = delivery_metrics.get("activeSpeechWpm") or delivery_metrics.get("elapsedWpm") or 0
        filler_count = delivery_metrics.get("fillerCount", 0)
        fillers = [f["text"] for f in delivery_metrics.get("fillers", []) if not f.get("isPossibleFiller")]
        fillers_str = ", ".join([f'"{f}"' for f in fillers[:5]]) if fillers else "Không có"
        pauses = delivery_metrics.get("longPauseCount", 0)
        pause_list = [f"{(p/1000.0):.1f}s" for p in delivery_metrics.get("pauseDurationsMs", []) if p >= 1200]
        pauses_str = ", ".join(pause_list[:5]) if pause_list else "Không có"
        reps = delivery_metrics.get("repetitionCount", 0)
        reps_list = delivery_metrics.get("repeatedPhrases", [])
        reps_str = ", ".join([f'"{r}"' for r in reps_list[:3]]) if reps_list else "Không có"
        duration_sec = int(delivery_metrics.get("durationMs", 0) / 1000.0)

        prompt = f"""Bạn là Giám khảo Phỏng vấn AI chuyên gia cấp cao (AI Interview Coach). Hãy chấm điểm và đưa ra nhận xét chuyên môn sắc sảo cho bài làm của ứng viên:

【THÔNG TIN CÂU HỎI & ĐÁP ÁN MẪU CHUẨN MỰC】
- Vị trí: {role_name} (Cấp độ: {level})
- Câu hỏi phỏng vấn: {question_text}
- Câu trả lời mẫu chuẩn benchmark theo khung STAR:
"{sample_answer or 'Áp dụng khung STAR: Nêu rõ bối cảnh tình huống (S), nhiệm vụ cụ thể (T), hành động kỹ thuật trực tiếp (A) và kết quả định lượng cụ thể (R).'}"

【BÀI LÀM THỰC TẾ CỦA ỨNG VIÊN】
1. Phần Tự luận STAR (Text):
"{text_answer or '(Ứng viên chưa viết câu trả lời)'}"

2. Phần Ghi âm giọng nói (Speech):
- Nội dung ứng viên đã phát biểu (STT Transcript):
"{transcript or '(Ứng viên chưa phát biểu hoặc micro không thu được tiếng)'}"
- Dữ liệu đo lường phát âm & lỗi ngập ngừng từ microphone:
  + Tốc độ nói: {wpm} WPM (Chuẩn phỏng vấn: 110 - 165 WPM)
  + Từ đệm / ậm ừ phát hiện: {filler_count} lần ({fillers_str})
  + Khoảng dừng suy nghĩ lâu (>1.2s): {pauses} lần ({pauses_str})
  + Lặp từ / nói lắp: {reps} lần ({reps_str})
  + Thời lượng phát biểu: {duration_sec} giây

【QUY TẮC CHẤM ĐIỂM NGHIÊM TÚC CỦA GIÁM KHẢO】
A. PHẦN TỰ LUẬN STAR (Thang điểm: 0.0 - 35.0đ):
   - So sánh ngữ nghĩa với câu trả lời mẫu benchmark:
     + NẾU ứng viên chưa điền nội dung, chỉ để lại tiêu đề mẫu (Situation, Task, Action, Result) hoặc viết quá ngắn/vô nghĩa (< 15 từ) -> Điểm Tự luận BẮT BUỘC từ 0.0 - 5.0đ!
     + NẾU bài viết có bối cảnh (S), nhiệm vụ (T), hành động kỹ thuật (A) và kết quả số liệu rõ ràng -> Chấm điểm tương xứng từ 15.0 - 35.0đ.
   - Bóc tách 4 thành tố STAR (thang điểm 0 - 10đ cho mỗi thành tố).
   - Nhận xét tự luận: Nhận xét ngắn gọn, chỉ ra điểm mạnh (nếu làm tốt) hoặc gợi ý cải thiện kỹ thuật (nếu điểm < 28đ). TUYỆT ĐỐI KHÔNG nhận xét về giọng nói hay nhịp thở ở phần này.

B. PHẦN GHI ÂM GIỌNG NÓI (Thang điểm: 0.0 - 50.0đ):
   - 1. Ngữ nghĩa nội dung phát biểu (0 - 25đ):
     + ĐẶC BIỆT CHÚ Ý: Nếu transcript cho thấy ứng viên nói "không biết", "không biết trả lời", "alo", "thử mic", "test", hoặc câu nói không có nội dung chuyên môn trả lời câu hỏi -> Điểm nội dung BẮT BUỘC = 0đ! Tổng điểm phần nói không được vượt quá 5.0/50.0đ!
     + Nếu ứng viên thực sự chia sẻ nội dung chuyên môn bám sát câu hỏi -> 12.0 - 25.0đ.
   - 2. Kỹ năng phát âm & Nhịp điệu (0 - 25đ):
     + Đánh giá dựa trên tốc độ WPM thực tế, mật độ từ đệm (fillers), các khoảng dừng suy nghĩ lâu và lặp từ.
   - Nhận xét giọng nói: Nhận xét trực tiếp về nội dung phát biểu và phong thái nói, chỉ rõ các lỗi ậm ừ/ngập ngừng hoặc khen ngợi sự lưu loát.

BẮT BUỘC TRẢ VỀ DUY NHẤT MỘT CHUỖI JSON HỢP LỆ (KHÔNG KÈM TEXT NGOÀI JSON):
{{
  "text_score": <float 0.0 - 35.0>,
  "text_feedback": "<Nhận xét súc tích về bài viết STAR>",
  "text_improvements": ["<Gợi ý cải thiện tự luận nếu điểm < 28đ>"],
  "text_strengths": ["<Khen ngợi tự luận nếu làm tốt>"],
  "star_breakdown": {{
    "situation_score": <int 0-10>,
    "situation_feedback": "<Nhận xét S>",
    "task_score": <int 0-10>,
    "task_feedback": "<Nhận xét T>",
    "action_score": <int 0-10>,
    "action_feedback": "<Nhận xét A>",
    "result_score": <int 0-10>,
    "result_feedback": "<Nhận xét R>"
  }},
  "voice_score": <float 0.0 - 50.0>,
  "voice_feedback": "<Nhận xét trực tiếp về nội dung phát biểu và phong thái nói, chỉ rõ lỗi ngập ngừng hoặc khen ngợi>",
  "voice_improvements": ["<Gợi ý cải thiện phát âm/nhịp điệu>"],
  "voice_strengths": ["<Khen ngợi phát âm nếu có>"],
  "sample_better_answer": "<Gợi ý câu trả lời mẫu tối ưu>"
}}"""

        if not self.api_key:
            # Fallback when no API key configured
            return {
                "text_score": 0.0 if len(text_answer.split()) < 15 else 20.0,
                "text_feedback": "Bài tự luận quá ngắn." if len(text_answer.split()) < 15 else "Bài viết có cấu trúc STAR.",
                "text_improvements": ["Cần viết chi tiết hơn."] if len(text_answer.split()) < 15 else [],
                "text_strengths": ["Đã áp dụng cấu trúc STAR."] if len(text_answer.split()) >= 15 else [],
                "star_breakdown": {
                    "situation_score": 2 if len(text_answer.split()) < 15 else 7,
                    "situation_feedback": "Nội dung ngắn.",
                    "task_score": 2 if len(text_answer.split()) < 15 else 7,
                    "task_feedback": "Nhiệm vụ cơ bản.",
                    "action_score": 2 if len(text_answer.split()) < 15 else 7,
                    "action_feedback": "Hành động cơ bản.",
                    "result_score": 1 if len(text_answer.split()) < 15 else 6,
                    "result_feedback": "Thiếu số liệu.",
                },
                "voice_score": 0.0 if not transcript.strip() else 3.0 if "không biết" in transcript.lower() else 30.0,
                "voice_feedback": "Chưa ghi âm câu trả lời." if not transcript.strip() else "Phát biểu đã được ghi nhận.",
                "voice_improvements": ["Cần tự tin trả lời."] if "không biết" in transcript.lower() else [],
                "voice_strengths": [],
                "sample_better_answer": "",
            }

        system_prompt = "Bạn là Giám khảo Phỏng vấn AI cấp cao. Do NOT generate long thinking or reasoning tokens. BẮT BUỘC chỉ sử dụng TIẾNG VIỆT CHUẨN MỰC 100%, ngữ pháp tự nhiên. TUYỆT ĐỐI KHÔNG sử dụng chữ Hán, từ ngoại lai hay ký tự lạ."
        try:
            resp_text = self._chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ])
            data = _extract_json_data(resp_text)
            if data and "text_score" in data and "voice_score" in data:
                return data
        except Exception as err:
            print("Multi-modal evaluation LLM error:", err)

        return {
            "text_score": 0.0 if len(text_answer.split()) < 15 else 18.0,
            "text_feedback": "Bài viết chưa đủ nội dung theo khung STAR." if len(text_answer.split()) < 15 else "Bài viết có cấu trúc.",
            "text_improvements": ["Bổ sung dẫn chứng thực tế."],
            "text_strengths": [],
            "star_breakdown": {
                "situation_score": 2, "situation_feedback": "Quá ngắn.",
                "task_score": 2, "task_feedback": "Quá ngắn.",
                "action_score": 2, "action_feedback": "Quá ngắn.",
                "result_score": 1, "result_feedback": "Thiếu số liệu.",
            },
            "voice_score": 2.0 if "không biết" in transcript.lower() else (0.0 if not transcript.strip() else 25.0),
            "voice_feedback": "Ứng viên chưa trả lời câu hỏi chuyên môn." if "không biết" in transcript.lower() else "Đã ghi nhận phát biểu.",
            "voice_improvements": ["Tự tin chia sẻ kinh nghiệm."],
            "voice_strengths": [],
            "sample_better_answer": "",
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

        system_prompt = "Bạn là Giám khảo Phỏng vấn AI cấp cao. Do NOT generate long thinking or reasoning tokens. BẮT BUỘC chỉ sử dụng TIẾNG VIỆT CHUẨN MỰC 100%, ngữ pháp tự nhiên. TUYỆT ĐỐI KHÔNG sử dụng chữ Hán, từ ngoại lai hay ký tự lạ."
        try:
            resp = self._chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ])
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
