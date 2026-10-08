from __future__ import annotations

import logging
from typing import Any
import uuid

import httpx

from ....domain.job_aggregator import compute_job_fingerprint
from .base import BaseJobSourceAdapter

logger = logging.getLogger(__name__)


class GreenhouseAdapter(BaseJobSourceAdapter):
    def __init__(self, board_tokens: list[str] | None = None, timeout: float = 12.0) -> None:
        self.board_tokens = board_tokens or ["gitlab", "cloudflare"]
        self.timeout = timeout

    async def fetch_jobs(self, query: str = "", limit: int = 15) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for token in self.board_tokens:
                url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    jobs = data.get("jobs", [])
                    for j in jobs:
                        title = j.get("title", "")
                        loc = j.get("location", {}).get("name", "Remote")
                        apply_url = j.get("absolute_url", "")
                        if not title or not apply_url:
                            continue
                        # Filter software/engineering roles
                        title_lower = title.lower()
                        if not any(k in title_lower for k in ["engineer", "developer", "backend", "frontend", "fullstack", "devops", "software", "architect", "data"]):
                            continue

                        skills, techs = self.extract_tech_keywords(title, loc)
                        seniority = self.detect_seniority(title)
                        workplace = self.detect_workplace_type(title, loc)
                        emp_type = self.detect_employment_type(title)
                        company_name = token.capitalize()
                        description = f"Vị trí: {title} tại {company_name}.\nĐịa điểm làm việc: {loc}.\nXem chi tiết và ứng tuyển tại bài đăng gốc."
                        fp = compute_job_fingerprint(company_name, title, description)

                        results.append({
                            "external_job_id": str(j.get("id")),
                            "source_id": "greenhouse",
                            "company_name": company_name,
                            "company_location": loc,
                            "title": title,
                            "location": loc,
                            "seniority": seniority.value,
                            "employment_type": emp_type.value,
                            "workplace_type": workplace.value,
                            "raw_description": description,
                            "cleaned_jd_text": description,
                            "skills_required": skills,
                            "technologies": techs,
                            "original_apply_url": apply_url,
                            "content_fingerprint": fp,
                            "via_source": "via Greenhouse",
                        })
                        if len(results) >= limit:
                            break
                except Exception as exc:
                    logger.warning("Failed fetching greenhouse jobs for %s: %s", token, exc)
                if len(results) >= limit:
                    break
        return results


class SeedFallbackAdapter(BaseJobSourceAdapter):
    """Deprecated: Mock seed data is strictly disabled. Real crawler only."""
    async def fetch_jobs(self, query: str = "", limit: int = 30) -> list[dict[str, Any]]:
        return []

