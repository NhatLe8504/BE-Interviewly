from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from .estimator import SkillEstimateResult
from .taxonomy import get_default_taxonomy

SENIORITY_LEVEL_MAP = {
    "intern": 1,
    "fresher": 1,
    "junior": 2,
    "mid": 3,
    "middle": 3,
    "senior": 4,
    "lead": 5,
}

LEVEL_NUM_TO_NAME = {
    1: "beginner",
    2: "junior",
    3: "middle",
    4: "senior",
    5: "lead",
}

LEVEL_NAME_TO_NUM = {
    "none": 0,
    "beginner": 1,
    "junior": 2,
    "middle": 3,
    "senior": 4,
    "lead": 5,
}


@dataclass
class JobRequirementItem:
    skill_id: str
    name: str
    importance: str  # "must" | "nice"
    required_level: str  # "beginner", "junior", "middle", "senior", "lead"
    required_level_num: int
    user_level: str  # "none", "beginner", "junior", "middle", "senior", "lead"
    user_level_num: int
    status: str  # "met", "partial", "gap", "unknown"
    confidence: float
    level_assumed: bool


@dataclass
class JobReadinessAssessment:
    job_id: str
    match_percent: int
    verdict: str  # "ready", "almost", "not_ready", "insufficient_data"
    data_coverage: float  # 0.0 to 1.0
    requirements: list[JobRequirementItem]
    explanation: str
    recommended_skills: list[str]


