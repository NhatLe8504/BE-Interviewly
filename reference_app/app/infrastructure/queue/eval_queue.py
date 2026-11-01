from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from typing import Any

from ..persistence.practice_evaluation_repository import (
    PART_CONTENT,
    PART_VOICE,
    persist_llm_evaluation,
)


class EvaluationPullQueueManager:
    """
    Asynchronous Pull MQ Manager for Multi-Modal Question Evaluation.
    Guarantees strict separation between Written STAR Essay (35%) and Voice Delivery (50%).
    """
    def __init__(self, redis_client: Any = None) -> None:
        self.redis = redis_client
        self._memory_store: dict[str, dict[str, Any]] = {}

    def enqueue(self, payload: dict[str, Any]) -> str:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task_data = {
            "task_id": task_id,
            "status": "queued",
            "created_at": time.time(),
            "payload": payload,
            "result": None,
        }

        if self.redis is not None:
            try:
                self.redis.setex(
                    f"interviewly:task:{task_id}",
                    86400,
                    json.dumps(task_data, ensure_ascii=False),
                )
                self.redis.lpush("interviewly:eval_queue", json.dumps(task_data, ensure_ascii=False))
                return task_id
            except Exception:
                pass

        self._memory_store[task_id] = task_data
        return task_id

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        if self.redis is not None:
            try:
                raw = self.redis.get(f"interviewly:task:{task_id}")
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        return self._memory_store.get(task_id)

    def update_task_status(
        self,
        task_id: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        task = self.get_task(task_id)
        if not task:
            task = {
                "task_id": task_id,
                "created_at": time.time(),
                "payload": {},
            }
        task["status"] = status
        task["updated_at"] = time.time()
        if result is not None:
            task["result"] = result
        if error is not None:
            task["error"] = error

        if self.redis is not None:
            try:
                self.redis.setex(
                    f"interviewly:task:{task_id}",
                    86400,
                    json.dumps(task, ensure_ascii=False),
                )
            except Exception:
                pass
        self._memory_store[task_id] = task


    async def process_task_async(self, task_id: str, container: Any) -> None:
        """Keep the legacy combined endpoint aligned with the separate evaluation workers."""
        task = self.get_task(task_id)
        if not task:
            return
        payload = task.get("payload", {})
        self.update_task_status(task_id, "processing")
        text_task_id = self.enqueue({
            **payload,
            "answer_text": payload.get("text_answer") or "",
        })
        voice_task_id = self.enqueue(payload)
        await asyncio.gather(
            self.process_text_task_async(text_task_id, container),
            self.process_voice_task_async(voice_task_id, container),
        )
        text_result = (self.get_task(text_task_id) or {}).get("result") or {}
        voice_result = (self.get_task(voice_task_id) or {}).get("result") or {}
        quiz_score = 15.0 if payload.get("is_quiz_correct") is True else 0.0
        text_score = max(0.0, min(35.0, float(text_result.get("text_score") or 0)))
        voice_score = max(0.0, min(50.0, float(voice_result.get("voice_score") or 0)))
        total_score = min(100, round(quiz_score + text_score + voice_score))
        result = {
            **text_result,
            **voice_result,
            "score": total_score,
            "passed": total_score >= 70,
            "score_provisional": bool(voice_result.get("score_provisional")),
            "answer_framework": text_result.get("answer_framework", "generic"),
            "star_breakdown": text_result.get("star_breakdown"),
            "text_score": text_score,
            "voice_score": voice_score,
            "modal_breakdown": {
                "quiz_score": quiz_score, "quiz_max": 15.0,
                "text_score": text_score, "text_max": 35.0,
                "voice_score": voice_score, "voice_max": 50.0,
                "total_score": total_score,
            },
            "evaluation_ids": [evaluation_id for evaluation_id in (
                text_result.get("evaluation_id"), voice_result.get("evaluation_id")
            ) if evaluation_id is not None],
        }
        self.update_task_status(task_id, "completed", result=result)

    async def process_text_task_async(self, task_id: str, container: Any) -> None:
        """
        Background Worker for Written STAR Essay Evaluation (35% max).
        Evaluates purely the written text: logic, structure, depth, and evidence.
        NO voice or breathing metrics are included here.
        """
        task = self.get_task(task_id)
        if not task:
            return

        self.update_task_status(task_id, "processing")
        payload = task.get("payload", {})
        qid = payload.get("question_id")
        text = (payload.get("answer_text") or "").strip()
        q_text = payload.get("question_text") or f"Câu hỏi #{qid}"
        role = payload.get("role_name") or "Software Engineer"
        language = payload.get("language") or "vi"
        from ...domain.answer_framework import answer_framework

        framework = answer_framework(payload.get("question_type"))
        if framework != "star":
            evaluator = getattr(getattr(container, "evaluation_service", None), "evaluator", None)
            if not evaluator or not hasattr(evaluator, "evaluate_text_essay"):
                self.update_task_status(task_id, "completed", result={"text_score": 0.0, "text_max": 35.0, "star_breakdown": None, "answer_framework": framework, "feedback": "Chưa thể đánh giá nội dung; vui lòng thử lại sau."})
                return
            try:
                result = evaluator.evaluate_text_essay(
                    question_text=q_text,
                    sample_answer=payload.get("sample_answer") or "",
                    answer_text=text,
                    role_name=role,
                    language=language,
                    question_type=payload.get("question_type"),
                )
            except Exception:
                result = {"text_score": 0.0, "text_feedback": "Chưa thể đánh giá nội dung; vui lòng thử lại sau."}
            evaluation_id = None
            if result.get("text_score", 0) > 0:
                evaluation_id = persist_llm_evaluation(
                    container, user_id=payload.get("user_id"), question_id=qid,
                    part=PART_CONTENT, part_score=float(result["text_score"]),
                    part_max=35.0, answer_text=text,
                )
            self.update_task_status(task_id, "completed", result={**result, "text_max": 35.0,
                "star_breakdown": None, "answer_framework": framework,
                "feedback": result.get("text_feedback", ""), "evaluation_id": evaluation_id})
            return

        # Clean prompt template headers to get actual candidate words
        clean_text = re.sub(
            r"•?\s*(Tình huống|Nhiệm vụ|Hành động|Kết quả|Situation|Task|Action|Result)\s*(\([^)]*\))?:?",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        actual_words = len(clean_text.split())

        # Case 1: Candidate wrote NO actual content (0 words)
        if actual_words == 0:
            result = {
                "text_score": 0.0,
                "text_max": 35.0,
                "feedback": "Bạn chưa nhập nội dung câu trả lời cho phần tự luận (chỉ có các tiêu đề gợi ý mẫu). Hãy diễn giải chi tiết tình huống thực tế của bạn theo khung STAR để được chấm điểm.",
                "star_breakdown": {
                    "situation_score": 0,
                    "situation_feedback": "Chưa có nội dung tình huống.",
                    "task_score": 0,
                    "task_feedback": "Chưa có nội dung nhiệm vụ.",
                    "action_score": 0,
                    "action_feedback": "Chưa có nội dung hành động cụ thể.",
                    "result_score": 0,
                    "result_feedback": "Chưa có số liệu kết quả đo lường.",
                },
                "strengths": [],
                "improvements": ["Hãy trình bày cụ thể bối cảnh, nhiệm vụ, giải pháp và kết quả dự án thực tế theo khung STAR."],
                "sample_better_answer": "",
            }
            self.update_task_status(task_id, "completed", result=result)
            return

        # Case 2: Candidate wrote very few words (< 15 words)
        if actual_words < 15:
            text_pct = min(0.25, actual_words / 60.0)
            text_score = round(text_pct * 35.0, 1)
            result = {
                "text_score": text_score,
                "text_max": 35.0,
                "feedback": f"Câu trả lời tự luận quá ngắn ({actual_words} từ thực tế), chưa đủ thông tin để AI đánh giá chiều sâu năng lực theo khung STAR. Hãy trình bày chi tiết từ 100 - 300 từ.",
                "star_breakdown": {
                    "situation_score": 2,
                    "situation_feedback": "Bối cảnh quá sơ sài.",
                    "task_score": 2,
                    "task_feedback": "Cần nêu rõ vai trò và nhiệm vụ cá nhân.",
                    "action_score": 2,
                    "action_feedback": "Cần nêu các bước giải pháp kỹ thuật cụ thể.",
                    "result_score": 1,
                    "result_feedback": "Thiếu số liệu đo lường định lượng.",
                },
                "strengths": ["Đã bước đầu áp dụng khung STAR để phân đoạn ý."],
                "improvements": [
                    "Cần đi sâu vào giải pháp kỹ thuật cụ thể đã triển khai.",
                    "Bổ sung số liệu định lượng (thời gian xử lý, phần trăm cải thiện, hiệu năng) để tăng tính thuyết phục.",
                ],
                "sample_better_answer": "",
            }
            self.update_task_status(task_id, "completed", result=result)
            return

        # Case 3: Candidate wrote substantial text -> Evaluate with AI LLM
        sample_answer = payload.get("sample_answer") or ""
        eval_data = None
        evaluator = getattr(container, "evaluation_service", None) and getattr(container.evaluation_service, "evaluator", None)
        if evaluator and hasattr(evaluator, "evaluate_text_essay"):
            try:
                res = evaluator.evaluate_text_essay(
                    question_text=q_text,
                    sample_answer=sample_answer,
                    answer_text=text,
                    role_name=role,
                    level="junior",
                    language=language,
                )
                if isinstance(res, dict):
                    evaluation_id = persist_llm_evaluation(
                        container,
                        user_id=payload.get("user_id"),
                        question_id=qid,
                        part=PART_CONTENT,
                        part_score=float(res.get("text_score") or 0.0),
                        part_max=35.0,
                        answer_text=text,
                    )
                    if evaluation_id:
                        res = {**res, "evaluation_id": evaluation_id}
                self.update_task_status(task_id, "completed", result=res)
                return
            except Exception as err:
                print("evaluate_text_essay error:", err)

        if eval_data is not None:
            clarity = float(eval_data.clarity_score)
            structure = float(eval_data.structure_score)
            evidence = float(eval_data.evidence_score)
            llm_avg = (clarity + structure + evidence) / 300.0
            text_score = round(llm_avg * 35.0, 1)
            star_dict = eval_data.star_analysis or {}
            feedback = eval_data.feedback or "Bài viết thể hiện tư duy logic tốt theo khung STAR."
        else:
            text_score = round(min(1.0, 0.45 + (actual_words / 150.0) * 0.55) * 35.0, 1)
            star_dict = {"situation": True, "task": True, "action": actual_words >= 30, "result": actual_words >= 50}
            feedback = "Bài viết có cấu trúc rõ ràng, thể hiện được các bước giải quyết vấn đề."

        improvements = []
        if text_score < 28.0:
            improvements.append("Bổ sung thêm số liệu định lượng cụ thể (% cải thiện, thời gian xử lý) để kết quả thuyết phục hơn.")
            improvements.append("Nêu rõ hơn các đánh đổi (trade-offs) và lý do lựa chọn giải pháp kỹ thuật.")

        strengths = []
        if text_score >= 20.0:
            strengths.append("Cấu trúc STAR mạch lạc, phân chia rõ ràng giữa bối cảnh và hành động.")
            strengths.append("Giải pháp thực tế, thể hiện tinh thần chủ động giải quyết vấn đề.")

        result = {
            "text_score": text_score,
            "text_max": 35.0,
            "feedback": feedback,
            "star_breakdown": {
                "situation_score": 9 if star_dict.get("situation") else 6,
                "situation_feedback": "Bối cảnh rõ ràng." if star_dict.get("situation") else "Nên nêu rõ hơn bối cảnh ban đầu.",
                "task_score": 9 if star_dict.get("task") else 7,
                "task_feedback": "Nhiệm vụ cụ thể." if star_dict.get("task") else "Cần nêu rõ vai trò cá nhân.",
                "action_score": 9 if star_dict.get("action") else 6,
                "action_feedback": "Hành động logic." if star_dict.get("action") else "Nên đi sâu vào giải pháp kỹ thuật.",
                "result_score": 9 if star_dict.get("result") else 6,
                "result_feedback": "Có số liệu đo lường cụ thể." if star_dict.get("result") else "Nên bổ sung số liệu kết quả.",
            },
            "strengths": strengths,
            "improvements": improvements,
            "sample_better_answer": getattr(eval_data, "sample_better_answer", ""),
        }
        self.update_task_status(task_id, "completed", result=result)

    async def process_voice_task_async(self, task_id: str, container: Any) -> None:
        """
        Background Worker for Spoken Voice & Telemetry Evaluation (50% max).
        Evaluates purely delivery metrics: WPM, fillers, long pauses, repetitions.
        """
        task = self.get_task(task_id)
        if not task:
            return

        self.update_task_status(task_id, "processing")
        payload = task.get("payload", {})
        qid = payload.get("question_id")
        transcript = (payload.get("transcript") or "").strip()
        delivery = payload.get("delivery_metrics") or {}
        language = payload.get("language") or "vi"
        role = payload.get("role_name") or "Software Engineer"
        q_text = payload.get("question_text") or f"Câu hỏi #{qid}"

        duration_ms = float(delivery.get("durationMs") or 0.0)
        word_count = int(delivery.get("wordCount") or len(transcript.split()))

        # If user did not record (under 3.5s AND no words detected)
        if duration_ms < 3500.0 and (word_count == 0 and not transcript):
            empty_voice_result = {
                "voice_score": 0.0,
                "voice_max": 50.0,
                "pace_label": "Chưa ghi âm",
                "feedback": "Chưa thực hiện ghi âm câu trả lời bằng giọng nói (chiếm 50% số điểm câu hỏi). Hãy sử dụng micro để luyện tập phát biểu trực tiếp.",
                "strengths": [],
                "improvements": ["Hãy bấm micro và phát biểu trực tiếp ít nhất 15-30 giây để đạt điểm thành phần phát âm."],
            }
            self.update_task_status(task_id, "completed", result=empty_voice_result)
            return

        # If audio was recorded for >=3.5s but transcript was sparse or unclear
        if not transcript:
            dur_sec = max(1.0, duration_ms / 1000.0)
            wpm = float(delivery.get("activeSpeechWpm") or 0.0)
            base_score = 0.0
            sparse_voice_result = {
                "voice_score": base_score,
                "voice_max": 50.0,
                "pace_label": f"{int(wpm)} WPM",
                "feedback": f"Thời lượng ghi âm {int(dur_sec)}s nhưng hệ thống không thu nhận được câu từ có nghĩa rõ ràng. Hãy kiểm tra microphone và phát biểu to, rõ chữ để AI đánh giá nội dung chuyên môn.",
                "strengths": [],
                "improvements": ["Phát biểu to, rõ ràng và tập trung trả lời đúng trọng tâm câu hỏi phỏng vấn."],
            }
            self.update_task_status(task_id, "completed", result=sparse_voice_result)
            return

        sample_answer = payload.get("sample_answer") or ""
        evaluator = getattr(container, "evaluation_service", None) and getattr(container.evaluation_service, "evaluator", None)
        if evaluator and hasattr(evaluator, "evaluate_voice_delivery"):
            try:
                res = evaluator.evaluate_voice_delivery(
                    question=q_text,
                    transcript=transcript,
                    delivery_metrics=delivery,
                    sample_answer=sample_answer,
                    role_name=role,
                    language=language,
                    question_type=payload.get("question_type"),
                )
                if isinstance(res, dict):
                    res = {**res, "score_provisional": True}
                self.update_task_status(task_id, "completed", result=res)
                return
            except Exception as err:
                print("evaluate_voice_delivery error:", err)

        fallback_result = {
            "voice_score": 0.0,
            "voice_max": 50.0,
            "score_provisional": True,
            "feedback": "Chưa thể đánh giá giọng nói; vui lòng thử lại sau.",
            "strengths": [],
            "improvements": [],
        }
        self.update_task_status(task_id, "completed", result=fallback_result)

    async def process_synthesis_task_async(self, task_id: str, container: Any) -> None:
        """
        Background Worker for Final Overall Examination Synthesis.
        """
        task = self.get_task(task_id)
        if not task:
            return

        self.update_task_status(task_id, "processing")
        payload = task.get("payload", {})
        title = payload.get("session_title") or "Bài luyện tập phỏng vấn"
        questions = payload.get("evaluated_questions") or []
        language = payload.get("language") or "vi"

        evaluator = getattr(container, "evaluation_service", None) and getattr(container.evaluation_service, "evaluator", None)
        if evaluator and hasattr(evaluator, "synthesize_overall_performance"):
            try:
                res = evaluator.synthesize_overall_performance(
                    session_title=title,
                    evaluated_questions=questions,
                    language=language,
                )
                self.update_task_status(task_id, "completed", result=res)
                return
            except Exception:
                pass

        scores = [float(q.get("total_score") or q.get("score") or 0.0) for q in questions]
        avg = round(sum(scores) / len(scores), 1) if scores else 0.0
        fallback = {
            "session_title": title,
            "average_score": avg,
            "overall_feedback": f"Điểm luyện tập trung bình: {avg}/100. Chưa có tổng hợp nhận xét chuyên môn từ AI.",
            "strengths": [],
            "improvements": [],
            "career_readiness_verdict": "Sẵn sàng nhận việc (Job Ready)" if avg >= 70 else "Cần rèn luyện thêm",
        }
        self.update_task_status(task_id, "completed", result=fallback)


# Singleton instance
eval_pull_queue = EvaluationPullQueueManager()
