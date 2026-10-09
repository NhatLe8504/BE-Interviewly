from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobCompanyOut(BaseModel):
    company_id: int
    company_name: str
    slug: str
    logo_url: str | None = None
    company_logo_url: str | None = None
    company_banner_url: str | None = None
    branding_source_url: str | None = None
    branding_license_url: str | None = None
    branding_reuse_allowed: bool = False
    branding_candidates: dict[str, Any] = {}
    location: str | None = None


class JobItemOut(BaseModel):
    job_id: str
    source_id: str | None = None
    title: str
    slug: str
    seniority: str
    employment_type: str
    workplace_type: str
    location: str | None = None
    salary_display: str = "Chưa công bố"
    salary_currency: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    skills_required: list[str] = Field(default_factory=list)
    thumbnail_url: str | None = None
    technologies: list[str] = Field(default_factory=list)
    via_source: str | None = None
    original_apply_url: str
    posted_at: datetime | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_synced_at: datetime | None = None
    expires_at: datetime | None = None
    country_codes: list[str] = Field(default_factory=list)
    is_global_remote: bool = False
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
    locations: list[str] = Field(default_factory=list)
    countries: list[dict[str, str]] = Field(default_factory=list)
    sources: list[dict[str, str]] = Field(default_factory=list)
    sort_options: list[dict[str, str]] = Field(default_factory=list)


class JobSkillMatchOut(BaseModel):
    has_candidate_skills: bool = False
    job_id: str
    match_score_pct: int
    matched_skills: list[str]
    missing_skills: list[str]
    recommendation: str


class StartJobPracticeOut(BaseModel):
    interview_id: str
    job_id: str
    redirect_url: str
