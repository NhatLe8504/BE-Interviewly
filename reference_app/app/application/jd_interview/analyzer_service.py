from __future__ import annotations

import json
import logging
import re
from typing import Any
import httpx

from ...domain.errors import DomainValidationError
from ...domain.jd_interview import (
    BlueprintSection,
    InterviewBlueprint,
    JobAnalysis,
    NormalizedJD,
    JDSectionType,
    JDSeniorityLevel,
)
from .prompts import (
    PROMPT_VERSIONS,
    build_jd_analysis_system_prompt,
    build_jd_analysis_user_prompt,
)
from .schemas import JobAnalysisExtractionSchema

logger = logging.getLogger(__name__)


def _extract_json_from_llm(raw_text: str) -> dict[str, Any]:
    if not raw_text:
        return {}
    clean = raw_text.strip()
    try:
        return json.loads(clean)
    except Exception:
        pass

    # Match ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", clean)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass

    # Match outermost curly braces
    first_brace = clean.find("{")
    last_brace = clean.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(clean[first_brace : last_brace + 1])
        except Exception:
            pass

    return {}


class JDAnalyzerService:
    def __init__(
        self,
        api_key: str = "",
        model: str = "llama-3.3-70b-versatile",
        base_url: str = "https://api.groq.com/openai/v1",
    ) -> None:
        self.api_key = api_key
        self.model = model or "llama-3.3-70b-versatile"
        if api_key.startswith("gsk_"):
            self.base_url = "https://api.groq.com/openai/v1"
        else:
            self.base_url = base_url.rstrip("/")

    async def _call_llm_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not self.api_key:
            return {}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return _extract_json_from_llm(content)

    def _fallback_heuristic_analysis(self, normalized_jd: NormalizedJD) -> JobAnalysis:
        text = normalized_jd.cleaned_text
        lower = text.lower()

        # Job title extraction heuristic
        first_line = text.split("\n")[0][:100]
        title = first_line.strip()
        if len(title) < 5 or any(kw in title.lower() for kw in ["tuyển dụng", "job description", "yêu cầu"]):
            title = "Software Engineer"
            for role_name in ["Backend Engineer", "Frontend Engineer", "Fullstack Engineer", "DevOps Engineer", "Data Engineer", "Mobile Developer", "QA Engineer", "Product Manager"]:
                if role_name.lower() in lower:
                    title = role_name
                    break

        # Seniority extraction heuristic
        seniority = JDSeniorityLevel.junior.value
        for lvl in [JDSeniorityLevel.lead, JDSeniorityLevel.senior, JDSeniorityLevel.mid, JDSeniorityLevel.fresher, JDSeniorityLevel.intern]:
            if lvl.value in lower:
                seniority = lvl.value
                break

        # Tech extraction heuristic
        common_techs = ["python", "fastapi", "django", "nodejs", "react", "vue", "next.js", "typescript", "golang", "java", "spring", "docker", "kubernetes", "aws", "postgresql", "mysql", "redis", "mongodb", "git", "ci/cd", "rest api", "graphql"]
        detected_tech = [t.title() for t in common_techs if re.search(r"\b" + re.escape(t) + r"\b", lower)]

        return JobAnalysis(
            job_title=title,
            seniority=seniority,
            responsibilities=["Phát triển và bảo trì các tính năng của hệ thống.", "Tối ưu hiệu năng và độ ổn định của ứng dụng.", "Phối hợp với các thành viên trong nhóm để thiết kế kiến trúc."],
            required_skills=detected_tech[:6] or ["Lập trình căn bản", "Cấu trúc dữ liệu & giải thuật", "Thiết kế hệ thống"],
            preferred_skills=detected_tech[6:10],
            technologies=detected_tech,
            domain_knowledge=["Phát triển phần mềm", "Clean Architecture"],
            soft_skills=["Làm việc nhóm", "Giải quyết vấn đề", "Giao tiếp kỹ thuật"],
            technical_signals=["Khả năng giải thích kiến trúc", "Tư duy clean code & testing"],
            behavioral_signals=["Thái độ cầu tiến", "Trách nhiệm với sản phẩm"],
            confidence_score=0.85,
        )

    async def analyze(self, normalized_jd: NormalizedJD) -> JobAnalysis:
        system_prompt = build_jd_analysis_system_prompt()
        user_prompt = build_jd_analysis_user_prompt(normalized_jd.cleaned_text, normalized_jd.language)

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                raw_json = await self._call_llm_json(system_prompt, user_prompt)
                if raw_json and "job_title" in raw_json:
                    schema_data = JobAnalysisExtractionSchema(**raw_json)
                    return JobAnalysis(
                        job_title=schema_data.job_title,
                        company_name=schema_data.company_name,
                        seniority=schema_data.seniority,
                        employment_type=schema_data.employment_type,
                        location=schema_data.location,
                        responsibilities=schema_data.responsibilities or ["Đảm nhiệm các yêu cầu chuyên môn theo JD."],
                        required_skills=schema_data.required_skills or ["Kỹ năng chuyên môn chính"],
                        preferred_skills=schema_data.preferred_skills,
                        technologies=schema_data.technologies,
                        domain_knowledge=schema_data.domain_knowledge,
                        soft_skills=schema_data.soft_skills,
                        technical_signals=schema_data.technical_signals,
                        behavioral_signals=schema_data.behavioral_signals,
                        confidence_score=schema_data.confidence_score,
                    )
            except Exception as exc:
                last_error = exc
                logger.warning("LLM analysis attempt %d failed: %s", attempt + 1, exc)

        logger.info("Using fallback heuristic analysis for JD")
        return self._fallback_heuristic_analysis(normalized_jd)


