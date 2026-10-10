"""Adapter gọi TypeSafe Jev System One theo đúng giao thức `systemone`.

Giao thức thật (OpenAPI: https://api.typesafe.ai/openapi.json):
- POST /v1/systemone, body {"model": str, "state": str|object|array, "questions": {name: Question}}
- Question: {"type": "score", "criteria": [...]} | {"type": "choice", "criteria": {...}} | {"type": "noul"}
- Response: {"model": str, "answers": {name: Answer}, "usage": {...}};
  Answer: {"type": "score", "score": float, "confidence": float, ...} |
  {"type": "choice", "choice": str, "confidence": float, ...} | {"type": "noul", "noul": float}

Jev không trả về văn bản tự do, nên phần diễn giải được soạn cục bộ từ dữ
liệu cấu trúc (điểm tổng, verdict, danh sách kỹ năng dưới mức yêu cầu). Adapter
chỉ được gọi khi người dùng chủ động bấm kiểm tra một job cụ thể — không có
luồng quét hàng loạt theo kiểu user x JD.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Any
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

_PLACEHOLDER_KEYS = {"your_jev_api_key", "your_jev_key", "changeme", "placeholder"}

MAX_SKILL_QUESTIONS = 6
MAX_REQUIREMENTS_IN_STATE = 12
MAX_JD_EXCERPT_CHARS = 700

# 10 mức 0..9 cho câu hỏi điểm tổng (API giới hạn tối đa 10 mức).
# match_percent = score / 9 * 100.
OVERALL_MATCH_MAX_SCORE = 9.0
OVERALL_MATCH_CRITERIA: tuple[str, ...] = (
    "0 - No verified evidence for any requirement.",
    "1 - Isolated evidence only; every must-have skill is far below the required level.",
    "2 - Sparse evidence; most must-have skills are far below the required level.",
    "3 - Around one third of must-have skills roughly at level; major must-have gaps remain.",
    "4 - Around half of must-have skills at level; several must-have skills still below the required level.",
    "5 - Most must-have skills at level; a few must-have gaps remain.",
    "6 - All must-have skills at level; nice-to-have skills partially below level.",
    "7 - All must-have skills at level with solid surplus; most nice-to-have skills covered.",
    "8 - All requirements at or above level, verified by consistent evidence.",
    "9 - Every requirement clearly exceeded with strong, consistent verified evidence.",
)

VERDICT_CHOICES: dict[str, str] = {
    "ready": "Verified skills meet the job requirements; the candidate can apply now.",
    "almost": "Small improvement needed before applying; most must-have skills are at level.",
    "not_ready": "Important must-have skills are below the required level; practice first.",
    "insufficient_data": "Too little verified evidence to judge readiness reliably.",
}

# 6 mức 0..5 cho từng kỹ năng (khớp thang level nội bộ none -> lead).
SKILL_CRITERIA: tuple[str, ...] = (
    "0 - No verified evidence for this skill.",
    "1 - Verified level is far below the required level.",
    "2 - Verified level is one level below the required level.",
    "3 - Verified level meets the required level.",
    "4 - Verified level is one level above the required level.",
    "5 - Verified level clearly exceeds the required level with strong evidence.",
)

_STATUS_BY_LEVEL = {0: "unknown", 1: "gap", 2: "partial", 3: "met", 4: "met", 5: "met"}


@dataclass
class JevSkillRating:
    skill_id: str
    score: float
    confidence: float
    status: str
    level_num: int


@dataclass
class JevReadinessResult:
    match_percent: int
    verdict: str
    confidence: float
    recommended_skills: list[str]
    skill_ratings: dict[str, JevSkillRating]
    explanation: str
    model: str


class JevSystemOneAdapter:
    """Client cho TypeSafe AI - Jev System One (systemone protocol)."""

    def __init__(
        self,
        api_key: str = "",
        api_url: str = "https://api.typesafe.ai/v1/systemone",
        model: str = "jev-latest",
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key.strip()
        self.api_url = api_url.strip()
        self.model = model.strip() or "jev-latest"
        self.timeout = timeout

    def is_available(self) -> bool:
        return bool(self.api_key) and self.api_key not in _PLACEHOLDER_KEYS and len(self.api_key) >= 12

    def evaluate_readiness(
        self,
        job_title: str,
        job_seniority: str,
        requirements: list[dict[str, Any]],
        candidate_skills: dict[str, Any],
        cleaned_jd_text: str = "",
    ) -> JevReadinessResult | None:
        """Đánh giá mức độ sẵn sàng ứng tuyển; trả None để caller fallback."""
        if not self.is_available():
            return None

        bounded = self._bounded_requirements(requirements)
        if not bounded:
            return None

        payload = {
            "model": self.model,
            "state": self._build_state(job_title, job_seniority, bounded, candidate_skills, cleaned_jd_text),
            "questions": self._build_questions(job_title, bounded),
        }

        try:
            body = self._post(payload)
        except Exception as exc:  # noqa: BLE001 - fallback được ghi log rõ
            logger.warning("Jev System One call failed; using heuristic fallback: %s", exc)
            return None

        result = self._parse_result(body, bounded, job_title)
        if result is None:
            logger.warning("Jev System One returned an unusable response; using heuristic fallback")
            return None

        usage = body.get("usage") if isinstance(body, dict) else None
        logger.info(
            "Jev System One evaluated job readiness: model=%s match=%s verdict=%s usage=%s",
            result.model,
            result.match_percent,
            result.verdict,
            usage,
        )
        return result

    # ------------------------------------------------------------------ build

    def _bounded_requirements(self, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        must: list[dict[str, Any]] = []
        nice: list[dict[str, Any]] = []
        for raw in requirements or []:
            skill_id = str(raw.get("skill_id") or "").strip()
            if not skill_id:
                continue
            item = {
                "skill_id": skill_id,
                "name": str(raw.get("name") or skill_id),
                "importance": "must" if raw.get("importance") == "must" else "nice",
                "required_level": str(raw.get("required_level") or "middle"),
            }
            (must if item["importance"] == "must" else nice).append(item)
        ordered = must[:MAX_REQUIREMENTS_IN_STATE]
        if len(ordered) < MAX_REQUIREMENTS_IN_STATE:
            ordered += nice[: MAX_REQUIREMENTS_IN_STATE - len(ordered)]
        return ordered

    def _skill_question_targets(self, bounded: list[dict[str, Any]]) -> list[dict[str, Any]]:
        must = [r for r in bounded if r["importance"] == "must"]
        nice = [r for r in bounded if r["importance"] != "must"]
        targets = must[:MAX_SKILL_QUESTIONS]
        if len(targets) < 3:
            targets += nice[: MAX_SKILL_QUESTIONS - len(targets)]
        return targets

    def _build_state(
        self,
        job_title: str,
        job_seniority: str,
        bounded: list[dict[str, Any]],
        candidate_skills: dict[str, Any],
        cleaned_jd_text: str,
    ) -> dict[str, Any]:
        verified: dict[str, dict[str, Any]] = {}
        for req in bounded:
            cand = candidate_skills.get(req["skill_id"])
            if isinstance(cand, dict):
                verified[req["skill_id"]] = {
                    "level": str(cand.get("level") or "none"),
                    "confidence": self._as_float(cand.get("confidence"), 0.0),
                    "ability_score": self._as_float(cand.get("ability_score"), 0.0),
                }
        return {
            "job_title": job_title,
            "seniority": job_seniority or "unknown",
            "requirements": [
                {
                    "skill_id": req["skill_id"],
                    "skill_name": req["name"],
                    "importance": req["importance"],
                    "required_level": req["required_level"],
                    "candidate_verified_level": verified.get(req["skill_id"], {}).get("level", "none"),
                    "candidate_evidence_confidence": verified.get(req["skill_id"], {}).get("confidence", 0.0),
                }
                for req in bounded
            ],
            "verified_candidate_skills": verified,
            "jd_excerpt": (cleaned_jd_text or "")[:MAX_JD_EXCERPT_CHARS],
            "note": "candidate_verified_level comes from graded practice and interview evidence; 'none' means no verified evidence.",
        }

    def _build_questions(self, job_title: str, bounded: list[dict[str, Any]]) -> dict[str, Any]:
        questions: dict[str, Any] = {
            "overall_match": {
                "type": "score",
                "instructions": (
                    f"Rate how well the candidate's verified skills match the requirements of '{job_title}'. "
                    "Weigh must-have requirements first, then nice-to-have ones, and respect the gap between "
                    "each verified level and its required level. 'none' means the skill has no verified evidence."
                ),
                "criteria": list(OVERALL_MATCH_CRITERIA),
            },
            "verdict": {
                "type": "choice",
                "instructions": "Choose the hiring-readiness verdict that best matches the candidate's verified profile.",
                "criteria": dict(VERDICT_CHOICES),
            },
        }
        for req in self._skill_question_targets(bounded):
            questions[f"skill__{req['skill_id']}"] = {
                "type": "score",
                "instructions": (
                    f"Rate the candidate's verified proficiency in '{req['name']}' against the required level "
                    f"'{req['required_level']}' for this job. Use level 0 when there is no verified evidence."
                ),
                "criteria": list(SKILL_CRITERIA),
            }
        return questions

    # ------------------------------------------------------------------- http

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.api_url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Interviewly-Jev/2.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"Jev returned HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))

    # ------------------------------------------------------------------ parse

    def _parse_result(self, body: Any, bounded: list[dict[str, Any]], job_title: str) -> JevReadinessResult | None:
        if not isinstance(body, dict):
            return None
        answers = body.get("answers")
        if not isinstance(answers, dict):
            return None

        overall = self._read_score(answers.get("overall_match"), 0.0, OVERALL_MATCH_MAX_SCORE)
        if overall is None:
            logger.warning("Jev response has no usable 'overall_match' score answer")
            return None
        overall_score, confidence = overall
        match_percent = int(round(min(max(overall_score, 0.0), OVERALL_MATCH_MAX_SCORE) / OVERALL_MATCH_MAX_SCORE * 100))

        verdict = self._read_choice(answers.get("verdict"))
        if verdict not in VERDICT_CHOICES:
            verdict = self._verdict_from_percent(match_percent)

        name_by_id = {req["skill_id"]: req["name"] for req in bounded}
        ratings: dict[str, JevSkillRating] = {}
        ranked: list[tuple[float, int, str]] = []
        for index, req in enumerate(bounded):
            skill_id = req["skill_id"]
            parsed = self._read_score(answers.get(f"skill__{skill_id}"), 0.0, 5.0)
            if parsed is None:
                continue
            raw_score, raw_confidence = parsed
            level_num = max(0, min(5, int(round(raw_score))))
            ratings[skill_id] = JevSkillRating(
                skill_id=skill_id,
                score=raw_score,
                confidence=raw_confidence,
                status=_STATUS_BY_LEVEL[level_num],
                level_num=level_num,
            )
            if level_num < 3:
                ranked.append((raw_score, index, skill_id))

        ranked.sort(key=lambda item: (item[0], item[1]))
        recommended = [skill_id for _, _, skill_id in ranked]

        explanation = self._compose_explanation(
            job_title=job_title,
            match_percent=match_percent,
            confidence=confidence,
            verdict=verdict,
            recommended=recommended,
            name_by_id=name_by_id,
        )
        return JevReadinessResult(
            match_percent=match_percent,
            verdict=verdict,
            confidence=confidence,
            recommended_skills=recommended,
            skill_ratings=ratings,
            explanation=explanation,
            model=str(body.get("model") or self.model),
        )

    @staticmethod
    def _read_score(answer: Any, low: float, high: float) -> tuple[float, float] | None:
        if not isinstance(answer, dict) or answer.get("type") != "score":
            return None
        score = answer.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            return None
        confidence = JevSystemOneAdapter._as_float(answer.get("confidence"), 0.0)
        return (
            min(max(float(score), low), high),
            min(max(confidence, 0.0), 1.0),
        )

    @staticmethod
    def _read_choice(answer: Any) -> str | None:
        if not isinstance(answer, dict) or answer.get("type") != "choice":
            return None
        choice = answer.get("choice")
        return choice if isinstance(choice, str) else None

    @staticmethod
    def _verdict_from_percent(match_percent: int) -> str:
        if match_percent >= 75:
            return "ready"
        if match_percent >= 50:
            return "almost"
        return "not_ready"

    @staticmethod
    def _as_float(value: Any, default: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return default
        return float(value)

    @staticmethod
    def _compose_explanation(
        job_title: str,
        match_percent: int,
        confidence: float,
        verdict: str,
        recommended: list[str],
        name_by_id: dict[str, str],
    ) -> str:
        sentences = []
        if match_percent == 0 or verdict == "insufficient_data":
            sentences.append(
                f"Interviewly AI đánh giá bạn chưa có kỹ năng để ứng tuyển vị trí {job_title}."
            )
            sentences.append(
                "Hãy hoàn thành các buổi luyện tập phỏng vấn theo các kỹ năng yêu cầu bên dưới để nâng cao độ phù hợp."
            )
        elif verdict == "not_ready":
            sentences.append(
                f"Interviewly AI đánh giá bạn đạt {match_percent}% độ phù hợp với vị trí {job_title}. Bạn cần luyện tập thêm để đáp ứng các yêu cầu chính."
            )
        elif verdict == "almost":
            sentences.append(
                f"Interviewly AI đánh giá bạn đạt {match_percent}% độ phù hợp với vị trí {job_title}. Bạn gần đạt yêu cầu; nên củng cố thêm trước khi ứng tuyển."
            )
        else:
            sentences.append(
                f"Interviewly AI đánh giá bạn đạt {match_percent}% độ phù hợp với vị trí {job_title}. Bạn đã sẵn sàng ứng tuyển."
            )

        if recommended:
            names = [name_by_id.get(skill_id, skill_id) for skill_id in recommended[:5]]
            sentences.append("Ưu tiên luyện tập: " + ", ".join(names) + ".")
        return " ".join(part for part in sentences if part)
