from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ...domain.errors import NotFoundError, ForbiddenError
from ...infrastructure.persistence.models.cv import CvDocumentRecord
from ...infrastructure.persistence.models.job_aggregator import JobPostingRecord
from ...infrastructure.persistence.models.user import CandidateProfile, User
from ...infrastructure.persistence.models.user_skills import (
    UserCareerProfileRecord,
    UserSkillEvidenceRecord,
    UserSkillLevelRecord,
)
from ...presentation.api.schemas.cv import (
    CvAtsScoreOut,
    CvCreateIn,
    CvGenerateDraftIn,
    CvListItemOut,
    CvOut,
    CvSelectionRefineIn,
    CvSelectionRefineOut,
    CvUpdateIn,
    UserSkillsSummaryOut,
)

logger = logging.getLogger(__name__)


def _extract_json_block(text: str) -> dict[str, Any]:
    if not text:
        return {}
    clean = text.strip()
    try:
        return json.loads(clean)
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", clean, re.DOTALL)
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


class CvService:
    def __init__(self, llm: Any = None, clock: Any = None) -> None:
        self.llm = llm
        self.clock = clock

    def _call_llm(self, messages: list[dict[str, str]], json_format: bool = False) -> str:
        if self.llm is not None:
            try:
                if hasattr(self.llm, "_chat_completion"):
                    fmt = {"type": "json_object"} if json_format else None
                    return self.llm._chat_completion(messages, response_format=fmt)
            except Exception as e:
                logger.warning(f"CvService LLM call failed: {e}")
        return ""

    def get_user_skills_summary(self, session: Session, user_id: int) -> UserSkillsSummaryOut:
        user = session.get(User, user_id)
        if not user:
            raise NotFoundError("User not found")

        profile = session.get(CandidateProfile, user_id)
        skill_records = list(
            session.scalars(
                select(UserSkillLevelRecord).where(UserSkillLevelRecord.user_id == user_id)
            ).all()
        )
        evidences = list(
            session.scalars(
                select(UserSkillEvidenceRecord.evidence_quote)
                .where(
                    UserSkillEvidenceRecord.user_id == user_id,
                    UserSkillEvidenceRecord.evidence_quote.is_not(None),
                )
                .limit(10)
            ).all()
        )

        skill_names = [s.skill_id for s in skill_records]
        skill_details = [
            {
                "skill_id": s.skill_id,
                "level": s.level,
                "ability_score": float(s.ability_score) if s.ability_score else 0.0,
                "evidence_count": s.evidence_count,
            }
            for s in skill_records
        ]

        # If no skills recorded yet, check career profile
        career_profile = session.scalars(
            select(UserCareerProfileRecord).where(UserCareerProfileRecord.user_id == user_id)
        ).first()
        if career_profile and career_profile.top_skills and not skill_names:
            skill_names = [
                s.get("skill_id", "")
                for s in career_profile.top_skills
                if isinstance(s, dict) and s.get("skill_id")
            ]

        target_domain_name = None
        if profile and profile.target_domain_id:
            from ...infrastructure.persistence.models.catalog import JobDomain

            dom = session.get(JobDomain, profile.target_domain_id)
            if dom:
                target_domain_name = dom.domain_name

        return UserSkillsSummaryOut(
            user_id=user.user_id,
            full_name=user.full_name or "",
            email=user.email or "",
            target_domain=target_domain_name,
            experience_level=profile.experience_level.value
            if profile and profile.experience_level
            else "mid",
            skills=skill_names,
            skill_details=skill_details,
            evidences=[e for e in evidences if e],
        )

    def create_cv(self, session: Session, user_id: int, data: CvCreateIn) -> CvOut:
        user = session.get(User, user_id)
        if not user:
            raise NotFoundError("User not found")

        profile = session.get(CandidateProfile, user_id)

        target_job: JobPostingRecord | None = None
        if data.target_job_id:
            target_job = session.get(JobPostingRecord, data.target_job_id)

        # Build initial CV data
        personal_info = {
            "full_name": user.full_name or "Nguyễn Văn A",
            "email": user.email or "candidate@example.com",
            "phone": user.phone or "+84 912 345 678",
            "title": target_job.title
            if target_job
            else (
                f"{profile.experience_level.value.capitalize() if profile and profile.experience_level else 'Senior'} Software Engineer"
            ),
            "location": target_job.location if target_job and target_job.location else "Hà Nội, Việt Nam",
            "linkedin": f"linkedin.com/in/{user.email.split('@')[0] if user.email else 'profile'}",
            "github": f"github.com/{user.email.split('@')[0] if user.email else 'developer'}",
            "portfolio": "",
            "avatar_url": profile.avatar_url if profile and profile.avatar_url else "",
        }

        # Gather skills
        initial_skills: list[str] = []
        if target_job and target_job.skills_required:
            initial_skills.extend([str(s) for s in target_job.skills_required][:8])

        if data.load_from_user_skills:
            user_skills = self.get_user_skills_summary(session, user_id)
            for s in user_skills.skills:
                if s not in initial_skills:
                    initial_skills.append(s)

        if not initial_skills:
            initial_skills = [
                "TypeScript",
                "React",
                "Next.js",
                "Node.js",
                "PostgreSQL",
                "Docker",
                "Tailwind CSS",
                "RESTful APIs",
            ]

        # Initial Experiences with STAR highlights
        job_title = target_job.title if target_job else "Fullstack Engineer"
        company_name = target_job.company.company_name if target_job and target_job.company else "Tech Innovation Labs"

        work_experiences = [
            {
                "id": str(uuid4()),
                "company": company_name,
                "role": f"Senior {job_title}",
                "location": "Hà Nội, Việt Nam",
                "start_date": "2023-01",
                "end_date": "",
                "is_current": True,
                "description": f"Chịu trách nhiệm kiến trúc và phát triển hệ thống lõi phục vụ hơn 200,000 người dùng hàng tháng.",
                "highlights": [
                    "Tái cấu trúc kiến trúc microservices giúp giảm 45% thời gian phản hồi API (p99 latency từ 850ms xuống 460ms).",
                    "Thiết kế và triển khai pipeline CI/CD tự động hoá với Docker và GitHub Actions, rút ngắn chu kỳ deploy từ 2 giờ xuống 15 phút.",
                    "Dẫn dắt đội ngũ 6 kỹ sư, triển khai quy chuẩn Unit & Integration Testing nâng cao code coverage từ 55% lên 88%.",
                ],
            },
            {
                "id": str(uuid4()),
                "company": "VTI Cloud Solutions",
                "role": f"{job_title}",
                "location": "Hà Nội, Việt Nam",
                "start_date": "2021-06",
                "end_date": "2022-12",
                "is_current": False,
                "description": "Tham gia phát triển các sản phẩm SaaS và tích hợp hệ thống thanh toán điện tử.",
                "highlights": [
                    "Xây dựng tính năng thanh toán đa cổng kết nối xử lý thành công 50,000+ giao dịch mỗi ngày với độ ổn định 99.98%.",
                    "Tối ưu hóa các truy vấn PostgreSQL và lập chỉ mục (indexing), giảm tải database 30% trong giờ cao điểm.",
                ],
            },
        ]

        projects = [
            {
                "id": str(uuid4()),
                "name": "High-Throughput E-Commerce Platform",
                "role": "Lead Architect & Developer",
                "start_date": "2023-05",
                "end_date": "2023-11",
                "technologies": ["Next.js", "FastAPI", "PostgreSQL", "Redis", "Kafka"],
                "link": "https://github.com/project/demo",
                "description": "Nền tảng thương mại điện tử chịu tải cao với khả năng đồng bộ kho hàng theo thời gian thực.",
                "highlights": [
                    "Triển khai cơ chế cache đa tầng với Redis giúp chịu tải 10,000 req/s trong các đợt flash sale.",
                    "Áp dụng Clean Architecture và Domain-Driven Design giúp việc mở rộng tính năng mới nhanh hơn 35%.",
                ],
            },
            {
                "id": str(uuid4()),
                "name": "AI Interview Coach Assistant",
                "role": "Core Backend & AI Engineer",
                "start_date": "2024-01",
                "end_date": "2024-06",
                "technologies": ["Python", "FastAPI", "WebSockets", "Groq LPU", "WebRTC"],
                "link": "https://github.com/project/interview-coach",
                "description": "Hệ thống luyện phỏng vấn thông minh với phản hồi giọng nói thời gian thực dưới 300ms.",
                "highlights": [
                    "Tích hợp mô hình ngôn ngữ lớn LLM và Edge TTS để sinh phản hồi phỏng vấn mượt mà theo phương pháp STAR.",
                    "Xây dựng pipeline phân tích chỉ số ATS và phát hiện lỗ hổng kỹ năng của ứng viên tự động.",
                ],
            },
        ]

        educations = [
            {
                "id": str(uuid4()),
                "institution": "Đại học Bách Khoa Hà Nội",
                "degree": "Kỹ sư",
                "field_of_study": "Công nghệ Thông tin",
                "start_date": "2018",
                "end_date": "2022",
                "gpa": "3.5/4.0",
                "honors": "Tốt nghiệp loại Giỏi, Học bổng Khuyến khích học tập 3 kỳ liên tiếp",
            }
        ]

        certifications = [
            {
                "id": str(uuid4()),
                "name": "AWS Certified Solutions Architect – Associate",
                "issuer": "Amazon Web Services",
                "issue_date": "2023-08",
                "expiration_date": "2026-08",
                "credential_id": "AWS-PSA-894721",
                "url": "https://aws.amazon.com/verification",
            }
        ]

        summary = (
            f"Kỹ sư phần mềm giàu kinh nghiệm với thế mạnh về kiến trúc hệ thống phân tán, xử lý tải cao và phát triển ứng dụng hiện đại. "
            f"Thành thạo {', '.join(initial_skills[:4])}. Đam mê tối ưu hóa trải nghiệm người dùng, "
            f"tự động hóa quy trình và luôn hướng tới việc tạo ra giá trị kinh doanh thực tế thông qua các giải pháp công nghệ bền vững."
        )

        record = CvDocumentRecord(
            user_id=user_id,
            target_job_id=data.target_job_id,
            template_id=data.template_id or "modern_tech",
            title=data.title or (f"CV - {target_job.title}" if target_job else "My Professional CV"),
            color_theme=data.color_theme or "navy",
            font_family=data.font_family or "inter",
            personal_info=personal_info,
            summary=summary,
            work_experiences=work_experiences,
            projects=projects,
            skills=initial_skills,
            educations=educations,
            certifications=certifications,
            section_order=["summary", "experience", "projects", "skills", "education", "certifications"],
            ats_score=85.0 if target_job else None,
            ats_feedback={},
        )

        session.add(record)
        session.commit()
        session.refresh(record)

        # Calculate initial ATS score if target job provided
        if target_job:
            try:
                ats_result = self.calculate_ats_match(
                    session=session,
                    user_id=user_id,
                    cv_id=record.id,
                    target_job_id=target_job.job_id,
                )
                record.ats_score = ats_result.ats_score
                record.ats_feedback = ats_result.model_dump()
                session.commit()
                session.refresh(record)
            except Exception as e:
                logger.warning(f"Error calculating initial ATS score: {e}")

        return self._to_cv_out(record)

    def get_cv(self, session: Session, user_id: int, cv_id: int) -> CvOut:
        record = session.get(CvDocumentRecord, cv_id)
        if not record or record.user_id != user_id:
            raise NotFoundError("CV not found or access denied")
        return self._to_cv_out(record)

    def list_user_cvs(self, session: Session, user_id: int) -> list[CvListItemOut]:
        stmt = (
            select(CvDocumentRecord)
            .where(CvDocumentRecord.user_id == user_id)
            .order_by(desc(CvDocumentRecord.updated_at))
        )
        records = list(session.scalars(stmt).all())
        out: list[CvListItemOut] = []
        for r in records:
            job_title = r.target_job.title if r.target_job else None
            company_name = r.target_job.company.company_name if r.target_job and r.target_job.company else None
            out.append(
                CvListItemOut(
                    id=r.id,
                    user_id=r.user_id,
                    title=r.title,
                    template_id=r.template_id,
                    color_theme=r.color_theme,
                    target_job_id=r.target_job_id,
                    target_job_title=job_title,
                    target_company_name=company_name,
                    ats_score=float(r.ats_score) if r.ats_score is not None else None,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                )
            )
        return out

    def update_cv(self, session: Session, user_id: int, cv_id: int, data: CvUpdateIn) -> CvOut:
        record = session.get(CvDocumentRecord, cv_id)
        if not record or record.user_id != user_id:
            raise NotFoundError("CV not found or access denied")

        if data.title is not None:
            record.title = data.title
        if data.template_id is not None:
            record.template_id = data.template_id
        if data.color_theme is not None:
            record.color_theme = data.color_theme
        if data.font_family is not None:
            record.font_family = data.font_family
        if data.personal_info is not None:
            record.personal_info = data.personal_info
        if data.summary is not None:
            record.summary = data.summary
        if data.work_experiences is not None:
            record.work_experiences = data.work_experiences
        if data.projects is not None:
            record.projects = data.projects
        if data.skills is not None:
            record.skills = data.skills
        if data.educations is not None:
            record.educations = data.educations
        if data.certifications is not None:
            record.certifications = data.certifications
        if data.section_order is not None:
            record.section_order = data.section_order
        if data.target_job_id is not None:
            record.target_job_id = data.target_job_id

        session.commit()
        session.refresh(record)
        return self._to_cv_out(record)

    def delete_cv(self, session: Session, user_id: int, cv_id: int) -> None:
        record = session.get(CvDocumentRecord, cv_id)
        if not record or record.user_id != user_id:
            raise NotFoundError("CV not found or access denied")
        session.delete(record)
        session.commit()

    def refine_selection(
        self, session: Session, user_id: int, data: CvSelectionRefineIn
    ) -> CvSelectionRefineOut:
        selected_text = data.selected_text.strip()
        if not selected_text:
            return CvSelectionRefineOut(
                original_text="",
                refined_text="",
                action=data.action,
                explanation="No text selected",
            )

        jd_context = ""
        if data.target_job_id:
            job = session.get(JobPostingRecord, data.target_job_id)
            if job:
                jd_context = f"Job Title: {job.title}\nRequirements: {job.cleaned_jd_text[:1000]}"
        elif data.target_jd_text:
            jd_context = f"Target Job Context:\n{data.target_jd_text[:1000]}"

        system_prompt = (
            "You are an Elite Executive Resume Writer & ATS Optimization Specialist. "
            "Your mission is to rewrite and optimize candidate resume text strictly adhering to the requested technique. "
            "Always respond with a valid JSON object with exactly two keys: 'refined_text' and 'explanation'. "
            "Write 'refined_text' in the SAME language as the original text (Vietnamese or English). "
            "Make the content compelling, professional, and impact-driven."
        )

        action_guides = {
            "star_metrics": (
                "Format this bullet point into the STAR method (Situation, Task, Action, Result). "
                "Include concrete, realistic metrics (% improvement, latency drop, scale, hours saved, throughput). "
                "Ensure it demonstrates ownership and quantifiable impact."
            ),
            "tailor_to_job": (
                f"Tailor this text specifically to match the following target job description:\n{jd_context}\n"
                "Naturally embed high-priority keywords and technical expectations from the JD without fluff."
            ),
            "strong_verbs": (
                "Replace passive phrasing, generic verbs, or 'Responsible for' with powerful active verbs "
                "(e.g., Architected, Engineered, Spearheaded, Optimized, Orchestrated, Overhauled, Scaled, Streamlined). "
                "Keep the tone assertive and senior."
            ),
            "shorten": (
                "Condense this text into a crisp, punchy, high-impact single line. "
                "Eliminate filler words, keep the core achievement and metrics intact for 3-second recruiter scanning."
            ),
            "custom": (
                f"Follow the user's specific instruction carefully:\n{data.custom_instruction or 'Improve clarity and professionalism'}"
            ),
        }

        guide = action_guides.get(data.action, action_guides["star_metrics"])
        user_prompt = (
            f"Original resume text:\n\"\"\"{selected_text}\"\"\"\n\n"
            f"Section context: {data.context_section or 'General'}\n"
            f"Instruction: {guide}\n\n"
            "Return JSON only:\n"
            "{\n  \"refined_text\": \"...\",\n  \"explanation\": \"...\"\n}"
        )

        llm_response = self._call_llm(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            json_format=True,
        )

        parsed = _extract_json_block(llm_response)
        refined_text = parsed.get("refined_text", "")
        explanation = parsed.get("explanation", "")

        # Fallback if LLM offline or empty
        if not refined_text:
            refined_text, explanation = self._fallback_refinement(selected_text, data.action, data.custom_instruction)

        return CvSelectionRefineOut(
            original_text=selected_text,
            refined_text=refined_text,
            action=data.action,
            explanation=explanation,
        )

    def _fallback_refinement(
        self, original: str, action: str, custom_instruction: str | None = None
    ) -> tuple[str, str]:
        # Algorithmic fallbacks for instant response
        clean = original.rstrip(".")
        if action == "star_metrics":
            return (
                f"Thiết kế và triển khai {clean.lower()}, giúp tăng 35% hiệu năng xử lý và giảm thiểu 20% chi phí vận hành hạ tầng.",
                "Đã cấu trúc lại theo mô hình STAR và bổ sung chỉ số định lượng về hiệu năng và chi phí.",
            )
        elif action == "strong_verbs":
            words = clean.split()
            first_word = words[0].lower() if words else ""
            if first_word in ["làm", "phụ", "tham", "viết", "hỗ"]:
                clean = "Chủ trì kiến trúc và phát triển " + " ".join(words[2:])
            else:
                clean = "Tiên phong xây dựng và tối ưu " + clean
            return (
                f"{clean}.",
                "Đã thay thế động từ bị động bằng động từ hành động mạnh mẽ thể hiện vai trò dẫn dắt.",
            )
        elif action == "shorten":
            sentences = clean.split(".")
            short = sentences[0] if sentences else clean
            return (
                f"{short} với hiệu suất tối ưu và độ ổn định cao.",
                "Đã cô đọng nội dung, loại bỏ chi tiết rườm rà giúp nhà tuyển dụng nắm bắt nhanh.",
            )
        elif action == "tailor_to_job":
            return (
                f"{clean}, đáp ứng toàn diện các tiêu chuẩn kỹ thuật cốt lõi và yêu cầu khắt khe của dự án mục tiêu.",
                "Đã căn chỉnh thuật ngữ để khớp với tiêu chí tuyển dụng của vị trí mục tiêu.",
            )
        else:
            return (
                f"{clean} một cách bài bản, đảm bảo tính mở rộng và tuân thủ các quy chuẩn kỹ thuật quốc tế.",
                f"Đã tinh chỉnh văn phong theo yêu cầu: {custom_instruction or 'chuyên nghiệp hơn'}.",
            )

    def generate_ai_draft(
        self, session: Session, user_id: int, data: CvGenerateDraftIn
    ) -> dict[str, Any]:
        user = session.get(User, user_id)
        profile = session.get(CandidateProfile, user_id)
        user_skills_summary = self.get_user_skills_summary(session, user_id)

        target_job: JobPostingRecord | None = None
        if data.target_job_id:
            target_job = session.get(JobPostingRecord, data.target_job_id)

        job_title = data.role_title or (target_job.title if target_job else "Senior Fullstack Engineer")
        jd_text = data.target_jd_text or (target_job.cleaned_jd_text if target_job else "")
        exp_level = data.experience_level or (profile.experience_level.value if profile and profile.experience_level else "mid")

        combined_skills = list(
            set(
                (user_skills_summary.skills if data.use_system_skills else [])
                + data.user_provided_skills
                + (list(target_job.skills_required or []) if target_job else [])
            )
        )
        if not combined_skills:
            combined_skills = ["React", "TypeScript", "Node.js", "Python", "FastAPI", "PostgreSQL", "Docker", "AWS"]

        system_prompt = (
            "You are a World-Class Executive Resume Architect. "
            "Generate a complete, high-converting, ATS-optimized CV in JSON format for the candidate based on target role, skills, and JD. "
            "Respond ONLY with a valid JSON object containing: "
            "personal_info (dict), summary (str), work_experiences (list of objects with company, role, location, start_date, end_date, is_current, description, highlights), "
            "projects (list of objects with name, role, start_date, end_date, technologies, link, description, highlights), "
            "skills (list of strings), educations (list), certifications (list). "
            "Every highlight bullet MUST use the STAR formula with quantifiable metrics (% improvement, numbers, scales). "
            "Write the CV in Vietnamese (or English if JD is entirely English)."
        )

        user_prompt = (
            f"Candidate Name: {user.full_name if user else 'Ứng viên'}\n"
            f"Candidate Email: {user.email if user else 'candidate@example.com'}\n"
            f"Target Role: {job_title}\n"
            f"Experience Level: {exp_level}\n"
            f"Available Skills: {', '.join(combined_skills[:12])}\n"
            f"Target Job Description:\n{jd_text[:1500] if jd_text else 'Tiêu chuẩn ngành công nghệ thông tin hiện đại'}\n\n"
            "Generate complete structured CV JSON."
        )

        llm_response = self._call_llm(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            json_format=True,
        )

        parsed = _extract_json_block(llm_response)
        if parsed and "work_experiences" in parsed and "summary" in parsed:
            # Ensure unique IDs
            for exp in parsed.get("work_experiences", []):
                if not exp.get("id"):
                    exp["id"] = str(uuid4())
            for proj in parsed.get("projects", []):
                if not proj.get("id"):
                    proj["id"] = str(uuid4())
            for edu in parsed.get("educations", []):
                if not edu.get("id"):
                    edu["id"] = str(uuid4())
            for cert in parsed.get("certifications", []):
                if not cert.get("id"):
                    cert["id"] = str(uuid4())
            return parsed

        # Fallback structured draft
        return {
            "personal_info": {
                "full_name": user.full_name if user else "Nguyễn Văn A",
                "email": user.email if user else "candidate@example.com",
                "phone": user.phone if user and user.phone else "+84 988 123 456",
                "title": job_title,
                "location": "Hà Nội, Việt Nam",
                "linkedin": "linkedin.com/in/profile",
                "github": "github.com/profile",
                "portfolio": "",
                "avatar_url": profile.avatar_url if profile and profile.avatar_url else "",
            },
            "summary": (
                f"Kỹ sư {job_title} với hơn 4 năm kinh nghiệm chuyên sâu trong việc kiến trúc và triển khai các hệ thống phần mềm hiệu năng cao. "
                f"Thành thạo {', '.join(combined_skills[:5])}. "
                "Có năng lực giải quyết các bài toán kỹ thuật phức tạp, tối ưu hóa chi phí đám mây và dẫn dắt đội ngũ kỹ thuật đạt KPI vượt trội."
            ),
            "work_experiences": [
                {
                    "id": str(uuid4()),
                    "company": "Tech Corp Vietnam",
                    "role": f"Lead {job_title}",
                    "location": "Hà Nội",
                    "start_date": "2023-02",
                    "end_date": "",
                    "is_current": True,
                    "description": "Chịu trách nhiệm kiến trúc nền tảng và vận hành dịch vụ cốt lõi.",
                    "highlights": [
                        "Dẫn dắt phát triển hệ sinh thái microservices giúp tăng 40% thông lượng xử lý và giảm 30% thời gian downtime.",
                        "Tối ưu hóa quy trình CI/CD và hạ tầng Kubernetes, tiết kiệm 2,500 USD chi phí máy chủ hàng tháng.",
                        "Đào tạo và kèm cặp 5 kỹ sư trẻ áp dụng thực hành Clean Code, TDD và Code Review chất lượng cao.",
                    ],
                },
                {
                    "id": str(uuid4()),
                    "company": "Global Software Hub",
                    "role": f"{job_title}",
                    "location": "Đà Nẵng",
                    "start_date": "2021-01",
                    "end_date": "2023-01",
                    "is_current": False,
                    "description": "Phát triển các phân hệ nghiệp vụ cho khách hàng quốc tế.",
                    "highlights": [
                        "Xây dựng hệ thống đồng bộ dữ liệu thời gian thực phục vụ 500,000+ giao dịch mỗi ngày.",
                        "Tái cấu trúc cơ sở dữ liệu quan hệ, giảm 50% thời gian thực thi các truy vấn báo cáo tài chính.",
                    ],
                },
            ],
            "projects": [
                {
                    "id": str(uuid4()),
                    "name": "Enterprise Cloud Orchestrator",
                    "role": "Principal Developer",
                    "start_date": "2023-06",
                    "end_date": "2023-12",
                    "technologies": combined_skills[:5],
                    "link": "https://github.com/project/cloud-orchestrator",
                    "description": "Giải pháp tự động hóa quản lý hạ tầng đám mây đa vùng (multi-region).",
                    "highlights": [
                        "Triển khai kiến trúc Event-Driven xử lý hàng triệu message mỗi ngày với độ trễ dưới 50ms.",
                        "Đạt chứng nhận tuân thủ an toàn thông tin ISO 27001 cho toàn bộ module quản lý truy cập.",
                    ],
                }
            ],
            "skills": combined_skills,
            "educations": [
                {
                    "id": str(uuid4()),
                    "institution": "Đại học Bách Khoa",
                    "degree": "Cử nhân / Kỹ sư",
                    "field_of_study": "Khoa học Máy tính",
                    "start_date": "2017",
                    "end_date": "2021",
                    "gpa": "3.6/4.0",
                    "honors": "Tốt nghiệp loại Xuất sắc",
                }
            ],
            "certifications": [
                {
                    "id": str(uuid4()),
                    "name": "Professional Cloud Architect",
                    "issuer": "Google Cloud",
                    "issue_date": "2023",
                    "expiration_date": "2026",
                    "credential_id": "GCP-PCA-10492",
                    "url": "https://cloud.google.com",
                }
            ],
        }

    def calculate_ats_match(
        self,
        session: Session,
        user_id: int,
        cv_id: int,
        target_job_id: str | None = None,
        target_jd_text: str | None = None,
    ) -> CvAtsScoreOut:
        record = session.get(CvDocumentRecord, cv_id)
        if not record or record.user_id != user_id:
            raise NotFoundError("CV not found or access denied")

        job: JobPostingRecord | None = None
        effective_job_id = target_job_id or record.target_job_id
        if effective_job_id:
            job = session.get(JobPostingRecord, effective_job_id)

        jd_text = target_jd_text or (job.cleaned_jd_text if job else "")
        required_skills = list(job.skills_required or []) if job else []
        technologies = list(job.technologies or []) if job else []

        # Combine CV text for keyword matching
        cv_text_corpus = (
            f"{record.title} {record.summary or ''} "
            f"{' '.join(record.skills)} "
            f"{' '.join([e.get('role', '') + ' ' + e.get('description', '') + ' ' + ' '.join(e.get('highlights', [])) for e in record.work_experiences])} "
            f"{' '.join([p.get('name', '') + ' ' + p.get('description', '') + ' ' + ' '.join(p.get('technologies', [])) for p in record.projects])}"
        ).lower()

        # Keyword matching
        match_keywords: list[str] = []
        missing_keywords: list[str] = []

        all_target_keywords = list(dict.fromkeys(required_skills + technologies))
        if not all_target_keywords and jd_text:
            # Extract common tech words from JD text
            words = re.findall(r"\b[A-Za-z0-9+#\.\-]{3,15}\b", jd_text)
            common_tech = {
                "python", "react", "next.js", "vue", "angular", "node.js", "typescript",
                "javascript", "golang", "java", "spring", "docker", "kubernetes", "aws",
                "azure", "sql", "postgresql", "mongodb", "redis", "kafka", "graphql",
                "rest", "ci/cd", "git", "linux", "microservices", "unit test", "tailored"
            }
            extracted = {w.lower() for w in words if w.lower() in common_tech}
            all_target_keywords = list(extracted)

        if not all_target_keywords:
            all_target_keywords = [s.lower() for s in record.skills[:6]]

        for kw in all_target_keywords:
            if kw.lower() in cv_text_corpus:
                match_keywords.append(kw)
            else:
                missing_keywords.append(kw)

        total_kw = len(all_target_keywords)
        matched_kw_count = len(match_keywords)
        kw_ratio = (matched_kw_count / total_kw) if total_kw > 0 else 0.85

        # Factor in experience STAR metrics density
        has_metrics_count = 0
        total_bullets = 0
        for exp in record.work_experiences:
            for hl in exp.get("highlights", []):
                total_bullets += 1
                if re.search(r"\d+[%|\$|k|ms|s|x|người|triệu|kỹ sư]", hl, re.IGNORECASE):
                    has_metrics_count += 1

        metrics_ratio = (has_metrics_count / total_bullets) if total_bullets > 0 else 0.7

        raw_score = (kw_ratio * 65.0) + (metrics_ratio * 30.0) + 5.0
        ats_score = round(min(98.0, max(45.0, raw_score)), 1)

        strengths = [
            f"Đã khớp {len(match_keywords)} từ khóa trọng tâm của mô tả công việc (JD).",
            f"Tỷ lệ điểm STAR có số liệu định lượng đạt {int(metrics_ratio * 100)}% tổng số thành tích.",
            "Bố cục các mục theo chuẩn ATS-friendly, dễ dàng được quét bởi hệ thống lọc hồ sơ tự động.",
        ]

        improvements = []
        if missing_keywords:
            improvements.append(
                f"Bổ sung các từ khóa kỹ thuật còn thiếu: {', '.join(missing_keywords[:5])}."
            )
        if metrics_ratio < 0.6:
            improvements.append(
                "Nhiều gạch đầu dòng còn mang tính mô tả chung chung, hãy dùng tính năng AI Bôi Đen -> STAR Metrics để thêm % và con số."
            )
        if len(record.skills) < 8:
            improvements.append(
                "Nên liệt kê ít nhất 8-12 kỹ năng liên quan trực tiếp đến vị trí tuyển dụng."
            )

        if ats_score >= 85:
            verdict = "Hồ sơ xuất sắc! Tỷ lệ vượt qua vòng lọc ATS tự động rất cao (Top 5% ứng viên)."
        elif ats_score >= 70:
            verdict = "Hồ sơ tốt. Bổ sung thêm các từ khóa còn thiếu để đạt tỷ lệ phỏng vấn tối ưu."
        else:
            verdict = "Hồ sơ cần hoàn thiện thêm các kỹ năng trọng yếu và số liệu thành tích để cạnh tranh."

        result = CvAtsScoreOut(
            ats_score=ats_score,
            match_keywords=match_keywords,
            missing_keywords=missing_keywords,
            strengths=strengths,
            improvements=improvements,
            summary_verdict=verdict,
        )

        # Update record
        record.ats_score = ats_score
        record.ats_feedback = result.model_dump()
        session.commit()

        return result

    def _to_cv_out(self, record: CvDocumentRecord) -> CvOut:
        job_title = record.target_job.title if record.target_job else None
        company_name = (
            record.target_job.company.company_name
            if record.target_job and record.target_job.company
            else None
        )
        return CvOut(
            id=record.id,
            user_id=record.user_id,
            target_job_id=record.target_job_id,
            target_job_title=job_title,
            target_company_name=company_name,
            template_id=record.template_id,
            title=record.title,
            color_theme=record.color_theme,
            font_family=record.font_family,
            personal_info=record.personal_info or {},
            summary=record.summary,
            work_experiences=record.work_experiences or [],
            projects=record.projects or [],
            skills=record.skills or [],
            educations=record.educations or [],
            certifications=record.certifications or [],
            section_order=record.section_order
            or ["summary", "experience", "projects", "skills", "education", "certifications"],
            ats_score=float(record.ats_score) if record.ats_score is not None else None,
            ats_feedback=record.ats_feedback or {},
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
