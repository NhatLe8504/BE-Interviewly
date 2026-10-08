from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import enum
import hashlib
import re
from typing import Any


class JobSeniority(str, enum.Enum):
    intern = "intern"
    fresher = "fresher"
    junior = "junior"
    mid = "mid"
    senior = "senior"
    lead = "lead"


class JobEmploymentType(str, enum.Enum):
    full_time = "full_time"
    part_time = "part_time"
    contract = "contract"
    internship = "internship"


class JobWorkplaceType(str, enum.Enum):
    remote = "remote"
    hybrid = "hybrid"
    on_site = "on_site"


class JobStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    SUSPECTED = "SUSPECTED"


class JobSourceType(str, enum.Enum):
    serp_api = "serp_api"
    ats_api = "ats_api"
    rss = "rss"
    crawler = "crawler"


def compute_job_fingerprint(company_name: str, title: str, description: str) -> str:
    norm_company = re.sub(r"[^a-z0-9]", "", company_name.lower())
    norm_title = re.sub(r"[^a-z0-9]", "", title.lower())
    norm_desc = re.sub(r"\s+", " ", description.lower().strip())[:200]
    raw = f"{norm_company}|{norm_title}|{norm_desc}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class JobCompany:
    company_name: str
    slug: str
    company_id: int | None = None
    logo_url: str | None = None
    website_url: str | None = None
    industry: str | None = None
    location: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class JobSource:
    source_id: str
    source_name: str
    source_type: JobSourceType
    base_url: str
    is_active: bool = True
    crawl_interval_m: int = 120
    last_synced_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class JobPosting:
    job_id: str
    source_id: str
    company_id: int
    title: str
    slug: str
    raw_description: str
    cleaned_jd_text: str
    original_apply_url: str
    content_fingerprint: str
    external_job_id: str | None = None
    domain_id: int | None = None
    seniority: JobSeniority = JobSeniority.mid
    employment_type: JobEmploymentType = JobEmploymentType.full_time
    workplace_type: JobWorkplaceType = JobWorkplaceType.hybrid
    location: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = "VND"
    is_salary_negotiable: bool = True
    skills_required: list[str] = field(default_factory=list)
    technologies: list[str] = field(default_factory=list)
    via_source: str | None = None
    status: JobStatus = JobStatus.ACTIVE
    posted_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    company: JobCompany | None = None


@dataclass
class JobSkillMatch:
    job_id: str
    match_score_pct: int
    matched_skills: list[str]
    missing_skills: list[str]
    recommendation: str
