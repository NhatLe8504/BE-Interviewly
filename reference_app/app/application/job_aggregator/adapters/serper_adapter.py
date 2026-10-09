from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any
import uuid

from bs4 import BeautifulSoup
import httpx

from ....domain.job_aggregator import compute_job_fingerprint
from .base import BaseJobSourceAdapter
from ..ports import CompanyBrandingLookup

logger = logging.getLogger(__name__)

DEFAULT_QUERIES = [
    'site:topcv.vn/viec-lam/ "Java" -tim-viec-lam',
    'site:topcv.vn/viec-lam/ "React" -tim-viec-lam',
    'site:topcv.vn/viec-lam/ "Golang" -tim-viec-lam',
    'site:topcv.vn/viec-lam/ "Python" -tim-viec-lam',
    'site:topcv.vn/viec-lam/ "DevOps" -tim-viec-lam',
    'site:topcv.vn/viec-lam/ "Node" -tim-viec-lam',
    'site:itviec.com/it-jobs/ "Java"',
    'site:itviec.com/it-jobs/ "React"',
    'site:itviec.com/it-jobs/ "Golang"',
    'site:itviec.com/it-jobs/ "Python"',
    'site:itviec.com/it-jobs/ "DevOps"',
]

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
}


def make_deterministic_job_key(source_id: str, company_name: str, job_title: str, external_id: str = "") -> str:
    norm_comp = re.sub(r"[^a-z0-9]", "", company_name.lower())
    norm_title = re.sub(r"[^a-z0-9]", "", job_title.lower())
    norm_extra = re.sub(r"[^a-z0-9]", "", external_id.lower())
    return f"{source_id}:{norm_comp}:{norm_title}:{norm_extra}"


