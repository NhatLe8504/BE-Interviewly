from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from .models.job_aggregator import JobCompanyRecord, JobPostingRecord, JobSourceRecord

logger = logging.getLogger(__name__)


class SqlAlchemyJobAggregatorRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_source(
        self, source_id: str, source_name: str, source_type: str, base_url: str
    ) -> JobSourceRecord:
        source = self.session.execute(
            select(JobSourceRecord).where(JobSourceRecord.source_id == source_id)
        ).scalar_one_or_none()
        if source is None:
            source = JobSourceRecord(
                source_id=source_id,
                source_name=source_name,
                source_type=source_type,
                base_url=base_url,
                is_active=True,
                crawl_interval_m=120,
            )
            self.session.add(source)
            self.session.flush()
        return source

    def get_or_create_company(
        self, company_name: str, location: str | None = None, logo_url: str | None = None
    ) -> JobCompanyRecord:
        slug = re.sub(r"[^a-z0-9]+", "-", company_name.lower()).strip("-") or "company"
        company = self.session.execute(
            select(JobCompanyRecord).where(JobCompanyRecord.slug == slug)
        ).scalar_one_or_none()
        if company is None:
            company = JobCompanyRecord(
                company_name=company_name,
                slug=slug,
                location=location,
                logo_url=logo_url,
            )
            self.session.add(company)
            self.session.flush()
        return company

    def find_by_fingerprint(self, fingerprint: str) -> JobPostingRecord | None:
        return self.session.execute(
            select(JobPostingRecord)
            .options(joinedload(JobPostingRecord.company), joinedload(JobPostingRecord.source))
            .where(JobPostingRecord.content_fingerprint == fingerprint)
        ).scalar_one_or_none()

    def save_job(self, job_dict: dict[str, Any]) -> JobPostingRecord:
        source_id = job_dict.get("source_id", "serper_jobs")
        self.get_or_create_source(
            source_id=source_id,
            source_name=source_id.replace("_", " ").title(),
            source_type="serp_api" if "serper" in source_id else "ats_api",
            base_url="https://google.serper.dev" if "serper" in source_id else "https://boards-api.greenhouse.io",
        )

        company = self.get_or_create_company(
            company_name=job_dict.get("company_name", "Tech Company"),
            location=job_dict.get("company_location"),
        )

        fp = job_dict["content_fingerprint"]
        existing = self.find_by_fingerprint(fp)
        if existing:
            existing.updated_at = datetime.now(timezone.utc)
            existing.status = "ACTIVE"
            self.session.flush()
            return existing

        title = job_dict["title"]
        title_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        job_id = str(uuid.uuid4())

        record = JobPostingRecord(
            job_id=job_id,
            source_id=source_id,
            company_id=company.company_id,
            external_job_id=job_dict.get("external_job_id"),
            title=title,
            slug=f"{title_slug}-{job_id[:8]}",
            domain_id=job_dict.get("domain_id"),
            seniority=job_dict.get("seniority", "mid"),
            employment_type=job_dict.get("employment_type", "full_time"),
            workplace_type=job_dict.get("workplace_type", "hybrid"),
            location=job_dict.get("location"),
            salary_min=job_dict.get("salary_min"),
            salary_max=job_dict.get("salary_max"),
            salary_currency=job_dict.get("salary_currency", "VND"),
            is_salary_negotiable=job_dict.get("is_salary_negotiable", True),
            raw_description=job_dict.get("raw_description", ""),
            cleaned_jd_text=job_dict.get("cleaned_jd_text", ""),
            skills_required=job_dict.get("skills_required", []),
            technologies=job_dict.get("technologies", []),
            original_apply_url=job_dict["original_apply_url"],
            content_fingerprint=fp,
            via_source=job_dict.get("via_source"),
            status="ACTIVE",
            posted_at=datetime.now(timezone.utc),
        )
        self.session.add(record)
        self.session.flush()
        return record

    def list_jobs(
        self,
        keyword: str = "",
        domain_id: int | None = None,
        seniority: str = "",
        workplace_type: str = "",
        technology: str = "",
        page: int = 1,
        limit: int = 12,
    ) -> tuple[list[JobPostingRecord], int]:
        stmt = (
            select(JobPostingRecord)
            .options(joinedload(JobPostingRecord.company), joinedload(JobPostingRecord.source))
            .where(JobPostingRecord.status == "ACTIVE")
        )
        count_stmt = select(func.count(JobPostingRecord.job_id)).where(JobPostingRecord.status == "ACTIVE")

        if keyword:
            kw = f"%{keyword.lower()}%"
            cond = or_(
                func.lower(JobPostingRecord.title).like(kw),
                func.lower(JobPostingRecord.location).like(kw),
                func.lower(JobPostingRecord.cleaned_jd_text).like(kw),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        if domain_id:
            stmt = stmt.where(JobPostingRecord.domain_id == domain_id)
            count_stmt = count_stmt.where(JobPostingRecord.domain_id == domain_id)

        if seniority:
            stmt = stmt.where(JobPostingRecord.seniority == seniority)
            count_stmt = count_stmt.where(JobPostingRecord.seniority == seniority)

        if workplace_type:
            stmt = stmt.where(JobPostingRecord.workplace_type == workplace_type)
            count_stmt = count_stmt.where(JobPostingRecord.workplace_type == workplace_type)

        if technology:
            tech_kw = f"%{technology.lower()}%"
            cond = or_(
                func.lower(JobPostingRecord.title).like(tech_kw),
                func.lower(JobPostingRecord.cleaned_jd_text).like(tech_kw),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = self.session.execute(count_stmt).scalar() or 0
        offset = max(0, (page - 1) * limit)
        items = list(
            self.session.execute(
                stmt.order_by(JobPostingRecord.created_at.desc()).offset(offset).limit(limit)
            ).scalars().all()
        )
        return items, total

    def get_job_by_id(self, job_id: str) -> JobPostingRecord | None:
        return self.session.execute(
            select(JobPostingRecord)
            .options(joinedload(JobPostingRecord.company), joinedload(JobPostingRecord.source))
            .where(JobPostingRecord.job_id == job_id)
        ).scalar_one_or_none()

    def get_metadata_filters(self) -> dict[str, Any]:
        seniorities = ["intern", "fresher", "junior", "mid", "senior", "lead"]
        workplace_types = ["hybrid", "remote", "on_site"]
        top_technologies = [
            "Java", "React", "Golang", "Python", "TypeScript", "Node.js",
            "Spring Boot", "Kafka", "PostgreSQL", "Docker", "Kubernetes", "AWS"
        ]
        return {
            "seniorities": seniorities,
            "workplace_types": workplace_types,
            "top_technologies": top_technologies,
        }
