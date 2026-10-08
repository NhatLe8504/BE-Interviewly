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
        self._adapters = [
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
            # Always run seed adapter if database has few jobs
            _, existing_count = self.repo.list_jobs(limit=1)
            if existing_count < 5 or force_seed:
                logger.info("Seeding initial high-quality jobs...")
                seed_adapter = SeedFallbackAdapter()
                seed_jobs = await seed_adapter.fetch_jobs(limit=20)
                for j in seed_jobs:
                    self.repo.save_job(j)
                    total_saved += 1

            # Run Serper adapter
            if self.serper_api_key:
                serper_adapter = SerperGoogleJobsAdapter(api_key=self.serper_api_key)
                serper_jobs = await serper_adapter.fetch_jobs(query=query, limit=15)
                for j in serper_jobs:
                    self.repo.save_job(j)
                    total_saved += 1

            # Run Greenhouse adapter
            gh_adapter = GreenhouseAdapter()
            gh_jobs = await gh_adapter.fetch_jobs(limit=10)
            for j in gh_jobs:
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

    def get_filter_metadata(self) -> dict[str, Any]:
        return self.repo.get_metadata_filters()

    def calculate_skill_match(self, job_id: str, candidate_skills: list[str]) -> JobSkillMatch:
        job = self.repo.get_job_by_id(job_id)
        if not job:
            return JobSkillMatch(
                job_id=job_id,
                match_score_pct=0,
                matched_skills=[],
                missing_skills=[],
                recommendation="Không tìm thấy thông tin tin tuyển dụng.",
            )

        job_skills = list(job.skills_required or [])
        if not job_skills:
            job_skills = list(job.technologies or [])

        candidate_lower = {s.lower().strip() for s in candidate_skills}
        matched = [s for s in job_skills if s.lower().strip() in candidate_lower]
        missing = [s for s in job_skills if s.lower().strip() not in candidate_lower]

        if not job_skills:
            score = 75
        else:
            score = int((len(matched) / len(job_skills)) * 100)
            score = max(20, min(100, score))

        if score >= 75:
            rec = "Hồ sơ của bạn rất phù hợp với vị trí này! Hãy tự tin luyện tập phỏng vấn ngay."
        elif score >= 50:
            rec = "Bạn đáp ứng được các kỹ năng cốt lõi. Nên ôn tập thêm các kỹ năng còn thiếu trước khi phỏng vấn."
        else:
            rec = "Vị trí này có nhiều yêu cầu công nghệ mới. Luyện tập với AI sẽ giúp bạn làm quen nhanh chóng."

        return JobSkillMatch(
            job_id=job_id,
            match_score_pct=score,
            matched_skills=matched,
            missing_skills=missing,
            recommendation=rec,
        )
