from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class CvPersonalInfo(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    title: str = ""
    location: str = ""
    linkedin: str = ""
    github: str = ""
    portfolio: str = ""
    avatar_url: str = ""


class CvWorkExperience(BaseModel):
    id: str = ""
    company: str = ""
    role: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    is_current: bool = False
    description: str = ""
    highlights: list[str] = Field(default_factory=list)


class CvProject(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    start_date: str = ""
    end_date: str = ""
    technologies: list[str] = Field(default_factory=list)
    link: str = ""
    description: str = ""
    highlights: list[str] = Field(default_factory=list)


class CvEducation(BaseModel):
    id: str = ""
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str = ""
    end_date: str = ""
    gpa: str = ""
    honors: str = ""


class CvCertification(BaseModel):
    id: str = ""
    name: str = ""
    issuer: str = ""
    issue_date: str = ""
    expiration_date: str = ""
    credential_id: str = ""
    url: str = ""


class CvCreateIn(BaseModel):
    title: str = "My Professional CV"
    template_id: str = "modern_tech"
    color_theme: str = "navy"
    font_family: str = "inter"
    target_job_id: str | None = None
    target_jd_text: str | None = None
    load_from_user_skills: bool = False


class CvUpdateIn(BaseModel):
    title: str | None = None
    template_id: str | None = None
    color_theme: str | None = None
    font_family: str | None = None
    personal_info: dict[str, Any] | None = None
    summary: str | None = None
    work_experiences: list[dict[str, Any]] | None = None
    projects: list[dict[str, Any]] | None = None
    skills: list[str] | None = None
    educations: list[dict[str, Any]] | None = None
    certifications: list[dict[str, Any]] | None = None
    section_order: list[str] | None = None
    target_job_id: str | None = None


class CvOut(BaseModel):
    id: int
    user_id: int
    target_job_id: str | None = None
    target_job_title: str | None = None
    target_company_name: str | None = None
    template_id: str
    title: str
    color_theme: str
    font_family: str
    personal_info: dict[str, Any]
    summary: str | None = None
    work_experiences: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    educations: list[dict[str, Any]] = Field(default_factory=list)
    certifications: list[dict[str, Any]] = Field(default_factory=list)
    section_order: list[str] = Field(default_factory=list)
    ats_score: float | None = None
    ats_feedback: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class CvListItemOut(BaseModel):
    id: int
    user_id: int
    title: str
    template_id: str
    color_theme: str
    target_job_id: str | None = None
    target_job_title: str | None = None
    target_company_name: str | None = None
    ats_score: float | None = None
    created_at: datetime
    updated_at: datetime


SelectionRefineAction = Literal[
    "star_metrics",
    "tailor_to_job",
    "strong_verbs",
    "shorten",
    "custom",
]


class CvSelectionRefineIn(BaseModel):
    selected_text: str
    action: SelectionRefineAction = "star_metrics"
    custom_instruction: str | None = None
    context_section: str | None = None  # experience, project, summary, skills
    target_job_id: str | None = None
    target_jd_text: str | None = None


class CvSelectionRefineOut(BaseModel):
    original_text: str
    refined_text: str
    action: str
    explanation: str


class CvGenerateDraftIn(BaseModel):
    target_job_id: str | None = None
    target_jd_text: str | None = None
    role_title: str | None = None
    experience_level: str | None = None
    user_provided_skills: list[str] = Field(default_factory=list)
    use_system_skills: bool = True
    current_cv_data: dict[str, Any] | None = None


class CvAtsScoreIn(BaseModel):
    target_job_id: str | None = None
    target_jd_text: str | None = None


class CvAtsScoreOut(BaseModel):
    ats_score: float
    match_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    summary_verdict: str


class UserSkillsSummaryOut(BaseModel):
    user_id: int
    full_name: str
    email: str
    target_domain: str | None = None
    experience_level: str | None = None
    skills: list[str] = Field(default_factory=list)
    skill_details: list[dict[str, Any]] = Field(default_factory=list)
    evidences: list[str] = Field(default_factory=list)
