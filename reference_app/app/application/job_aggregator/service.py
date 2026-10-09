from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from ...domain.job_aggregator import JobPosting, JobSkillMatch
from ...infrastructure.persistence.job_aggregator_repository import SqlAlchemyJobAggregatorRepository
from .adapters.ats_adapters import GreenhouseAdapter, SeedFallbackAdapter
from .adapters.recipe_engine import DomainRecipeRegistry, RecipeBasedCrawlerAdapter
from .adapters.serper_adapter import SerperGoogleJobsAdapter

logger = logging.getLogger(__name__)


class JobAggregatorService:
    def __init__(
        self,
        session: Session,
        serper_api_key: str = "",
        redis_client: Any = None,
        branding_lookup: Any = None,
    ) -> None:
        self.session = session
        self.repo = SqlAlchemyJobAggregatorRepository(session)
        self.serper_api_key = serper_api_key
        self.redis = redis_client
        self._lock_key = "interviewly:lock:job_ingestion"
        self.recipe_registry = DomainRecipeRegistry()
        if branding_lookup is None and serper_api_key:
            from ...infrastructure.company_branding import SerperCompanyBrandingLookup
            branding_lookup = SerperCompanyBrandingLookup(api_key=serper_api_key, redis_client=redis_client)
        self.branding_lookup = branding_lookup
        self.recipe_adapter = RecipeBasedCrawlerAdapter(
            registry=self.recipe_registry,
            branding_lookup=branding_lookup,
        )
        self._adapters = [
            self.recipe_adapter,
            SerperGoogleJobsAdapter(
                api_key=serper_api_key,
                branding_lookup=branding_lookup,
                recipe_registry=self.recipe_registry,
            ),
            GreenhouseAdapter(),
            SeedFallbackAdapter(),
        ]

    def _acquire_lock(self) -> bool:
        if self.redis is not None:
            try:
                # Lock TTL 600s
                return bool(self.redis.set(self._lock_key, "1", nx=True, ex=600))
            except Exception:
                return True
        return True

    def _release_lock(self) -> None:
        if self.redis is not None:
            try:
                self.redis.delete(self._lock_key)
            except Exception:
                pass

    async def run_ingestion(self, query: str = "", force_seed: bool = False) -> int:
        if not self._acquire_lock():
            logger.info("Job ingestion lock already active; skipping run.")
            return 0

        total_saved = 0
        try:
            # 1. Primary Ingestion: Verified Domain Recipes (Zero Serper credits burned)
            logger.info("Running Recipe-Based Crawler across verified domain recipes...")
            recipe_jobs = await self.recipe_adapter.fetch_jobs(query=query, limit=25)
            for j in recipe_jobs:
                self.repo.save_job(j)
                total_saved += 1

            # 2. Lifecycle expiration check
            self.repo.mark_expired_by_deadline()
            self.repo.mark_suspected_expired(days_threshold=7)

            # 3. Optional Serper discovery if explicitly configured and requested
            if self.serper_api_key and query:
                logger.info("Running Serper Google Jobs search for query '%s'...", query)
                serper_adapter = SerperGoogleJobsAdapter(api_key=self.serper_api_key)
                serper_jobs = await serper_adapter.fetch_jobs(query=query, limit=10)
                for j in serper_jobs:
                    self.repo.save_job(j)
                    total_saved += 1

            self.session.commit()
            logger.info("Job ingestion completed successfully. Saved/updated %d jobs.", total_saved)
        except Exception as exc:
            self.session.rollback()
            logger.error("Job ingestion failed: %s", exc)
        finally:
            self._release_lock()

        return total_saved

    async def backfill_missing_branding(self, limit: int = 50) -> int:
        if not self.branding_lookup:
            return 0
        from ...infrastructure.persistence.models.job_aggregator import JobPostingRecord
        from sqlalchemy import select
        from sqlalchemy.orm import joinedload
        postings = self.session.scalars(
            select(JobPostingRecord)
            .options(joinedload(JobPostingRecord.company))
            .where(JobPostingRecord.status == "ACTIVE")
        ).all()
        updated_companies: set[int] = set()
        for p in postings:
            if not p.company or p.company.company_id in updated_companies:
                continue
            if p.company.banner_url and p.company.logo_url and p.company.branding_reuse_allowed:
                continue
            recipe = self.recipe_registry.get(p.source_id)
            if not recipe:
                continue
            job_dummy = {
                "company_name": p.company.company_name,
                "original_apply_url": p.original_apply_url,
            }
            try:
                assets = await self.branding_lookup.lookup(job_dummy, recipe)
                if assets:
                    logo = assets.get("company_logo_url")
                    banner = assets.get("company_banner_url")
                    src = assets.get("branding_source_url")
                    lic = assets.get("branding_license_url")
                    allowed = assets.get("branding_reuse_allowed", False)
                    cand = assets.get("branding_candidates")
                    if logo:
                        p.company.logo_url = logo
                    if banner:
                        p.company.banner_url = banner
                        if not p.thumbnail_url:
                            p.thumbnail_url = banner
                    if src:
                        p.company.branding_source_url = src
                    if lic:
                        p.company.branding_license_url = lic
                    if allowed or (banner or logo):
                        p.company.branding_reuse_allowed = True
                    if cand:
                        p.company.branding_candidates = dict(cand)
                    updated_companies.add(p.company.company_id)
                    if len(updated_companies) >= limit:
                        break
            except Exception as exc:
                logger.debug("Backfill branding error for %s: %s", p.company.company_name, exc)
        if updated_companies:
            self.session.commit()
        return len(updated_companies)

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
    ) -> tuple[list[Any], int]:
        return self.repo.list_jobs(
            keyword=keyword,
            domain_id=domain_id,
            seniority=seniority,
            workplace_type=workplace_type,
            technology=technology,
            location=location,
            source_id=source_id,
            country_code=country_code,
            sort_by=sort_by,
            page=page,
            limit=limit,
        )

    def get_job_by_id(self, job_id: str) -> Any | None:
        return self.repo.get_job_by_id(job_id)

    def match_candidate_skills(self, job_id: str, candidate_skills: list[str]) -> JobSkillMatch | None:
        job = self.repo.get_job_by_id(job_id)
        if not job:
            return None

        required = list(dict.fromkeys(skill.strip().lower() for skill in (job.skills_required or []) if skill.strip()))
        user_skills = {skill.strip().lower() for skill in candidate_skills if skill.strip()}

        matching = [s for s in required if s in user_skills]
        missing = [s for s in required if s not in user_skills]
        pct = round((len(matching) / max(1, len(required))) * 100)

        recommendation = "Đối chiếu các kỹ năng còn thiếu với mô tả công việc để lên kế hoạch luyện tập."
        if not required:
            recommendation = "Nguồn chưa cung cấp đủ danh sách kỹ năng để đối chiếu."
        elif not user_skills:
            recommendation = "Bổ sung kỹ năng trong hồ sơ để đối chiếu với yêu cầu công việc."
        elif pct >= 80:
            recommendation = "Hồ sơ có nhiều kỹ năng trùng yêu cầu. Hãy đọc kỹ JD và luyện tập theo vị trí."
        elif pct >= 50:
            recommendation = "Hồ sơ khớp một phần yêu cầu. Tham khảo các kỹ năng còn thiếu để luyện tập."

        return JobSkillMatch(
            job_id=job_id,
            match_score_pct=pct,
            matched_skills=matching,
            missing_skills=missing,
            recommendation=recommendation,
        )

    def get_filter_metadata(self, country_code: str = "VN") -> dict[str, Any]:
        return self.repo.get_metadata_filters(country_code=country_code)

    def calculate_skill_match(self, job_id: str, candidate_skills: list[str]) -> JobSkillMatch:
        match = self.match_candidate_skills(job_id, candidate_skills)
        return match or JobSkillMatch(
            job_id=job_id, match_score_pct=0, matched_skills=[], missing_skills=[],
            recommendation="Chưa có thông tin công việc để đối chiếu.",
        )
