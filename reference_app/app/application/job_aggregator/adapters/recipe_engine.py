from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
import re
from typing import Any
import uuid
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import httpx

from ....domain.job_aggregator import compute_job_fingerprint
from .base import BaseJobSourceAdapter
from .company_branding import collect_company_branding, job_structured_data, page_job_metadata
from ..ports import CompanyBrandingLookup

logger = logging.getLogger(__name__)

RECIPES_DIR = Path(__file__).parent.parent / "recipes"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
}

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
}


NON_IT_KEYWORDS = [
    "accountant", "accounting", "accounts payable", "accounts receivable",
    "clerk", "cashier", "receptionist", "secretary", "office administrator",
    "sales executive", "sales representative", "telesales", "bán hàng",
    "hr manager", "hr business partner", "recruiter", "talent acquisition", "tuyển dụng nhân sự",
    "nhân viên hành chính", "kế toán", "thu ngân", "nhân viên kinh doanh",
    "legal counsel", "pháp chế", "lái xe", "bảo vệ", "tạp vụ", "đầu bếp",
    "cook", "driver", "security guard", "customer service agent", "chăm sóc khách hàng",
    "fpa executive", "fp&a", "cash loan", "thai localization",
]

POSITIVE_IT_KEYWORDS = [
    "software", "engineer", "developer", "programmer", "architect",
    "backend", "frontend", "front-end", "fullstack", "full-stack",
    "devops", "sre", "cloud", "platform", "infrastructure", "system",
    "data engineer", "data analyst", "data scientist", "bi analyst",
    "ai", "machine learning", "ml", "deep learning", "nlp", "llm", "computer vision",
    "qa", "qc", "tester", "test automation", "automation engineer",
    "security engineer", "cybersecurity", "soc",
    "mobile", "android", "ios", "flutter", "react native",
    "java", "python", "golang", "go", "c#", ".net", "c++", "rust", "php", "node", "nodejs",
    "react", "vue", "angular", "nextjs", "typescript", "javascript",
    "database administrator", "dba", "embedded", "firmware", "iot",
    "it specialist", "it support", "it helpdesk", "network engineer",
    "scrum master", "product owner", "tech lead", "engineering manager",
]


def is_relevant_it_job(title: str, text: str = "", location: str = "") -> bool:
    title_lower = title.lower()

    # Reject explicit non-IT titles
    for bad in NON_IT_KEYWORDS:
        if bad in title_lower:
            return False

    # Check positive technical keywords in title or summary
    has_it_title = any(kw in title_lower for kw in POSITIVE_IT_KEYWORDS)
    if not has_it_title:
        text_lower = text[:500].lower()
        if not any(kw in text_lower for kw in ["software", "programming", "lập trình", "source code", "git", "api", "database"]):
            return False

    # Check location constraints: exclude overseas-only on-site offices
    loc_lower = location.lower()
    if "office based" in loc_lower and not any(vn in loc_lower for vn in ["vietnam", "viet nam", "hanoi", "ha noi", "ho chi minh", "hcm", "da nang"]):
        if "remote" not in loc_lower and "worldwide" not in loc_lower:
            return False

    return True


def make_deterministic_job_key(source_id: str, company_name: str, job_title: str, external_id: str = "") -> str:
    norm_comp = re.sub(r"[^a-z0-9]", "", company_name.lower())
    norm_title = re.sub(r"[^a-z0-9]", "", job_title.lower())
    norm_extra = re.sub(r"[^a-z0-9]", "", external_id.lower())
    return f"{source_id}:{norm_comp}:{norm_title}:{norm_extra}"


