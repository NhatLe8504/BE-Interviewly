from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobCompanyOut(BaseModel):
    company_id: int
    company_name: str
    slug: str
    logo_url: str | None = None
    location: str | None = None


class JobItemOut(BaseModel):
    job_id: str
    title: str
    slug: str
    seniority: str
    employment_type: str
    workplace_type: str
    location: str | None = None
    salary_display: str = "Thỏa thuận"
    salary_min: float | None = None
    salary_max: float | None = None
    skills_required: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    via_source: str | None = None
    original_apply_url: str
    posted_at: datetime | None = None
    company: JobCompanyOut | None = None


class JobDetailOut(JobItemOut):
    raw_description: str
    cleaned_jd_text: str
    created_at: datetime


class JobListResponse(BaseModel):
    total: int
    page: int
    limit: int
    total_pages: int
    items: list[JobItemOut]


class JobFilterMetadataOut(BaseModel):
    seniorities: list[str]
    workplace_types: list[str]
    top_technologies: list[str]


class JobSkillMatchOut(BaseModel):
    job_id: str
    match_score_pct: int
    matched_skills: list[str]
    missing_skills: list[str]
    recommendation: str


class StartJobPracticeOut(BaseModel):
    interview_id: str
    job_id: str
    redirect_url: str
