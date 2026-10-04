from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class JDQueueManager:
    """
    Queue Manager for asynchronous JD-to-Interview generation pipeline.
    Uses Redis as the primary broker and state cache, with in-memory fallback.
    """
    QUEUE_KEY = "interviewly:jd_queue"
    DLQ_KEY = "interviewly:jd_dlq"
    TASK_KEY_PREFIX = "interviewly:jd_job:"

    def __init__(self, redis_client: Any = None) -> None:
        self.redis = redis_client
        self._memory_store: dict[str, dict[str, Any]] = {}

    def enqueue(self, job_id: str, payload: dict[str, Any]) -> str:
        job_data = {
            "job_id": job_id,
            "status": "PENDING",
            "stage": "INITIALIZED",
            "progress_pct": 5,
            "created_at": time.time(),
            "updated_at": time.time(),
            "payload": payload,
            "result": None,
            "error": None,
        }

        if self.redis is not None:
            try:
                self.redis.setex(
                    f"{self.TASK_KEY_PREFIX}{job_id}",
                    86400,
                    json.dumps(job_data, ensure_ascii=False),
                )
                self.redis.lpush(self.QUEUE_KEY, json.dumps({"job_id": job_id}, ensure_ascii=False))
                return job_id
            except Exception as exc:
                logger.warning("Failed to push to Redis queue, using memory fallback: %s", exc)

        self._memory_store[job_id] = job_data
        return job_id

    def get_job_state(self, job_id: str) -> dict[str, Any] | None:
        if self.redis is not None:
            try:
                raw = self.redis.get(f"{self.TASK_KEY_PREFIX}{job_id}")
                if raw:
                    return json.loads(raw)
            except Exception:
                pass
        return self._memory_store.get(job_id)

    def update_job_progress(
        self,
        job_id: str,
        status: str,
        stage: str,
        progress_pct: int,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        state = self.get_job_state(job_id) or {
            "job_id": job_id,
            "created_at": time.time(),
            "payload": {},
        }
        state["status"] = status
        state["stage"] = stage
        state["progress_pct"] = progress_pct
        state["updated_at"] = time.time()
        if result is not None:
            state["result"] = result
        if error is not None:
            state["error"] = error

        if self.redis is not None:
            try:
                self.redis.setex(
                    f"{self.TASK_KEY_PREFIX}{job_id}",
                    86400,
                    json.dumps(state, ensure_ascii=False),
                )
                return
            except Exception as exc:
                logger.warning("Failed to update job in Redis: %s", exc)

        self._memory_store[job_id] = state

    def push_to_dlq(self, job_id: str, error_details: dict[str, Any]) -> None:
        dlq_entry = {
            "job_id": job_id,
            "failed_at": time.time(),
            "details": error_details,
        }
        if self.redis is not None:
            try:
                self.redis.lpush(self.DLQ_KEY, json.dumps(dlq_entry, ensure_ascii=False))
                return
            except Exception:
                pass
        logger.error("Job %s pushed to Dead Letter Queue: %s", job_id, error_details)
