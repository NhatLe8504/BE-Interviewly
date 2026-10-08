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
    ) -> None:
        self.session = session
        self.repo = SqlAlchemyJobAggregatorRepository(session)
        self.serper_api_key = serper_api_key
        self.redis = redis_client
        self._lock_key = "interviewly:lock:job_ingestion"
        self.recipe_registry = DomainRecipeRegistry()
        self.recipe_adapter = RecipeBasedCrawlerAdapter(registry=self.recipe_registry)
        self._adapters = [
            self.recipe_adapter,
            SerperGoogleJobsAdapter(api_key=serper_api_key),
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

            # 2. Seed fallback if database is empty
            _, existing_count = self.repo.list_jobs(limit=1)
            if existing_count < 5 or force_seed:
                logger.info("Seeding initial high-quality jobs...")
                seed_adapter = SeedFallbackAdapter()
                seed_jobs = await seed_adapter.fetch_jobs(limit=20)
                for j in seed_jobs:
                    self.repo.save_job(j)
                    total_saved += 1

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

    def list_jobs(
        self,
        keyword: str = "",
        domain_id: int | None = None,
        seniority: str = "",
        workplace_type: str = "",
        technology: str = "",
        page: int = 1,
        limit: int = 12,
    ) -> tuple[list[Any], int]:
        return self.repo.list_jobs(
            keyword=keyword,
            domain_id=domain_id,
            seniority=seniority,
            workplace_type=workplace_type,
            technology=technology,
            page=page,
            limit=limit,
        )

    def get_job_by_id(self, job_id: str) -> Any | None:
        return self.repo.get_job_by_id(job_id)

    def match_candidate_skills(self, job_id: str, candidate_skills: list[str]) -> JobSkillMatch | None:
        job = self.repo.get_job_by_id(job_id)
        if not job:
            return None

        required = [s.lower() for s in (job.skills_required or [])]
        user_skills = [s.lower() for s in candidate_skills]

        matching = [s for s in required if s in user_skills]
        missing = [s for s in required if s not in user_skills]
        pct = (len(matching) / max(1, len(required))) * 100.0

        readiness = "Cần bổ sung kiến thức chuyên sâu"
        if pct >= 80:
            readiness = "Rất sẵn sàng ứng tuyển"
        elif pct >= 50:
            readiness = "Đáp ứng cơ bản yêu cầu"

        return JobSkillMatch(
            matching_skills=matching,
            missing_skills=missing,
            readiness_score=round(pct, 1),
            readiness_assessment=readiness,
        )