class InterviewPlannerService:
    @staticmethod
    def build_blueprint(
        analysis: JobAnalysis,
        total_duration_minutes: int = 45,
        target_difficulty: int | None = None,
    ) -> InterviewBlueprint:
        # Determine target difficulty based on seniority if not overridden
        seniority_diff_map = {
            JDSeniorityLevel.intern.value: 2,
            JDSeniorityLevel.fresher.value: 2,
            JDSeniorityLevel.junior.value: 3,
            JDSeniorityLevel.mid.value: 3,
            JDSeniorityLevel.senior.value: 4,
            JDSeniorityLevel.lead.value: 5,
            JDSeniorityLevel.staff.value: 5,
            JDSeniorityLevel.principal.value: 5,
        }
        diff = target_difficulty if target_difficulty is not None else seniority_diff_map.get(analysis.seniority, 3)

        # Distribute competencies and sections
        tech_competency = f"Kiến thức cốt lõi & Công nghệ ({', '.join(analysis.required_skills[:3]) if analysis.required_skills else analysis.job_title})"
        scenario_competency = f"Xử lý tình huống kỹ thuật & Thiết kế ({analysis.job_title})"
        behavioral_competency = "Giao tiếp, làm việc nhóm & Văn hóa phù hợp"

        competencies = [tech_competency, scenario_competency, behavioral_competency]

        sections = [
            BlueprintSection(
                section_type=JDSectionType.introduction.value,
                allocated_minutes=5,
                target_competencies=["Giới thiệu bản thân & định hướng nghề nghiệp"],
                question_count=1,
                objective="Tạo tâm lý thoải mái và tìm hiểu tổng quan background ứng viên.",
            ),
            BlueprintSection(
                section_type=JDSectionType.technical.value,
                allocated_minutes=max(15, int(total_duration_minutes * 0.45)),
                target_competencies=[tech_competency],
                question_count=3,
                objective="Đánh giá chiều sâu kiến thức kỹ thuật và kỹ năng lập trình bắt buộc trong JD.",
            ),
            BlueprintSection(
                section_type=JDSectionType.scenario.value,
                allocated_minutes=max(10, int(total_duration_minutes * 0.25)),
                target_competencies=[scenario_competency],
                question_count=2,
                objective="Đánh giá tư duy giải quyết vấn đề, kiến trúc hệ thống và xử lý sự cố.",
            ),
            BlueprintSection(
                section_type=JDSectionType.behavioral.value,
                allocated_minutes=max(10, int(total_duration_minutes * 0.20)),
                target_competencies=[behavioral_competency],
                question_count=2,
                objective="Đánh giá tinh thần trách nhiệm, phản xạ khi gặp áp lực và làm việc nhóm theo mô hình STAR.",
            ),
            BlueprintSection(
                section_type=JDSectionType.closing.value,
                allocated_minutes=5,
                target_competencies=["Q&A & Đúc kết"],
                question_count=1,
                objective="Giải đáp thắc mắc của ứng viên và kết thúc buổi phỏng vấn chuyên nghiệp.",
            ),
        ]

        return InterviewBlueprint(
            target_role=analysis.job_title,
            seniority=analysis.seniority,
            total_duration_minutes=total_duration_minutes,
            target_difficulty=diff,
            objectives=[
                f"Đánh giá mức độ phù hợp toàn diện với vị trí {analysis.job_title} ({analysis.seniority}).",
                "Xác minh kinh nghiệm thực chiến với các kỹ năng trọng yếu trong JD.",
                "Đo lường năng lực giải quyết tình huống kỹ thuật và độ chín chắn nghề nghiệp.",
            ],
            competencies=competencies,
            sections=sections,
            scoring_dimensions=[
                "Technical Depth (Độ sâu kỹ thuật)",
                "Problem Solving & Architecture (Tư duy giải quyết vấn đề)",
                "Communication & STAR Clarity (Giao tiếp & cấu trúc trả lời)",
                "Cultural & Behavioral Alignment (Độ phù hợp văn hóa)",
            ],
        )
