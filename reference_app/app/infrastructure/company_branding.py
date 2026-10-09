from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx

from ..application.job_aggregator.adapters.company_branding import approved_asset_url, extract_company_branding
from ..application.job_aggregator.adapters.recipe_engine import BROWSER_HEADERS
from ..domain.job_metadata import normalized_text

logger = logging.getLogger(__name__)


class SerperCompanyBrandingLookup:
    def __init__(self, api_key: str = "", redis_client: Any = None, timeout: float = 12.0) -> None:
        self.api_key = api_key
        self.redis = redis_client
        self.timeout = timeout
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}

    async def lookup(self, job: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]:
        policy = recipe.get("company_branding", {})
        company_name = job.get("company_name", "").strip()
        if policy.get("collection_enabled") is not True or not company_name:
            return {}
        extraction_policy = {key: value for key, value in policy.items() if key not in {"reuse_allowed", "license_url"}}
        identity = json.dumps([recipe.get("source_id"), normalized_text(company_name), extraction_policy], sort_keys=True)
        cache_key = "interviewly:company-media:v1:" + sha256(identity.encode()).hexdigest()
        candidates = self._cached(cache_key)
        if candidates is None:
            async with httpx.AsyncClient(timeout=self.timeout, headers=BROWSER_HEADERS) as client:
                candidates = await self._discover(client, job, recipe)
            candidates.update(company_name=company_name, source_id=recipe.get("source_id", ""), checked_at=datetime.now(timezone.utc).isoformat())
            self._store_cache(cache_key, candidates)
        result: dict[str, Any] = {"branding_candidates": candidates}
        license_url = policy.get("license_url", "")
        if policy.get("reuse_allowed") is True and license_url.startswith("https://"):
            media = {key: candidates[key] for key in ("company_logo_url", "company_banner_url", "branding_source_url") if candidates.get(key)}
            if media.get("branding_source_url"):
                result.update(media, branding_reuse_allowed=True, branding_license_url=license_url)
        return result

    def _cached(self, key: str) -> dict[str, Any] | None:
        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            return dict(cached[1])
        if self.redis is not None:
            try:
                value = self.redis.get(key)
                decoded = json.loads(value) if value else None
                if isinstance(decoded, dict):
                    return decoded
            except Exception:
                pass
        return None

    def _store_cache(self, key: str, value: dict[str, Any]) -> None:
        has_media = bool(value.get("company_logo_url") or value.get("company_banner_url"))
        ttl = 7 * 86400 if has_media else 3600
        if len(self._cache) >= 256:
            self._cache.clear()
        self._cache[key] = (time.monotonic() + ttl, dict(value))
        if self.redis is not None:
            try:
                self.redis.set(key, json.dumps(value), ex=ttl)
            except Exception:
                pass

    async def _request(self, client: httpx.AsyncClient, url: str, hosts: list[str], method: str = "GET") -> httpx.Response | None:
        safe_url = approved_asset_url(url, url, hosts)
        for _attempt in range(4):
            if not safe_url:
                return None
            try:
                response = await client.request(method, safe_url, follow_redirects=False)
            except httpx.HTTPError:
                return None
            if response.is_redirect:
                safe_url = approved_asset_url(response.headers.get("location"), safe_url, hosts)
                continue
            if response.status_code != 200:
                return None
            return response
        return None

    def _profile_url(self, value: str, source_url: str, policy: dict[str, Any]) -> str | None:
        value = urljoin(source_url, value)
        parsed = urlparse(value)
        if parsed.scheme == "http" and parsed.hostname in policy.get("allowed_page_hosts", []):
            value = parsed._replace(scheme="https").geturl()
        safe_url = approved_asset_url(value, source_url, policy.get("allowed_page_hosts", []))
        if not safe_url:
            return None
        parsed = urlparse(safe_url)
        pattern = policy.get("company_page_path_pattern")
        if not pattern or not re.fullmatch(pattern, parsed.path):
            return None
        return parsed._replace(query="", fragment="").geturl()

    async def _search_profiles(self, client: httpx.AsyncClient, company_name: str, policy: dict[str, Any]) -> list[str]:
        template = policy.get("serper_query_template")
        if not self.api_key or not template:
            return []
        query = template.format(company_name=company_name.replace('"', " "))
        try:
            response = await client.post("https://google.serper.dev/search", headers={"X-API-KEY": self.api_key}, json={"q": query, "gl": "vn", "hl": "vi", "num": 5})
            if response.status_code != 200:
                return []
            results = response.json().get("organic", [])
        except (httpx.HTTPError, ValueError):
            logger.info("Company-profile discovery unavailable for %s", company_name)
            return []
        urls = []
        for item in results:
            profile = self._profile_url(item.get("link", ""), "", policy)
            if profile and profile not in urls:
                urls.append(profile)
        return urls[:2]

    def _clean_company_name(self, name: str) -> str:
        cleaned = re.sub(
            r"^(CÔNG TY|Công ty|TỔNG CÔNG TY|Tổng công ty|TẬP ĐOÀN)\s+(TNHH\s+MTV|TNHH|CỔ PHẦN|Cổ phần|CP|MTV)\s*",
            "",
            name,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s*[-–]\s*(Chi Nhánh|Chi nhánh|CN).*$", "", cleaned, flags=re.IGNORECASE)
        return cleaned.strip() or name.strip()

    async def _discover(self, client: httpx.AsyncClient, job: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]:
        policy = recipe["company_branding"]
        company_name = job["company_name"]
        source_url = job.get("original_apply_url", "")
        profiles = []
        source_pattern = policy.get("company_url_from_job_pattern")
        if source_pattern:
            match = re.fullmatch(source_pattern, source_url)
            if match:
                profile = self._profile_url(policy["company_url_template"].format(**match.groupdict()), source_url, policy)
                if profile:
                    profiles.append(profile)
        assets: dict[str, Any] = {}
        if not profiles:
            response = await self._request(client, source_url, policy.get("allowed_page_hosts", []))
            if response and len(response.content) <= 1500000 and "html" in response.headers.get("content-type", ""):
                soup = BeautifulSoup(response.text, "html.parser")
                assets = extract_company_branding(soup, str(response.url), company_name, recipe)
                for selector in policy.get("company_link_selectors", []):
                    for link in soup.select(selector):
                        if normalized_text(link.get_text(" ", strip=True)) != normalized_text(company_name):
                            continue
                        profile = self._profile_url(link.get("href", ""), str(response.url), policy)
                        if profile and profile not in profiles:
                            profiles.append(profile)
        visited = set()
        for profile_url in profiles[:2]:
            found = await self._profile_assets(client, profile_url, company_name, recipe)
            visited.add(profile_url)
            if found:
                assets.update(found)
            if assets.get("company_banner_url") and assets.get("company_logo_url"):
                break
        if not assets.get("company_banner_url") and not assets.get("company_logo_url"):
            for profile_url in await self._search_profiles(client, company_name, policy):
                if profile_url in visited:
                    continue
                found = await self._profile_assets(client, profile_url, company_name, recipe)
                if found:
                    assets.update(found)
                    break

        for field in ("company_logo_url", "company_banner_url"):
            if assets.get(field):
                val = assets[field]
                m = re.search(r"https://(static\.topcv\.vn/[^\s\"?]+)", val)
                if m:
                    assets[field] = f"https://{m.group(1)}"
                cand = assets[field].lower()
                response = await self._request(client, assets[field], policy.get("allowed_image_hosts", []), "HEAD")
                ct = response.headers.get("content-type", "").lower() if response else ""
                is_img = ct.startswith("image/") or any(cand.endswith(ext) or (ext + "?") in cand for ext in (".png", ".jpg", ".jpeg", ".webp", ".svg"))
                if not response or not is_img:
                    assets.pop(field, None)
        if not assets.get("company_banner_url") and not assets.get("company_logo_url"):
            return {}
        return assets

    async def _profile_assets(self, client: httpx.AsyncClient, url: str, company_name: str, recipe: dict[str, Any]) -> dict[str, Any]:
        response = await self._request(client, url, recipe["company_branding"].get("allowed_page_hosts", []))
        if not response or len(response.content) > 1500000 or "html" not in response.headers.get("content-type", ""):
            return {}
        return extract_company_branding(BeautifulSoup(response.text, "html.parser"), str(response.url), company_name, recipe, is_company_page=True)
