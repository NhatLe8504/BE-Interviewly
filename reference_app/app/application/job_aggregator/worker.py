from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import time
from typing import Any

from sqlalchemy.orm import sessionmaker, Session

from ...infrastructure.persistence.job_aggregator_repository import SqlAlchemyJobAggregatorRepository
from .adapters.recipe_engine import RecipeBasedCrawlerAdapter

logger = logging.getLogger(__name__)


class JobIngestionWorker:
    def __init__(
        self,
        session_factory: sessionmaker,
        redis_client: Any = None,
        serper_api_key: str = "",
        crawl_interval_seconds: int = 3600,
        branding_lookup: Any = None,
    ) -> None:
        self.session_factory = session_factory
        self.redis_client = redis_client
        self.serper_api_key = serper_api_key
        self.crawl_interval_seconds = crawl_interval_seconds
        self.lock_key = "interviewly:lock:job_ingestion"
        self.lock_ttl_seconds = 600

        self.crawler_adapter = RecipeBasedCrawlerAdapter(branding_lookup=branding_lookup)
        self.is_running = False
        self._task: asyncio.Task[None] | None = None
        self.last_run_stats: dict[str, Any] = {
            "status": "idle",
            "last_run_at": None,
            "next_run_at": None,
            "total_fetched": 0,
            "new_jobs": 0,
            "updated_jobs": 0,
            "expired_jobs": 0,
            "duration_seconds": 0.0,
        }

    def acquire_lock(self) -> bool:
        if self.redis_client is not None:
            try:
                acquired = bool(self.redis_client.set(self.lock_key, "1", nx=True, ex=self.lock_ttl_seconds))
                if not acquired:
                    logger.info("Ingestion lock already held by another worker process.")
                return acquired
            except Exception as exc:
                logger.warning("Redis lock error: %s; proceeding locally.", exc)
                return True
        return True

    def release_lock(self) -> None:
        if self.redis_client is not None:
            try:
                self.redis_client.delete(self.lock_key)
            except Exception as exc:
                logger.debug("Failed releasing redis lock: %s", exc)

    async def run_cycle(self, query: str = "", limit: int = 30) -> dict[str, Any]:
        """Runs a complete crawl, validation, upsert, and expiration cycle."""
        if not self.acquire_lock():
            return {
                "status": "skipped_locked",
                "message": "Another worker is currently executing the crawl cycle.",
                "last_run_stats": self.last_run_stats,
            }

        start_time = time.perf_counter()
        now = datetime.now(timezone.utc)
        logger.info("[JobIngestionWorker] Starting automated crawl cycle across verified recipes...")

        new_count = 0
        updated_count = 0
        total_fetched = 0
        expired_count = 0
        suspected_count = 0

        session: Session = self.session_factory()
        try:
            repo = SqlAlchemyJobAggregatorRepository(session)

            # 1. Fetch real jobs across verified recipes
            crawled_jobs = await self.crawler_adapter.fetch_jobs(query=query, limit=limit)
            total_fetched = len(crawled_jobs)

            # 2. Upsert each job with deduplication
            for job_dict in crawled_jobs:
                try:
                    _, is_new = repo.upsert_job(job_dict)
                    if is_new:
                        new_count += 1
                    else:
                        updated_count += 1
                except Exception as exc:
                    logger.warning("Error upserting job '%s': %s", job_dict.get("title"), exc)

            # 3. Check expirations
            expired_count = repo.mark_expired_by_deadline()
            suspected_count = repo.mark_suspected_expired(days_threshold=7)

            session.commit()
            elapsed = round(time.perf_counter() - start_time, 2)

            self.last_run_stats = {
                "status": "completed",
                "last_run_at": now.isoformat(),
                "next_run_at": datetime.fromtimestamp(now.timestamp() + self.crawl_interval_seconds, tz=timezone.utc).isoformat(),
                "total_fetched": total_fetched,
                "new_jobs": new_count,
                "updated_jobs": updated_count,
                "expired_jobs": expired_count,
                "suspected_expired": suspected_count,
                "duration_seconds": elapsed,
            }
            logger.info(
                "[JobIngestionWorker] Crawl cycle completed in %.2fs: Fetched=%d, New=%d, Updated=%d, Expired=%d",
                elapsed, total_fetched, new_count, updated_count, expired_count,
            )
            return self.last_run_stats

        except Exception as exc:
            session.rollback()
            logger.error("[JobIngestionWorker] Crawl cycle failed: %s", exc, exc_info=True)
            self.last_run_stats["status"] = f"error: {exc}"
            return self.last_run_stats
        finally:
            session.close()
            self.release_lock()

    async def _scheduler_loop(self) -> None:
        logger.info("[JobIngestionWorker] Scheduler started (Interval: %ds)", self.crawl_interval_seconds)
        # Initial warmup delay: 2s
        await asyncio.sleep(2.0)
        while self.is_running:
            try:
                await self.run_cycle()
            except Exception as exc:
                logger.error("[JobIngestionWorker] Unexpected error in scheduler loop: %s", exc)

            try:
                await asyncio.sleep(self.crawl_interval_seconds)
            except asyncio.CancelledError:
                break

        logger.info("[JobIngestionWorker] Scheduler loop stopped.")

    def start_background_scheduler(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._scheduler_loop())

    def stop(self) -> None:
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
