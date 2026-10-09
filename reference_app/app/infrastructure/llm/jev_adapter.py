from __future__ import annotations

import json
import logging
from typing import Any
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


class JevSystemOneAdapter:
    """
    Adapter for TypeSafe AI - Jev System One Model.
    Provides advanced AI-driven candidate readiness analysis against Job Descriptions.
    """

    def __init__(
        self,
        api_key: str = "",
        api_url: str = "https://api.typesafe.ai/v1/systemone",
        model: str = "jev-latest",
        timeout: float = 8.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.api_url = api_url.strip()
        self.model = model.strip()
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key != "your_jev_api_key")

    def evaluate_readiness(
        self,
        job_title: str,
        job_seniority: str,
        requirements: list[dict[str, Any]],
        candidate_skills: dict[str, Any],
        cleaned_jd_text: str = "",
    ) -> dict[str, Any] | None:
        """
        Calls Jev System One to evaluate candidate readiness.
        Returns parsed dictionary or None on failure/fallback.
        """
        if not self.is_available():
            return None

        prompt = (
            f"Vị trí tuyển dụng: {job_title} (Cấp bậc: {job_seniority})\n"
            f"Yêu cầu kỹ năng chính: {json.dumps(requirements, ensure_ascii=False)}\n"
            f"Kỹ năng ứng viên đã kiểm chứng: {json.dumps(candidate_skills, ensure_ascii=False)}\n"
            f"Trích đoạn JD: {cleaned_jd_text[:600]}\n\n"
            "Hãy đánh giá độ phù hợp (0-100), nhận định verdict (ready, almost_ready, needs_practice, insufficient_data), "
            "giải thích ngắn gọn súc tích và đề xuất kỹ năng cần ôn tập. "
            "Trả về DUY NHẤT format JSON: {\"match_percent\": int, \"verdict\": str, \"explanation\": str, \"recommended_skills\": [str]}."
        )

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Bạn là Jev System One - AI chuyên gia thẩm định mức độ sẵn sàng ứng tuyển của kỹ sư phần mềm.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.api_url,
                data=req_data,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Interviewly-Jev/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    body = json.loads(resp.read().decode("utf-8"))
                    # Extract content from openai-compatible or jev-format response
                    choices = body.get("choices", [])
                    if choices:
                        raw_content = choices[0].get("message", {}).get("content", "")
                        # Parse JSON from content
                        clean_content = raw_content.strip()
                        if "```json" in clean_content:
                            clean_content = clean_content.split("```json")[1].split("```")[0].strip()
                        elif "```" in clean_content:
                            clean_content = clean_content.split("```")[1].split("```")[0].strip()
                        return json.loads(clean_content)
        except Exception as e:
            logger.warning("Jev System One evaluation call failed (fallback will be used): %s", e)

        return None