class DomainRecipeRegistry:
    _instance = None
    _recipes: dict[str, dict[str, Any]] = {}

    def __init__(self, recipes_dir: Path | None = None) -> None:
        self.recipes_dir = recipes_dir or RECIPES_DIR
        self.reload_recipes()

    def reload_recipes(self) -> None:
        self._recipes.clear()
        if not self.recipes_dir.exists():
            return
        for file in self.recipes_dir.glob("*.json"):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                sid = data.get("source_id") or file.stem
                self._recipes[sid] = data
            except Exception as exc:
                logger.warning("Failed loading recipe %s: %s", file.name, exc)

    def get(self, source_id: str) -> dict[str, Any] | None:
        return self._recipes.get(source_id)

    def list_all(self) -> list[dict[str, Any]]:
        return list(self._recipes.values())

    def list_verified(self) -> list[dict[str, Any]]:
        return [r for r in self._recipes.values() if r.get("verification_status") in ("VERIFIED", "PARTIAL")]


class RecipeBasedCrawlerAdapter(BaseJobSourceAdapter):
    def __init__(
        self,
        registry: DomainRecipeRegistry | None = None,
        branding_lookup: CompanyBrandingLookup | None = None,
        timeout: float = 12.0,
    ) -> None:
        self.registry = registry or DomainRecipeRegistry()
        self.branding_lookup = branding_lookup
        self.timeout = timeout

    async def fetch_jobs(self, query: str = "", limit: int = 20) -> list[dict[str, Any]]:
        verified = self.registry.list_verified()
        if not verified:
            return []

        all_results: list[dict[str, Any]] = []
        per_source_limit = max(3, limit // max(1, len(verified)))

        for recipe in verified:
            sid = recipe.get("source_id")
            try:
                if sid == "topcv":
                    jobs = await self._crawl_topcv(recipe, limit=per_source_limit)
                elif sid == "itviec":
                    jobs = await self._crawl_itviec(recipe, limit=per_source_limit)
                elif sid == "vietnamworks":
                    jobs = await self._crawl_vietnamworks(recipe, query=query or "developer", limit=per_source_limit)
                elif sid == "vng":
                    jobs = await self._crawl_vng(recipe, limit=per_source_limit)
                elif sid == "greenhouse":
                    jobs = await self._crawl_greenhouse(recipe, limit=per_source_limit)
                elif sid == "lever":
                    jobs = await self._crawl_lever(recipe, limit=per_source_limit)
                elif sid == "linkedin":
                    jobs = await self._crawl_linkedin(recipe, query=query or "Software Engineer", limit=min(4, per_source_limit))
                else:
                    jobs = []
                valid_it_jobs = [
                    j for j in jobs
                    if is_relevant_it_job(j.get("title", ""), j.get("cleaned_jd_text", ""), j.get("location", ""))
                    and len(j.get("cleaned_jd_text", "")) >= 150
                ]
                await self._enrich_company_branding(valid_it_jobs, recipe)
                all_results.extend(valid_it_jobs)
            except Exception as exc:
                logger.warning("Error crawling source %s with recipe: %s", sid, exc)

        return all_results[:limit]

    async def _enrich_company_branding(self, jobs: list[dict[str, Any]], recipe: dict[str, Any]) -> None:
        policy = recipe.get("company_branding", {})
        if policy.get("collection_enabled") is not True and policy.get("reuse_allowed") is not True:
            return
        company_assets: dict[str, dict[str, Any]] = {}
        for job in jobs:
            company_name = job.get("company_name", "").strip()
            if not company_name:
                continue
            if job.get("company_banner_url") and job.get("company_logo_url"):
                continue
            if company_name not in company_assets:
                company_assets[company_name] = {}
                if self.branding_lookup is not None:
                    try:
                        company_assets[company_name] = await self.branding_lookup.lookup(job, recipe)
                    except Exception as exc:
                        logger.debug("Failed branding lookup for %s: %s", company_name, exc)
                elif policy.get("reuse_allowed") is True:
                    source_url = job.get("original_apply_url", "")
                    allowed_hosts = set(policy.get("allowed_page_hosts", []))
                    if urlparse(source_url).hostname in allowed_hosts:
                        try:
                            async with httpx.AsyncClient(timeout=self.timeout, headers=BROWSER_HEADERS) as client:
                                response = await client.get(source_url)
                                if response.status_code == 200:
                                    company_assets[company_name] = collect_company_branding(
                                        BeautifulSoup(response.text, "html.parser"), source_url, company_name, recipe,
                                    )
                        except httpx.HTTPError:
                            pass
            if company_assets.get(company_name):
                job.update(company_assets[company_name])

    async def _crawl_topcv(self, recipe: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        urls = recipe.get("listing", {}).get("default_urls", [])
        if not urls:
            return []
        target_url = urls[0]

        async with httpx.AsyncClient(timeout=self.timeout, headers=BROWSER_HEADERS, follow_redirects=True) as client:
            resp = await client.get(target_url)
            if resp.status_code != 200:
                return []

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(recipe.get("listing", {}).get("card_selector", ".job-item-search-result"))
            
            detail_links: list[tuple[str, str, str]] = []
            for card in cards:
                title_el = card.select_one(recipe.get("listing", {}).get("fields", {}).get("title", {}).get("selector", "h3.title a"))
                comp_el = card.select_one("a.company, a[href*='/cong-ty/']")
                if not title_el or not title_el.get("href"):
                    continue
                href = title_el.get("href").strip().split("?")[0]
                m = re.search(r"/(\d+)\.html", href)
                if not m:
                    continue
                jid = m.group(1)
                t = title_el.get_text(strip=True)
                c = comp_el.get_text(strip=True) if comp_el else "Doanh nghiệp IT"
                detail_links.append((jid, t, href))
                if len(detail_links) >= limit:
                    break

            for jid, orig_title, durl in detail_links:
                try:
                    await asyncio.sleep(0.3)
                    det_resp = await client.get(durl)
                    if det_resp.status_code != 200:
                        continue
                    dsoup = BeautifulSoup(det_resp.text, "html.parser")
                    h1 = dsoup.find("h1")
                    title = h1.get_text(strip=True) if h1 else orig_title
                    title = re.sub(r"^(Tuyển\s+|Tuyển\s+dụng\s+|[\[\(].*?[\]\)]\s*)", "", title, flags=re.I).strip()
                    
                    comp_name = ""
                    for c_sel in recipe.get("detail", {}).get("fields", {}).get("company", {}).get("selectors", [".name-company"]):
                        found = dsoup.select_one(c_sel)
                        if found and found.get_text(strip=True):
                            comp_name = found.get_text(strip=True)
                            break
                    if not comp_name:
                        comp_name = (job_structured_data(dsoup).get("hiringOrganization") or {}).get("name", "")
                    if not comp_name:
                        continue

                    sections: list[str] = []
                    for item in dsoup.select(recipe.get("detail", {}).get("fields", {}).get("sections", {}).get("container_selector", ".box-job-information-detail-item")):
                        title_el = item.select_one(".title, h3")
                        text_el = item.select_one(".text")
                        if title_el and text_el:
                            sections.append(f"### {title_el.get_text(strip=True)}\n{text_el.get_text('\n', strip=True)}")
                    jd_text = "\n\n".join(sections)
                    if len(jd_text) < 150:
                        continue

                    skills, techs = self.extract_tech_keywords(title, jd_text)
                    key = make_deterministic_job_key("topcv", comp_name, title, jid)
                    fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()

                    results.append({
                        "external_job_id": jid,
                        "source_id": "topcv",
                        "company_name": comp_name,
                        "company_location": None,
                        "title": title,
                        "location": None,
                        "seniority": self.detect_seniority(title, jd_text).value,
                        "employment_type": self.detect_employment_type(title, jd_text).value,
                        "workplace_type": self.detect_workplace_type(title, text=jd_text).value,
                        "raw_description": jd_text,
                        "cleaned_jd_text": jd_text,
                        "skills_required": skills,
                        "technologies": techs,
                        "original_apply_url": durl,
                        "content_fingerprint": fingerprint,
                        "via_source": "via TopCV",
                        **page_job_metadata(dsoup, durl, comp_name, recipe),
                    })
                except Exception as exc:
                    logger.debug("Failed topcv single job detail %s: %s", durl, exc)

        return results

    async def _crawl_itviec(self, recipe: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        urls = recipe.get("listing", {}).get("default_urls", [])
        if not urls:
            return []
        listing_url = urls[0]

        async with httpx.AsyncClient(timeout=self.timeout, headers=BROWSER_HEADERS, follow_redirects=True) as client:
            resp = await client.get(listing_url)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(recipe.get("listing", {}).get("card_selector", ".job-card"))
            
            slugs: list[tuple[str, str, str]] = []
            for card in cards:
                slug = card.get("data-search--job-selection-job-slug-value")
                jkey = card.get("data-job-key") or slug
                t_el = card.select_one("h3 a, .job-card__title a")
                if not slug and t_el and t_el.get("href"):
                    m = re.search(r"/it-jobs/([^/?]+)", t_el.get("href"))
                    if m:
                        slug = m.group(1)
                if not slug:
                    continue
                title = t_el.get_text(strip=True) if t_el else slug
                slugs.append((jkey, slug, title))
                if len(slugs) >= limit:
                    break

            for jkey, slug, orig_title in slugs:
                durl = f"https://itviec.com/it-jobs/{slug}"
                try:
                    await asyncio.sleep(0.3)
                    det_resp = await client.get(durl)
                    if det_resp.status_code != 200:
                        continue
                    dsoup = BeautifulSoup(det_resp.text, "html.parser")
                    h1 = dsoup.find("h1")
                    title = h1.get_text(strip=True) if h1 else orig_title
                    comp_el = dsoup.select_one(".employer-name, .company-name")
                    comp_name = comp_el.get_text(strip=True) if comp_el else (job_structured_data(dsoup).get("hiringOrganization") or {}).get("name", "")
                    if not comp_name:
                        continue
                    
                    paragraphs = dsoup.select(".job-details__paragraph, .paragraph")
                    jd_text = "\n\n".join(p.get_text("\n", strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
                    if len(jd_text) < 150:
                        continue

                    skills, techs = self.extract_tech_keywords(title, jd_text)
                    key = make_deterministic_job_key("itviec", comp_name, title, slug)
                    fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()

                    results.append({
                        "external_job_id": slug,
                        "source_id": "itviec",
                        "company_name": comp_name,
                        "company_location": None,
                        "title": title,
                        "location": None,
                        "seniority": self.detect_seniority(title, jd_text).value,
                        "employment_type": self.detect_employment_type(title, jd_text).value,
                        "workplace_type": self.detect_workplace_type(title, text=jd_text).value,
                        "raw_description": jd_text,
                        "cleaned_jd_text": jd_text,
                        "skills_required": skills,
                        "technologies": techs,
                        "original_apply_url": durl,
                        "content_fingerprint": fingerprint,
                        "via_source": "via ITviec",
                        **page_job_metadata(dsoup, durl, comp_name, recipe),
                    })
                except Exception as exc:
                    logger.debug("Failed itviec detail %s: %s", durl, exc)

        return results

    async def _crawl_vietnamworks(self, recipe: dict[str, Any], query: str = "developer", limit: int = 5) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        api_cfg = recipe.get("listing", {}).get("search_api", {})
        api_url = api_cfg.get("url", "https://ms.vietnamworks.com/job-search/v1.0/search")
        payload = {
            "userId": 0,
            "query": query,
            "filter": [],
            "ranges": [],
            "order": [],
            "hitsPerPage": limit,
            "page": 0,
        }

        async with httpx.AsyncClient(timeout=self.timeout, headers=API_HEADERS) as client:
            try:
                resp = await client.post(api_url, json=payload)
                if resp.status_code != 200:
                    return []
                data = resp.json()
                jobs = data.get("data", [])
            except Exception as exc:
                logger.warning("Vietnamworks search api error: %s", exc)
                return []

            for job in jobs[:limit]:
                jid = str(job.get("jobId", ""))
                title = job.get("jobTitle", "")
                comp = job.get("companyName", "Doanh nghiệp VietnamWorks")
                durl = job.get("jobUrl", "")
                logo = job.get("companyLogo", "")
                if not durl:
                    continue

                try:
                    await asyncio.sleep(0.3)
                    det_resp = await client.get(durl, headers=BROWSER_HEADERS)
                    if det_resp.status_code != 200:
                        continue
                    html_content = det_resp.text

                    # Extract Description
                    desc = ""
                    m_desc = re.search(r'jobDescription\\":\\"((?:(?!\\",\\").)*)\\"', html_content)
                    if m_desc:
                        raw = m_desc.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
                        desc = BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)

                    # Extract Requirements
                    req = ""
                    m_req_ptr = re.search(r'jobRequirement\\":\\"\$([a-zA-Z0-9]+)\\"', html_content)
                    if m_req_ptr:
                        ptr_id = m_req_ptr.group(1)
                        m_ptr_content = re.search(rf'{ptr_id}:T[0-9a-f]+,(.*?)(?:\\\\n|\",\[|$)', html_content)
                        if m_ptr_content:
                            raw_req = m_ptr_content.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
                            req = BeautifulSoup(raw_req, "html.parser").get_text("\n", strip=True)
                    if not req:
                        m_req = re.search(r'jobRequirement\\":\\"((?:(?!\\",\\").)*)\\"', html_content)
                        if m_req and not m_req.group(1).startswith("$"):
                            raw = m_req.group(1).encode("utf-8").decode("unicode_escape", errors="ignore")
                            req = BeautifulSoup(raw, "html.parser").get_text("\n", strip=True)

                    jd_text = f"### Mô tả công việc\n{desc}\n\n### Yêu cầu ứng viên\n{req}".strip()
                    if len(jd_text) < 150:
                        continue

                    skills, techs = self.extract_tech_keywords(title, jd_text)
                    key = make_deterministic_job_key("vietnamworks", comp, title, jid)
                    fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()

                    results.append({
                        "external_job_id": jid,
                        "source_id": "vietnamworks",
                        "company_name": comp,
                        "company_location": None,
                        "title": title,
                        "location": None,
                        "seniority": self.detect_seniority(title, jd_text).value,
                        "employment_type": self.detect_employment_type(title, jd_text).value,
                        "workplace_type": self.detect_workplace_type(title, text=jd_text).value,
                        "raw_description": jd_text,
                        "cleaned_jd_text": jd_text,
                        "skills_required": skills,
                        "technologies": techs,
                        "original_apply_url": durl,
                        "content_fingerprint": fingerprint,
                        "via_source": "via VietnamWorks",
                        **page_job_metadata(BeautifulSoup(html_content, "html.parser"), durl, comp, recipe),
                    })
                except Exception as exc:
                    logger.debug("Vietnamworks detail error %s: %s", durl, exc)

        return results

    async def _crawl_vng(self, recipe: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        urls = recipe.get("listing", {}).get("default_urls", [])
        if not urls:
            return []
        url = urls[0]

        async with httpx.AsyncClient(timeout=self.timeout, headers=BROWSER_HEADERS, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            nd = soup.find("script", id="__NEXT_DATA__")
            if not nd or not nd.string:
                return []
            data = json.loads(nd.string)
            jobs = data.get("props", {}).get("pageProps", {}).get("jobs", [])

            for job in jobs[:limit]:
                slug = job.get("slug")
                orig_title = job.get("title", "")
                if not slug:
                    continue
                durl = f"https://career.vng.com.vn/tim-kiem-viec-lam/chi-tiet/{slug}"
                try:
                    await asyncio.sleep(0.3)
                    det_resp = await client.get(durl)
                    if det_resp.status_code != 200:
                        continue
                    dsoup = BeautifulSoup(det_resp.text, "html.parser")
                    dnd = dsoup.find("script", id="__NEXT_DATA__")
                    if not dnd or not dnd.string:
                        continue
                    ddata = json.loads(dnd.string)
                    jdata = ddata.get("props", {}).get("pageProps", {}).get("job_data", {})
                    title = jdata.get("title") or orig_title
                    jid = str(jdata.get("job_id") or slug)
                    loc = jdata.get("location") or ""

                    desc_text = BeautifulSoup(jdata.get("description", ""), "html.parser").get_text("\n", strip=True)
                    req_text = BeautifulSoup(jdata.get("requirement", ""), "html.parser").get_text("\n", strip=True)
                    jd_text = f"### Mô tả công việc\n{desc_text}\n\n### Yêu cầu ứng viên\n{req_text}".strip()

                    if len(jd_text) < 150:
                        continue

                    skills, techs = self.extract_tech_keywords(title, jd_text)
                    key = make_deterministic_job_key("vng", "VNG Corporation", title, jid)
                    fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()

                    results.append({
                        "external_job_id": jid,
                        "source_id": "vng",
                        "company_name": "VNG Corporation",
                        "company_location": loc,
                        "title": title,
                        "location": loc,
                        "seniority": self.detect_seniority(title, jd_text).value,
                        "employment_type": self.detect_employment_type(title, jd_text).value,
                        "workplace_type": self.detect_workplace_type(title, loc, jd_text).value,
                        "raw_description": jd_text,
                        "cleaned_jd_text": jd_text,
                        "skills_required": skills,
                        "technologies": techs,
                        "original_apply_url": durl,
                        "content_fingerprint": fingerprint,
                        "via_source": "via VNG Careers",
                    })
                except Exception as exc:
                    logger.debug("VNG detail error %s: %s", durl, exc)

        return results

    async def _crawl_greenhouse(self, recipe: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        boards = ["canonical"]
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for b in boards:
                url = f"https://boards-api.greenhouse.io/v1/boards/{b}/jobs?content=true"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    jobs = resp.json().get("jobs", [])
                    for j in jobs:
                        jid = str(j.get("id"))
                        title = j.get("title", "")
                        loc = j.get("location", {}).get("name", "")
                        if not is_relevant_it_job(title, "", loc):
                            continue
                        apply_url = j.get("absolute_url", "")
                        clean_jd = BeautifulSoup(j.get("content", ""), "html.parser").get_text("\n", strip=True)
                        if len(clean_jd) < 150:
                            continue

                        skills, techs = self.extract_tech_keywords(title, clean_jd)
                        key = make_deterministic_job_key("greenhouse", b.title(), title, jid)
                        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()

                        results.append({
                            "external_job_id": jid,
                            "source_id": "greenhouse",
                            "company_name": b.title(),
                            "company_location": loc,
                            "title": title,
                            "location": loc,
                            "seniority": self.detect_seniority(title, clean_jd).value,
                            "employment_type": self.detect_employment_type(title, clean_jd).value,
                            "workplace_type": self.detect_workplace_type(title, loc, clean_jd).value,
                            "raw_description": clean_jd,
                            "cleaned_jd_text": clean_jd,
                            "skills_required": skills,
                            "technologies": techs,
                            "original_apply_url": apply_url,
                            "content_fingerprint": fingerprint,
                            "via_source": "via Greenhouse",
                        })
                        if len(results) >= limit:
                            break
                except Exception as exc:
                    logger.debug("Greenhouse error %s: %s", b, exc)
        return results

    async def _crawl_lever(self, recipe: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        companies = ["palantir"]
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for c in companies:
                url = f"https://api.lever.co/v0/postings/{c}?mode=json"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    jobs = resp.json()
                    for j in jobs:
                        jid = str(j.get("id"))
                        title = j.get("text", "")
                        hosted_url = j.get("hostedUrl", "")
                        loc = j.get("categories", {}).get("location", "")
                        if not is_relevant_it_job(title, "", loc):
                            continue
                        desc_plain = j.get("descriptionPlain", "")
                        lists_text = ""
                        for lst in j.get("lists", []):
                            lists_text += f"\n\n### {lst.get('text', '')}\n" + BeautifulSoup(lst.get("content", ""), "html.parser").get_text("\n", strip=True)
                        full_jd = (desc_plain + lists_text).strip()
                        if len(full_jd) < 150:
                            continue

                        skills, techs = self.extract_tech_keywords(title, full_jd)
                        key = make_deterministic_job_key("lever", c.title(), title, jid)
                        fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()

                        results.append({
                            "external_job_id": jid,
                            "source_id": "lever",
                            "company_name": c.title(),
                            "company_location": loc,
                            "title": title,
                            "location": loc,
                            "seniority": self.detect_seniority(title, full_jd).value,
                            "employment_type": self.detect_employment_type(title, full_jd).value,
                            "workplace_type": self.detect_workplace_type(title, loc, full_jd).value,
                            "raw_description": full_jd,
                            "cleaned_jd_text": full_jd,
                            "skills_required": skills,
                            "technologies": techs,
                            "original_apply_url": hosted_url,
                            "content_fingerprint": fingerprint,
                            "via_source": "via Lever",
                            "posted_at": j.get("createdAt"),
                        })
                except Exception as exc:
                    logger.debug("Lever error %s: %s", c, exc)
        return results

    async def _crawl_linkedin(self, recipe: dict[str, Any], query: str = "Software Engineer", limit: int = 3) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={query}&location=Vietnam&start=0"
        async with httpx.AsyncClient(timeout=self.timeout, headers=BROWSER_HEADERS, follow_redirects=True) as client:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return []
                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("li")
                jobs_to_fetch = []
                for c in cards:
                    div_card = c.select_one("div[data-entity-urn]")
                    link_el = c.select_one("a.base-card__full-link, a")
                    t_el = c.select_one("h3.base-search-card__title, .job-search-card__title")
                    comp_el = c.select_one("h4.base-search-card__subtitle, a.hidden-nested-link")
                    jid = None
                    if div_card and div_card.get("data-entity-urn"):
                        m = re.search(r"jobPosting:(\d+)", div_card["data-entity-urn"])
                        if m:
                            jid = m.group(1)
                    if not jid:
                        continue
                    jobs_to_fetch.append((jid, t_el.get_text(strip=True) if t_el else "", comp_el.get_text(strip=True) if comp_el else "Unknown"))
                    if len(jobs_to_fetch) >= limit:
                        break

                for jid, orig_title, orig_comp in jobs_to_fetch:
                    await asyncio.sleep(1.2)  # Respect rate-limit delay
                    det_url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{jid}"
                    det_resp = await client.get(det_url)
                    if det_resp.status_code != 200:
                        continue
                    dsoup = BeautifulSoup(det_resp.text, "html.parser")
                    h1 = dsoup.find("h1") or dsoup.find("h2")
                    title = h1.get_text(strip=True) if h1 else orig_title
                    comp_el = dsoup.select_one("a.topcard__org-name-link, .topcard__flavor")
                    comp = comp_el.get_text(strip=True) if comp_el else orig_comp
                    desc_el = dsoup.select_one(".show-more-less-html__markup, .description__text")
                    jd_text = desc_el.get_text("\n", strip=True) if desc_el else ""
                    if len(jd_text) < 150:
                        continue

                    skills, techs = self.extract_tech_keywords(title, jd_text)
                    key = make_deterministic_job_key("linkedin", comp, title, jid)
                    fingerprint = hashlib.sha256(key.encode("utf-8")).hexdigest()

                    results.append({
                        "external_job_id": jid,
                        "source_id": "linkedin",
                        "company_name": comp,
                        "company_location": None,
                        "title": title,
                        "location": (dsoup.select_one(".topcard__flavor--bullet").get_text(" ", strip=True) if dsoup.select_one(".topcard__flavor--bullet") else None),
                        "seniority": self.detect_seniority(title, jd_text).value,
                        "employment_type": self.detect_employment_type(title, jd_text).value,
                        "workplace_type": self.detect_workplace_type(title, text=jd_text).value,
                        "raw_description": jd_text,
                        "cleaned_jd_text": jd_text,
                        "skills_required": skills,
                        "technologies": techs,
                        "original_apply_url": f"https://www.linkedin.com/jobs/view/{jid}",
                        "content_fingerprint": fingerprint,
                        "via_source": "via LinkedIn",
                        **page_job_metadata(dsoup, f"https://www.linkedin.com/jobs/view/{jid}", comp, recipe),
                    })
            except Exception as exc:
                logger.debug("LinkedIn guest error: %s", exc)
        return results
