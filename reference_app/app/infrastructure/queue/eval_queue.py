from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any


class EvaluationPullQueueManager:
    """
    Asynchronous Pull MQ Manager for Multi-Modal Question Evaluation.
    Supports Redis (LPUSH / GET) with automatic In-Memory Fallback for 0-downtime resilience.
    """
    def __init__(self, redis_client: Any = None) -> None:
        self.redis = redis_client
        self._memory_store: dict[str, dict[str, Any]] = {}
        self._memory_queue: list[dict[str, Any]] = []

    def enqueue(self, payload: dict[str, Any]) -> str:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task_data = {
            "task_id": task_id,
            "status": "queued",
            "created_at": time.time(),
            "payload": payload,
            "result": None,
        }

        # Store in Redis if available
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

        # In-Memory fallback
        self._memory_store[task_id] = task_data
        self._memory_queue.append(task_data)
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
        """
        Background Worker execution: Evaluates text via LLM and computes
        delivery voice score + STAR breakdown without blocking HTTP response.
        """
        task = self.get_task(task_id)
        if not task:
            return

        self.update_task_status(task_id, "processing")
        payload = task.get("payload", {})
        question_id = payload.get("question_id")
        text = (payload.get("text_answer") or "").strip()
        delivery = payload.get("delivery_metrics") or {}
        language = payload.get("language") or "vi"
        is_quiz_correct = payload.get("is_quiz_correct")
        quiz_score = 15.0 if is_quiz_correct is True else 0.0

        # Voice Score Calculation (50% max)
        dur_sec = float(payload.get("audio_duration_seconds") or 0.0)
        if not dur_sec and delivery.get("durationMs"):
            dur_sec = delivery["durationMs"] / 1000.0

        wpm = float(delivery.get("activeSpeechWpm") or delivery.get("elapsedWpm") or 0.0)
        fillers = int(delivery.get("fillerCount") or 0)
        reps = int(delivery.get("repetitionCount") or 0)

        voice_score = 0.0
        if dur_sec >= 5.0:
            base_voice = min(1.0, 0.65 + min(dur_sec, 60.0) / 140.0) * 50.0
            # WPM bonus/penalty
            if 110.0 <= wpm <= 165.0:
                base_voice += 2.5
            elif wpm > 185.0 or (wpm < 85.0 and wpm > 0):
                base_voice -= 3.0
            # Filler penalty (max -4đ)
            base_voice -= min(4.0, fillers * 0.8)
            # Repetition penalty (max -2đ)
            base_voice -= min(2.0, reps * 0.5)
            voice_score = round(max(15.0, min(50.0, base_voice)), 1)
        elif dur_sec > 0.0:
            voice_score = round((dur_sec / 5.0) * 15.0, 1)

        # Text STAR Score Calculation (35% max) via LLM
        words = len(text.split())
        text_score = 0.0
        if words >= 20:
            text_score = round(min(1.0, 0.5 + (words / 150.0) * 0.5) * 35.0, 1)
        elif words > 0:
            text_score = round((words / 20.0) * 12.0, 1)

        eval_data = None
        if text and container.evaluation_service and getattr(container.evaluation_service, "evaluator", None):
            try:
                # Enrich prompt with delivery cues
                enriched_text = text
                if delivery.get("transcriptAvailable") and delivery.get("fillers"):
                    filler_words = ", ".join([f["text"] for f in delivery.get("fillers", [])[:4]])
                    enriched_text += f" (Phát âm: Tốc độ {int(wpm)} WPM, chứa từ đệm: {filler_words})"

                eval_data = container.evaluation_service.evaluator.evaluate(
                    question=f"Câu hỏi #{question_id}",
                    answer=enriched_text,
                    role="Software Engineer",
                    level="junior",
                    language=language,
                )
            except Exception:
                eval_data = None

        if eval_data is not None:
            clarity = float(eval_data.clarity_score)
            structure = float(eval_data.structure_score)
            evidence = float(eval_data.evidence_score)
            llm_avg_pct = (clarity + structure + evidence) / 300.0
            if words >= 20:
                text_score = round(llm_avg_pct * 35.0, 1)

        total_score = min(100, int(round(quiz_score + text_score + voice_score)))
        passed = total_score >= 70
        star_dict = (eval_data.star_analysis if eval_data else {}) or {}

        result = {
            "score": total_score,
            "passed": passed,
            "general_feedback": (
                eval_data.feedback
                if eval_data and eval_data.feedback
                else "Bài thi hoàn thành tốt cả 3 thành phần. Cần duy trì nhịp thở và luyện nói tự tin hơn."
            ),
            "star_breakdown": {
                "situation_score": 9 if star_dict.get("situation") else 6,
                "situation_feedback": "Bối cảnh rõ ràng." if star_dict.get("situation") else "Nên nêu rõ hơn bối cảnh ban đầu.",
                "task_score": 9 if star_dict.get("task") else 7,
                "task_feedback": "Nhiệm vụ rõ ràng." if star_dict.get("task") else "Cần nêu rõ vai trò cá nhân.",
                "action_score": 9 if star_dict.get("action") else 6,
                "action_feedback": "Hành động cụ thể, logic." if star_dict.get("action") else "Nên đi sâu vào giải pháp kỹ thuật.",
                "result_score": 9 if star_dict.get("result") else 6,
                "result_feedback": "Có số liệu đo lường cụ thể." if star_dict.get("result") else "Nên bổ sung số liệu kết quả.",
            },
            "rubric_scores": [
                {
                    "criterion_id": "quiz",
                    "criterion_name": "Trắc nghiệm tình huống (15%)",
                    "score": min(10, int(round((quiz_score / 15.0) * 10))),
                    "level_label": f"{quiz_score}/15đ",
                    "feedback": "Đạt trọn vẹn điểm trắc nghiệm." if quiz_score >= 15 else "Chưa chọn phương án tối ưu.",
                },
                {
                    "criterion_id": "text",
                    "criterion_name": "Tự luận khung STAR (35%)",
                    "score": min(10, int(round((text_score / 35.0) * 10))),
                    "level_label": f"{text_score}/35đ",
                    "feedback": "Cấu trúc rõ ràng, lập luận chặt chẽ." if text_score >= 25 else "Cần viết chi tiết hơn.",
                },
                {
                    "criterion_id": "voice",
                    "criterion_name": "Nói & Phát âm thực tế (50%)",
                    "score": min(10, int(round((voice_score / 50.0) * 10))),
                    "level_label": f"{voice_score}/50đ",
                    "feedback": (
                        f"Tốc độ phát âm {int(wpm)} WPM đạt chuẩn, thời lượng tốt."
                        if voice_score >= 35
                        else "Cần luyện nói lưu loát hơn và hạn chế từ đệm."
                    ),
                },
            ],
            "strengths": [
                "Hoàn thành các nội dung đúng trọng số đa thức.",
                f"Tốc độ phát âm {int(wpm)} WPM phản ánh phong thái tự tin.",
            ],
            "improvements": [
                "Nêu rõ các số liệu đo lường kết quả theo khung STAR.",
                f"Hạn chế các từ đệm ({fillers} từ đệm được phát hiện) để phần nói thuyết phục hơn.",
            ],
            "modal_breakdown": {
                "quiz_score": quiz_score,
                "quiz_max": 15.0,
                "text_score": text_score,
                "text_max": 35.0,
                "voice_score": voice_score,
                "voice_max": 50.0,
                "total_score": float(total_score),
            },
            "delivery_metrics": delivery,
        }

        self.update_task_status(task_id, "completed", result=result)



    async def process_text_task_async(self, task_id: str, container: Any) -> None:
        """
        Background Worker for Written STAR Essay Evaluation (35% max).
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

        words = len(text.split())
        text_score = 0.0
        if words >= 20:
            text_score = round(min(1.0, 0.5 + (words / 150.0) * 0.5) * 35.0, 1)
        elif words > 0:
            text_score = round((words / 20.0) * 12.0, 1)

        eval_data = None
        evaluator = getattr(container, "evaluation_service", None) and getattr(container.evaluation_service, "evaluator", None)
        if text and evaluator:
            try:
                eval_data = evaluator.evaluate(
                    question=q_text,
                    answer=text,
                    role=role,
                    level="junior",
                    language=language,
                )
            except Exception:
                eval_data = None

        if eval_data is not None:
            clarity = float(eval_data.clarity_score)
            structure = float(eval_data.structure_score)
            evidence = float(eval_data.evidence_score)
            llm_avg = (clarity + structure + evidence) / 300.0
            if words >= 20:
                text_score = round(llm_avg * 35.0, 1)

        star_dict = (eval_data.star_analysis if eval_data else {}) or {}
        result = {
            "text_score": text_score,
            "text_max": 35.0,
            "feedback": (
                eval_data.feedback
                if eval_data and eval_data.feedback
                else "Lập luận mạch lạc, thể hiện tư duy giải quyết vấn đề tốt."
            ),
            "star_breakdown": {
                "situation_score": 9 if star_dict.get("situation") else 6,
                "situation_feedback": "Bối cảnh rõ ràng." if star_dict.get("situation") else "Nên nêu rõ hơn bối cảnh ban đầu.",
                "task_score": 9 if star_dict.get("task") else 7,
                "task_feedback": "Nhiệm vụ rõ ràng." if star_dict.get("task") else "Cần nêu rõ vai trò cá nhân.",
                "action_score": 9 if star_dict.get("action") else 6,
                "action_feedback": "Hành động cụ thể, logic." if star_dict.get("action") else "Nên đi sâu vào giải pháp kỹ thuật.",
                "result_score": 9 if star_dict.get("result") else 6,
                "result_feedback": "Có số liệu đo lường cụ thể." if star_dict.get("result") else "Nên bổ sung số liệu kết quả.",
            },
            "sample_better_answer": getattr(eval_data, "sample_better_answer", ""),
        }
        self.update_task_status(task_id, "completed", result=result)

    async def process_voice_task_async(self, task_id: str, container: Any) -> None:
        """
        Background Worker for Spoken Voice & Telemetry Evaluation (50% max).
        """
        task = self.get_task(task_id)
        if not task:
            return

        self.update_task_status(task_id, "processing")
        payload = task.get("payload", {})
        qid = payload.get("question_id")
        transcript = payload.get("transcript") or ""
        delivery = payload.get("delivery_metrics") or {}
        language = payload.get("language") or "vi"
        q_text = payload.get("question_text") or f"Câu hỏi #{qid}"

        evaluator = getattr(container, "evaluation_service", None) and getattr(container.evaluation_service, "evaluator", None)
        if evaluator and hasattr(evaluator, "evaluate_voice_delivery"):
            try:
                res = evaluator.evaluate_voice_delivery(
                    question=q_text,
                    transcript=transcript,
                    delivery_metrics=delivery,
                    language=language,
                )
                self.update_task_status(task_id, "completed", result=res)
                return
            except Exception:
                pass

        # Fallback calculation
        wpm = float(delivery.get("activeSpeechWpm") or 0.0)
        dur_sec = float(delivery.get("durationMs", 0) / 1000.0)
        fillers = int(delivery.get("fillerCount", 0))
        base_v = min(50.0, max(15.0, 35.0 + (5.0 if 110 <= wpm <= 165 else 0.0) - min(6.0, fillers * 1.0)))

        fallback_result = {
            "voice_score": round(base_v, 1),
            "voice_max": 50.0,
            "pace_label": f"{int(wpm)} WPM",
            "feedback": f"Phát biểu {int(dur_sec)}s với tốc độ {int(wpm)} WPM.",
            "strengths": [f"Tốc độ phát âm {int(wpm)} WPM tự nhiên."],
            "improvements": ["Hạn chế từ đệm khi chuyển ý."],
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
            "overall_feedback": f"Bạn đã hoàn thành tốt bài luyện tập '{title}' với điểm trung bình {avg}/100đ.",
            "strengths": ["Tư duy logic theo cấu trúc STAR.", "Hoàn thành đầy đủ các phần thi."],
            "improvements": ["Bổ sung số liệu định lượng về tác động."],
            "career_readiness_verdict": "Sẵn sàng nhận việc (Job Ready)" if avg >= 70 else "Cần rèn luyện thêm",
        }
        self.update_task_status(task_id, "completed", result=fallback)


# Singleton instance
eval_pull_queue = EvaluationPullQueueManager()