class SerperGoogleJobsAdapter(BaseJobSourceAdapter):
    def __init__(
        self,
        api_key: str,
        timeout: float = 12.0,
        branding_lookup: CompanyBrandingLookup | None = None,
        recipe_registry: Any = None,
    ) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.branding_lookup = branding_lookup
        self.recipe_registry = recipe_registry
        self.endpoint = "https://google.serper.dev/search"

    @staticmethod
    def is_valid_detail_url(url: str) -> bool:
        if not url:
            return False
        # Reject category, search listing or company profile index pages
        if any(bad in url for bad in ["tim-viec-lam", "viec-lam-it", "/cong-ty/", "nha-tuyen-dung", "blog", "tin-tuc"]):
            return False
        # TopCV single job pattern: /viec-lam/{slug}/{id}.html
        if re.search(r"topcv\.vn/viec-lam/[^/]+/\d+\.html", url):
            return True
        # ITviec single job pattern: /it-jobs/{slug}-{id}
        if re.search(r"itviec\.com/it-jobs/[^/]+-\d+", url):
            return True
        return False

    async def fetch_jobs(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        if not self.api_key:
            logger.warning("SERPER_API_KEY is not configured; skipping Serper ingestion.")
            return []

        queries = [query] if query else DEFAULT_QUERIES[:6]
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

        found_links: list[str] = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for q in queries:
                try:
                    resp = await client.post(
                        self.endpoint,
                        headers=headers,
                        json={"q": q, "gl": "vn", "hl": "vi", "num": 10},
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    for item in data.get("organic", []):
                        link = item.get("link", "").strip()
                        if self.is_valid_detail_url(link) and link not in found_links:
                            found_links.append(link)
                            if len(found_links) >= limit * 2:
                                break
                except Exception as exc:
                    logger.warning("Failed querying Serper for query '%s': %s", q, exc)
                if len(found_links) >= limit * 2:
                    break

        if not found_links:
            logger.info("No direct individual job links found from Serper search.")
            return []

        # Step 2: Concurrently crawl detail pages
        results: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=8.0, headers=BROWSER_HEADERS, follow_redirects=True) as crawler_client:
            tasks = [self._crawl_single_job(crawler_client, link) for link in found_links[:limit]]
            crawl_outputs = await asyncio.gather(*tasks, return_exceptions=True)
            for out in crawl_outputs:
                if isinstance(out, dict) and out:
                    results.append(out)

        if self.branding_lookup and self.recipe_registry:
            for job in results:
                sid = job.get("source_id", "")
                recipe = self.recipe_registry.get(sid)
                if recipe:
                    try:
                        assets = await self.branding_lookup.lookup(job, recipe)
                        if assets:
                            job.update(assets)
                    except Exception as exc:
                        logger.debug("Failed branding lookup for Serper job %s: %s", job.get("title"), exc)

        logger.info("Successfully crawled %d individual jobs with full JD details", len(results))
        return results

    async def _crawl_single_job(self, client: httpx.AsyncClient, url: str) -> dict[str, Any] | None:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None

            if "topcv.vn" in url:
                return self._parse_topcv_page(url, resp.text)
            elif "itviec.com" in url:
                return self._parse_itviec_page(url, resp.text)
            return None
        except Exception as exc:
            logger.debug("Failed crawling single job detail %s: %s", url, exc)
            return None

    def _parse_topcv_page(self, url: str, html_text: str) -> dict[str, Any] | None:
        soup = BeautifulSoup(html_text, "html.parser")

        # 1. Title
        h1 = soup.find("h1")
        if not h1:
            return None
        raw_title = h1.get_text(strip=True)
        title = re.sub(r"^(Tuyển\s+|Tuyển\s+dụng\s+|[\[\(].*?[\]\)]\s*)", "", raw_title, flags=re.I).strip()
        if not title or len(title) < 4 or "việc làm" in title.lower():
            return None

        # 2. Company Name
        company_name = ""
        for a in soup.find_all("a", href=lambda h: h and "/cong-ty/" in h):
            txt = a.get_text(strip=True)
            if txt and "{{" not in txt and "Xem trang" not in txt and "TopCV" not in txt and len(txt) > 2:
                company_name = txt
                break
        if not company_name:
            company_name = "Doanh nghiệp IT"

        # 3. External Job ID from URL (e.g. 2193376)
        id_match = re.search(r"/(\d+)\.html", url)
        external_id = id_match.group(1) if id_match else str(uuid.uuid5(uuid.NAMESPACE_URL, url))

        # 4. Salary
        salary = "Thỏa thuận"
        sal_el = soup.find(class_=lambda c: c and "salary" in c)
        if sal_el:
            salary = re.sub(r"Xem mức lương.*$", "", sal_el.get_text(strip=True)).strip()

        # 5. Extract Detailed Sections
        mota, yeucau, quyenloi = "", "", ""
        for item in soup.find_all(class_=lambda c: c and "box-job-information-detail-item" in c):
            title_el = item.find(class_=lambda c: c and "title" in c)
            text_el = item.find(class_=lambda c: c and "text" in c)
            if title_el and text_el:
                t = title_el.get_text(strip=True).lower()
                content = text_el.get_text("\n", strip=True)
                if "mô tả" in t and not mota:
                    mota = content
                elif "yêu cầu" in t and not yeucau:
                    yeucau = content
                elif "quyền lợi" in t and not quyenloi:
                    quyenloi = content

        if not mota and not yeucau:
            return None

        jd_text = f"### 1. Mô tả công việc (Job Description)\n{mota}\n\n### 2. Yêu cầu ứng viên (Requirements & Skills)\n{yeucau}\n\n### 3. Quyền lợi được hưởng (Benefits)\n{quyenloi}"

        # 6. Location
        location = "Hà Nội"
        if "hồ chí minh" in html_text.lower() or "tp hcm" in html_text.lower() or "quận " in html_text.lower():
            location = "Hồ Chí Minh City"
        elif "đà nẵng" in html_text.lower():
            location = "Đà Nẵng"

        skills_required, technologies = self.extract_tech_keywords(title, jd_text)
        seniority = self.detect_seniority(title, jd_text)
        workplace = self.detect_workplace_type(title, location, jd_text)
        employment = self.detect_employment_type(title, jd_text)

        # 7. Deterministic key & fingerprint
        key = make_deterministic_job_key("topcv", company_name, title, external_id)
        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()

        return {
            "external_job_id": external_id,
            "source_id": "topcv",
            "company_name": company_name,
            "company_location": location,
            "title": title,
            "location": location,
            "seniority": seniority.value,
            "employment_type": employment.value,
            "workplace_type": workplace.value,
            "raw_description": jd_text,
            "cleaned_jd_text": jd_text,
            "skills_required": skills_required,
            "technologies": technologies,
            "original_apply_url": url,
            "content_fingerprint": fingerprint,
            "via_source": "via TopCV",
        }

    def _parse_itviec_page(self, url: str, html_text: str) -> dict[str, Any] | None:
        soup = BeautifulSoup(html_text, "html.parser")

        # 1. Title
        h1 = soup.find("h1")
        if not h1:
            return None
        title = h1.get_text(strip=True)
        if not title or len(title) < 4 or "jobs in viet nam" in title.lower():
            return None

        # 2. Company Name
        comp_el = soup.find(class_=lambda c: c and "employer-name" in c)
        company_name = comp_el.get_text(strip=True) if comp_el else "Nhà tuyển dụng IT"

        # 3. External Job ID from URL
        id_match = re.search(r"-(\d+)$", url)
        external_id = id_match.group(1) if id_match else str(uuid.uuid5(uuid.NAMESPACE_URL, url))

        # 4. Description Content
        paragraphs: list[str] = []
        for p in soup.find_all("div", class_=lambda c: c and "paragraph" in c):
            txt = p.get_text("\n", strip=True)
            if len(txt) > 50:
                paragraphs.append(txt)

        jd_text = "\n\n".join(paragraphs) if paragraphs else title
        if len(jd_text) < 100:
            return None

        location = "Hồ Chí Minh City" if "ho chi minh" in html_text.lower() else ("Hà Nội" if "ha noi" in html_text.lower() else "Việt Nam (Hybrid)")

        skills_required, technologies = self.extract_tech_keywords(title, jd_text)
        seniority = self.detect_seniority(title, jd_text)
        workplace = self.detect_workplace_type(title, location, jd_text)
        employment = self.detect_employment_type(title, jd_text)

        key = make_deterministic_job_key("itviec", company_name, title, external_id)
        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()

        return {
            "external_job_id": external_id,
            "source_id": "itviec",
            "company_name": company_name,
            "company_location": location,
            "title": title,
            "location": location,
            "seniority": seniority.value,
            "employment_type": employment.value,
            "workplace_type": workplace.value,
            "raw_description": jd_text,
            "cleaned_jd_text": jd_text,
            "skills_required": skills_required,
            "technologies": technologies,
            "original_apply_url": url,
            "content_fingerprint": fingerprint,
            "via_source": "via ITviec",
        }
