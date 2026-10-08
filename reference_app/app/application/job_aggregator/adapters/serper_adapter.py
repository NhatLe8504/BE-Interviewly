from __future__ import annotations

import logging
import re
from typing import Any
import uuid

import httpx

from ....domain.job_aggregator import compute_job_fingerprint
from .base import BaseJobSourceAdapter

logger = logging.getLogger(__name__)

DEFAULT_QUERIES = [
    "tuyen dung Java backend developer Ha Noi TopCV ITviec",
    "tuyen dung React frontend engineer Ho Chi Minh ITviec",
    "tuyen dung Golang developer VietnamWorks TopCV",
    "tuyen dung Python AI machine learning engineer",
    "tuyen dung DevOps cloud AWS Kubernetes Vietnam",
    "tuyen dung Fullstack Node.js developer Ha Noi Ho Chi Minh",
]


class SerperGoogleJobsAdapter(BaseJobSourceAdapter):
    def __init__(self, api_key: str, timeout: float = 12.0) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.endpoint = "https://google.serper.dev/search"

    async def fetch_jobs(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        if not self.api_key:
            logger.warning("SERPER_API_KEY is not configured; skipping Serper ingestion.")
            return []

        queries = [query] if query else DEFAULT_QUERIES[:3]
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

        results: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for q in queries:
                try:
                    resp = await client.post(
                        self.endpoint,
                        headers=headers,
                        json={"q": q, "gl": "vn", "hl": "vi", "num": 10},
                    )
                    if resp.status_code != 200:
                        logger.warning("Serper returned status %d for query '%s'", resp.status_code, q)
                        continue
                    data = resp.json()
                    organic_items = data.get("organic", [])
                    for item in organic_items:
                        parsed = self._parse_organic_item(item)
                        if parsed:
                            results.append(parsed)
                            if len(results) >= limit:
                                break
                except Exception as exc:
                    logger.warning("Failed querying Serper for query '%s': %s", q, exc)
                if len(results) >= limit:
                    break

        return results

    def _parse_organic_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        raw_title = item.get("title", "").strip()
        link = item.get("link", "").strip()
        snippet = item.get("snippet", "").strip()
        if not raw_title or not link:
            return None

        via = "via Web"
        if "itviec.com" in link:
            via = "via ITviec"
        elif "topcv.vn" in link:
            via = "via TopCV"
        elif "vietnamworks.com" in link:
            via = "via VietnamWorks"
        elif "linkedin.com" in link:
            via = "via LinkedIn"
        elif "glints.com" in link:
            via = "via Glints"

        # Clean title
        clean_title = re.sub(r"\s*[-|–]\s*(ITviec|TopCV|VietnamWorks|LinkedIn|Glints).*$", "", raw_title, flags=re.I).strip()
        clean_title = re.sub(r"^(Tuyển dụng|Việc làm|Tìm việc làm)\s*", "", clean_title, flags=re.I).strip()

        # Infer company name
        company_name = "Tech Recruiter"
        comp_match = re.search(r"tại\s+([A-Za-z0-9\s]+?)(?:\s+ở|\s+tại|\s+Hà Nội|\s+Hồ Chí Minh|\s*[-–]|$)", raw_title, flags=re.I)
        if comp_match and len(comp_match.group(1).strip()) > 2:
            company_name = comp_match.group(1).strip()
        elif " - " in raw_title:
            parts = raw_title.split(" - ")
            if len(parts) >= 2 and len(parts[-1].strip()) < 30:
                company_name = parts[-1].strip()

        location = "Hà Nội" if "ha noi" in f"{clean_title} {snippet}".lower() else ("Hồ Chí Minh" if "ho chi minh" in f"{clean_title} {snippet}".lower() else "Việt Nam (Hybrid)")

        skills_required, technologies = self.extract_tech_keywords(clean_title, snippet)
        seniority = self.detect_seniority(clean_title, snippet)
        workplace = self.detect_workplace_type(clean_title, location, snippet)
        employment = self.detect_employment_type(clean_title, snippet)

        description = f"Vị trí: {clean_title}.\nYêu cầu công việc & kỹ năng:\n{snippet}\nĐịa điểm làm việc: {location}."
        fingerprint = compute_job_fingerprint(company_name, clean_title, description)

        return {
            "external_job_id": str(uuid.uuid5(uuid.NAMESPACE_URL, link)),
            "source_id": "serper_jobs",
            "company_name": company_name,
            "company_location": location,
            "title": clean_title,
            "location": location,
            "seniority": seniority.value,
            "employment_type": employment.value,
            "workplace_type": workplace.value,
            "raw_description": description,
            "cleaned_jd_text": description,
            "skills_required": skills_required,
            "technologies": technologies,
            "original_apply_url": link,
            "content_fingerprint": fingerprint,
            "via_source": via,
        }
