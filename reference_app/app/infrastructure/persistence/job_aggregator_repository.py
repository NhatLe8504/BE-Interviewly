from __future__ import annotations

from datetime import datetime, timezone, timedelta
import logging
import re
from typing import Any
import uuid

from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from .models.job_aggregator import JobCompanyRecord, JobPostingRecord, JobSourceRecord
from ...domain.job_metadata import detect_countries, is_global_remote, parse_source_datetime

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
                crawl_interval_m=60,
            )
            self.session.add(source)
            self.session.flush()
        return source

    def get_or_create_company(
        self, company_name: str, location: str | None = None, logo_url: str | None = None,
        banner_url: str | None = None, branding_source_url: str | None = None,
        branding_license_url: str | None = None, branding_reuse_allowed: bool = False,
    ) -> JobCompanyRecord:
        clean_name = company_name.strip() if company_name else "Tech Enterprise"
        slug = re.sub(r"[^a-z0-9]+", "-", clean_name.lower()).strip("-") or "company"
        company = self.session.execute(
            select(JobCompanyRecord).where(JobCompanyRecord.slug == slug)
        ).scalar_one_or_none()
        if company is None:
            company = JobCompanyRecord(
                company_name=clean_name,
                slug=slug,
                location=location,
            )
            self.session.add(company)
            self.session.flush()
        if branding_reuse_allowed and branding_source_url and branding_license_url:
            if logo_url:
                company.logo_url = logo_url
            if banner_url:
                company.banner_url = banner_url
            company.branding_source_url = branding_source_url
            company.branding_license_url = branding_license_url
            company.branding_reuse_allowed = True
            self.session.flush()
        return company

    def find_by_source_and_external_id(self, source_id: str, external_job_id: str) -> JobPostingRecord | None:
        if not external_job_id:
            return None
        return self.session.execute(
            select(JobPostingRecord)
            .options(joinedload(JobPostingRecord.company), joinedload(JobPostingRecord.source))
            .where(
                JobPostingRecord.source_id == source_id,
                JobPostingRecord.external_job_id == str(external_job_id),
            )
        ).scalar_one_or_none()

    def find_by_fingerprint(self, fingerprint: str) -> JobPostingRecord | None:
        if not fingerprint:
            return None
        return self.session.execute(
            select(JobPostingRecord)
            .options(joinedload(JobPostingRecord.company), joinedload(JobPostingRecord.source))
            .where(JobPostingRecord.content_fingerprint == fingerprint)
        ).scalar_one_or_none()

    def find_by_apply_url(self, apply_url: str) -> JobPostingRecord | None:
        if not apply_url:
            return None
        # Clean query parameters for canonical url match
        clean_url = apply_url.split("?")[0].strip()
        return self.session.execute(
            select(JobPostingRecord)
            .options(joinedload(JobPostingRecord.company), joinedload(JobPostingRecord.source))
            .where(JobPostingRecord.original_apply_url.like(f"{clean_url}%"))
        ).scalar_one_or_none()

    def upsert_job(self, job_dict: dict[str, Any]) -> tuple[JobPostingRecord, bool]:
        """
        Upserts job according to deduplication rules:
        1. Match by (source_id, external_job_id)
        2. Match by content_fingerprint
        3. Match by canonical apply_url
        Returns (record, is_new).
        """
        now = datetime.now(timezone.utc)
        source_id = job_dict.get("source_id", "web")
        ext_id = str(job_dict.get("external_job_id") or "")
        fp = job_dict.get("content_fingerprint", "")
        apply_url = job_dict.get("original_apply_url", "")

        # 1. Ensure source and company exist
        self.get_or_create_source(
            source_id=source_id,
            source_name=source_id.replace("_", " ").title(),
            source_type="crawler_recipe",
            base_url=job_dict.get("original_apply_url", "https://interviewly.ai"),
        )
        company = self.get_or_create_company(
            company_name=job_dict.get("company_name", "Doanh nghiệp IT"),
            location=job_dict.get("company_location"),
            logo_url=job_dict.get("company_logo_url"),
            banner_url=job_dict.get("company_banner_url"),
            branding_source_url=job_dict.get("branding_source_url"),
            branding_license_url=job_dict.get("branding_license_url"),
            branding_reuse_allowed=job_dict.get("branding_reuse_allowed", False),
        )

        # 2. Hierarchical duplicate search
        existing = (
            self.find_by_source_and_external_id(source_id, ext_id)
            or self.find_by_fingerprint(fp)
            or self.find_by_apply_url(apply_url)
        )

        if existing:
            existing.seniority = job_dict.get("seniority") or "unknown"
            existing.employment_type = job_dict.get("employment_type") or "unknown"
            existing.workplace_type = job_dict.get("workplace_type") or "unknown"
            existing.location = job_dict.get("location") or None
            existing.country_codes = detect_countries(existing.location)
            existing.is_global_remote = is_global_remote(existing.location, existing.workplace_type)
            source_posted_at = parse_source_datetime(job_dict.get("posted_at"))
            if source_posted_at:
                existing.posted_at = source_posted_at
            source_expires_at = parse_source_datetime(job_dict.get("expires_at"))
            if source_expires_at:
                existing.expires_at = source_expires_at
            # Job already exists: refresh last_seen_at
            existing.last_seen_at = now
            existing.last_verified_at = now
            if existing.status in ("SUSPECTED_EXPIRED", "EXPIRED"):
                existing.status = "ACTIVE"

            # Check if content changed
            new_desc = job_dict.get("cleaned_jd_text", "")
            if new_desc and new_desc != existing.cleaned_jd_text:
                existing.title = job_dict.get("title", existing.title)
                existing.cleaned_jd_text = new_desc
                existing.raw_description = job_dict.get("raw_description", existing.raw_description)
                existing.skills_required = job_dict.get("skills_required", existing.skills_required)
                existing.technologies = job_dict.get("technologies", existing.technologies)
                existing.content_fingerprint = fp or existing.content_fingerprint
                existing.updated_at = now

            self.session.flush()
            return existing, False

        # 3. Insert new job posting
        title = job_dict["title"].strip()
        title_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
        job_id = str(uuid.uuid4())

        record = JobPostingRecord(
            job_id=job_id,
            source_id=source_id,
            company_id=company.company_id,
            external_job_id=ext_id or None,
            title=title,
            slug=f"{title_slug}-{job_id[:8]}",
            domain_id=job_dict.get("domain_id"),
            seniority=job_dict.get("seniority") or "unknown",
            employment_type=job_dict.get("employment_type") or "unknown",
            workplace_type=job_dict.get("workplace_type") or "unknown",
            location=job_dict.get("location") or None,
            country_codes=detect_countries(job_dict.get("location")),
            is_global_remote=is_global_remote(job_dict.get("location"), job_dict.get("workplace_type", "unknown")),
            salary_min=job_dict.get("salary_min"),
            salary_max=job_dict.get("salary_max"),
            salary_currency=job_dict.get("salary_currency", "VND"),
            is_salary_negotiable=job_dict.get("is_salary_negotiable", True),
            raw_description=job_dict.get("raw_description", ""),
            cleaned_jd_text=job_dict.get("cleaned_jd_text", ""),
            skills_required=job_dict.get("skills_required", []),
            technologies=job_dict.get("technologies", []),
            original_apply_url=apply_url,
            content_fingerprint=fp,
            via_source=job_dict.get("via_source"),
            status="ACTIVE",
            posted_at=parse_source_datetime(job_dict.get("posted_at")),
            expires_at=parse_source_datetime(job_dict.get("expires_at")),
            first_seen_at=now,
            last_seen_at=now,
            last_verified_at=now,
        )
        self.session.add(record)
        self.session.flush()
        return record, True

    def save_job(self, job_dict: dict[str, Any]) -> JobPostingRecord:
        record, _ = self.upsert_job(job_dict)
        return record

    def list_jobs(
        self,
        keyword: str = "",
        domain_id: int | None = None,
        seniority: str = "",
        workplace_type: str = "",
        technology: str = "",
        location: str = "",
        source_id: str = "",
        country_code: str = "VN",
        sort_by: str = "recent",
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

        if location:
            loc_lower = location.lower()
            if loc_lower in ("remote", "từ xa"):
                stmt = stmt.where(or_(JobPostingRecord.workplace_type == "remote", func.lower(JobPostingRecord.location).like("%remote%")))
                count_stmt = count_stmt.where(or_(JobPostingRecord.workplace_type == "remote", func.lower(JobPostingRecord.location).like("%remote%")))
            else:
                loc_kw = f"%{loc_lower}%"
                stmt = stmt.where(func.lower(JobPostingRecord.location).like(loc_kw))
                count_stmt = count_stmt.where(func.lower(JobPostingRecord.location).like(loc_kw))

        if source_id:
            stmt = stmt.where(JobPostingRecord.source_id == source_id)
            count_stmt = count_stmt.where(JobPostingRecord.source_id == source_id)

        if country_code:
            country_condition = cast(JobPostingRecord.country_codes, String).contains(f'"{country_code.upper()}"')
            if country_code.upper() == "VN":
                country_condition = or_(country_condition, JobPostingRecord.is_global_remote.is_(True))
            elif country_code.upper() == "GLOBAL":
                country_condition = JobPostingRecord.is_global_remote.is_(True)
            stmt = stmt.where(country_condition)
            count_stmt = count_stmt.where(country_condition)

        if sort_by == "posted":
            order_clause = [JobPostingRecord.posted_at.desc().nullslast(), JobPostingRecord.created_at.desc()]
        elif sort_by == "salary_desc":
            order_clause = [JobPostingRecord.salary_max.desc().nullslast(), JobPostingRecord.updated_at.desc()]
        elif sort_by == "title_asc":
            order_clause = [JobPostingRecord.title.asc()]
        else:
            order_clause = [JobPostingRecord.updated_at.desc(), JobPostingRecord.created_at.desc()]

        total = self.session.execute(count_stmt).scalar() or 0
        offset = max(0, (page - 1) * limit)
        items = list(
            self.session.execute(
                stmt.order_by(*order_clause, JobPostingRecord.job_id).offset(offset).limit(limit)
            ).scalars().all()
        )
        return items, total

    def get_job_by_id(self, job_id: str) -> JobPostingRecord | None:
        return self.session.execute(
            select(JobPostingRecord)
            .options(joinedload(JobPostingRecord.company), joinedload(JobPostingRecord.source))
            .where(JobPostingRecord.job_id == job_id)
        ).scalar_one_or_none()

    def mark_expired_by_deadline(self) -> int:
        """Marks jobs whose explicit expires_at has passed as EXPIRED."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(JobPostingRecord)
            .where(
                JobPostingRecord.status == "ACTIVE",
                JobPostingRecord.expires_at.is_not(None),
                JobPostingRecord.expires_at < now,
            )
            .values(status="EXPIRED", updated_at=now)
        )
        res = self.session.execute(stmt)
        self.session.flush()
        return res.rowcount

    def mark_suspected_expired(self, days_threshold: int = 7) -> int:
        """Marks jobs not seen in listings for over days_threshold as SUSPECTED_EXPIRED."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_threshold)
        stmt = (
            update(JobPostingRecord)
            .where(
                JobPostingRecord.status == "ACTIVE",
                JobPostingRecord.last_seen_at < cutoff,
            )
            .values(status="SUSPECTED_EXPIRED", updated_at=datetime.now(timezone.utc))
        )
        res = self.session.execute(stmt)
        self.session.flush()
        return res.rowcount

    def get_metadata_filters(self) -> dict[str, Any]:
        from collections import Counter

        jobs = list(self.session.scalars(select(JobPostingRecord).where(JobPostingRecord.status == "ACTIVE")))
        technologies = Counter(technology for job in jobs for technology in job.technologies or [])
        country_names = {
            "VN": "Việt Nam", "US": "Hoa Kỳ", "GB": "Vương quốc Anh", "SG": "Singapore",
            "JP": "Nhật Bản", "DE": "Đức", "ES": "Tây Ban Nha", "IN": "Ấn Độ",
            "CA": "Canada", "AU": "Australia", "IE": "Ireland", "PL": "Ba Lan",
            "BR": "Brazil", "MX": "Mexico", "FR": "Pháp",
        }
        countries = sorted({code for job in jobs for code in job.country_codes or []})
        source_names = {
            "topcv": "TopCV", "itviec": "ITviec", "vietnamworks": "VietnamWorks",
            "vng": "VNG Careers", "linkedin": "LinkedIn", "greenhouse": "Greenhouse", "lever": "Lever",
        }
        source_ids = sorted({job.source_id for job in jobs})
        return {
            "seniorities": sorted({job.seniority for job in jobs if job.seniority != "unknown"}),
            "workplace_types": sorted({job.workplace_type for job in jobs if job.workplace_type != "unknown"}),
            "top_technologies": [technology for technology, count in technologies.most_common(10)],
            "locations": sorted({job.location for job in jobs if job.location}),
            "countries": [{"id": code, "name": country_names.get(code, code)} for code in countries]
                + ([{"id": "GLOBAL", "name": "Remote toàn cầu"}] if any(job.is_global_remote for job in jobs) else []),
            "sources": [{"id": source_id, "name": source_names.get(source_id, source_id)} for source_id in source_ids],
            "sort_options": [
                {"id": "recent", "name": "Mới cập nhật dữ liệu"},
                {"id": "posted", "name": "Mới đăng tuyển"},
                {"id": "title_asc", "name": "Tên công việc A – Z"},
            ],
        }