class JobReadinessEvaluator:
    @classmethod
    def evaluate(
        cls,
        job_id: str,
        job_title: str,
        job_seniority: str,
        skills_required: list[str],
        technologies: list[str],
        cleaned_jd_text: str,
        user_skills: dict[str, SkillEstimateResult],
    ) -> JobReadinessAssessment:
        taxonomy = get_default_taxonomy()
        sen_key = (job_seniority or "unknown").strip().lower()
        level_assumed = sen_key not in SENIORITY_LEVEL_MAP
        target_level_num = SENIORITY_LEVEL_MAP.get(sen_key, 3)
        target_level_name = LEVEL_NUM_TO_NAME.get(target_level_num, "middle")

        # 1. Collect and deduplicate skill IDs
        must_skill_ids: list[str] = []
        for raw in skills_required or []:
            sid = taxonomy.normalize_skill_id(raw)
            if sid and sid not in must_skill_ids:
                must_skill_ids.append(sid)

        nice_skill_ids: list[str] = []
        for raw in technologies or []:
            sid = taxonomy.normalize_skill_id(raw)
            if sid and sid not in must_skill_ids and sid not in nice_skill_ids:
                nice_skill_ids.append(sid)

        # Also extract skills mentioned in title/JD if list is sparse
        if len(must_skill_ids) + len(nice_skill_ids) < 3 and cleaned_jd_text:
            extracted = taxonomy.extract_skills_from_text(cleaned_jd_text)
            for sk in extracted:
                if sk.id not in must_skill_ids and sk.id not in nice_skill_ids:
                    if len(must_skill_ids) < 4:
                        must_skill_ids.append(sk.id)
                    else:
                        nice_skill_ids.append(sk.id)

        # Fallback if totally empty: check title
        if not must_skill_ids and not nice_skill_ids and job_title:
            extracted = taxonomy.extract_skills_from_text(job_title)
            for sk in extracted:
                if sk.id not in must_skill_ids:
                    must_skill_ids.append(sk.id)

        total_reqs = len(must_skill_ids) + len(nice_skill_ids)
        if total_reqs == 0:
            return JobReadinessAssessment(
                job_id=job_id,
                match_percent=0,
                verdict="insufficient_data",
                data_coverage=0.0,
                requirements=[],
                explanation="Tin tuyển dụng này chưa cung cấp đủ thông tin kỹ năng để đối chiếu trình độ.",
                recommended_skills=[],
            )

        items: list[JobRequirementItem] = []
        known_count = 0
        must_scores: list[float] = []
        nice_scores: list[float] = []
        recommended_skills: list[str] = []

        all_specs = [(sid, "must") for sid in must_skill_ids] + [(sid, "nice") for sid in nice_skill_ids]

        for sid, importance in all_specs:
            defn = taxonomy.get_skill(sid)
            s_name = defn.name if defn else sid
            user_est = user_skills.get(sid)
            u_level = user_est.level if user_est else "none"
            u_level_num = LEVEL_NAME_TO_NUM.get(u_level, 0)
            u_confidence = user_est.confidence if user_est else 0.0

            if u_level == "none" or u_confidence < 0.20:
                status = "unknown"
                recommended_skills.append(sid)
            else:
                known_count += 1
                diff = u_level_num - target_level_num
                if diff >= 0:
                    status = "met"
                    cov = 1.0
                elif diff == -1:
                    status = "partial"
                    cov = 0.5
                    recommended_skills.append(sid)
                else:
                    status = "gap"
                    cov = 0.0
                    recommended_skills.append(sid)

                if importance == "must":
                    must_scores.append(cov)
                else:
                    nice_scores.append(cov)

            items.append(
                JobRequirementItem(
                    skill_id=sid,
                    name=s_name,
                    importance=importance,
                    required_level=target_level_name,
                    required_level_num=target_level_num,
                    user_level=u_level,
                    user_level_num=u_level_num,
                    status=status,
                    confidence=u_confidence,
                    level_assumed=level_assumed,
                )
            )

        data_coverage = round(known_count / max(1, total_reqs), 2)

        # Match calculation
        if known_count == 0:
            match_pct = 0
        else:
            must_avg = sum(must_scores) / max(1, len(must_scores)) if must_scores else 1.0
            nice_avg = sum(nice_scores) / max(1, len(nice_scores)) if nice_scores else 1.0
            if must_scores and nice_scores:
                match_pct = round(100 * (0.75 * must_avg + 0.25 * nice_avg))
            elif must_scores:
                match_pct = round(100 * must_avg)
            else:
                match_pct = round(100 * nice_avg)

        # Verdict
        has_must_gap = any(it.importance == "must" and it.status == "gap" for it in items)
        if data_coverage < 0.35:
            verdict = "insufficient_data"
        elif match_pct >= 75 and not has_must_gap:
            verdict = "ready"
        elif match_pct >= 50:
            verdict = "almost"
        else:
            verdict = "not_ready"

        # Explanation
        if verdict == "insufficient_data":
            explanation = (
                f"Hệ thống mới chỉ có dữ liệu {known_count}/{total_reqs} kỹ năng theo yêu cầu của công việc. "
                "Hãy hoàn thành thêm các buổi luyện tập để AI đánh giá chính xác độ sẵn sàng của bạn."
            )
        elif verdict == "ready":
            explanation = (
                f"Trình độ của bạn đáp ứng {match_pct}% yêu cầu chính của vị trí {job_title}. "
                "Các kỹ năng cốt lõi đều đạt chuẩn, bạn hoàn toàn tự tin ứng tuyển hoặc luyện tập thêm một buổi trước khi vào vòng thật!"
            )
        elif verdict == "almost":
            explanation = (
                f"Bạn đạt {match_pct}% độ tương thích với vị trí này. "
                "Bạn đã có nền tảng vững nhưng còn một vài kỹ năng cần củng cố thêm trước khi ứng tuyển."
            )
        else:
            explanation = (
                f"Độ tương thích hiện tại đạt {match_pct}%. "
                "Vị trí này đòi hỏi cấp bậc và kỹ năng chuyên sâu hơn. Hãy ôn tập theo các kỹ năng được gợi ý bên dưới."
            )

        return JobReadinessAssessment(
            job_id=job_id,
            match_percent=match_pct,
            verdict=verdict,
            data_coverage=data_coverage,
            requirements=items,
            explanation=explanation,
            recommended_skills=list(dict.fromkeys(recommended_skills))[:5],
        )
