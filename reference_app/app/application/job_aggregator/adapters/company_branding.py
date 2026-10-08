from __future__ import annotations

import json
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ....domain.job_metadata import normalized_text, parse_source_datetime


def job_structured_data(soup: BeautifulSoup) -> dict[str, Any]:
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            payload = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        while nodes:
            node = nodes.pop(0)
            if not isinstance(node, dict):
                continue
            node_types = node.get("@type", [])
            if "JobPosting" in (node_types if isinstance(node_types, list) else [node_types]):
                return node
            nodes.extend(node.get("@graph", []))
    return {}


def approved_asset_url(value: Any, source_url: str, allowed_hosts: list[str]) -> str | None:
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    if not isinstance(value, str) or not value.strip():
        return None
    url = urljoin(source_url, value.strip())
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username or parsed.password:
        return None
    return url


def collect_company_branding(
    soup: BeautifulSoup, source_url: str, company_name: str, recipe: dict[str, Any]
) -> dict[str, Any]:
    policy = recipe.get("company_branding", {})
    license_url = policy.get("license_url", "")
    if policy.get("reuse_allowed") is not True or not license_url.startswith("https://"):
        return {}
    posting = job_structured_data(soup)
    organization = posting.get("hiringOrganization") or {}
    if not isinstance(organization, dict):
        return {}
    organization_name = organization.get("name", "")
    if not organization_name:
        selector = policy.get("company_name_selector")
        company_heading = soup.select_one(selector) if selector else None
        organization_name = company_heading.get_text(" ", strip=True) if company_heading else ""
    if normalized_text(organization_name.strip()) != normalized_text(company_name.strip()):
        return {}
    allowed_hosts = policy.get("allowed_image_hosts", [])
    result: dict[str, Any] = {}
    logo_url = approved_asset_url(organization.get("logo"), source_url, allowed_hosts)
    if logo_url:
        result["company_logo_url"] = logo_url
    for field, selectors in (
        ("company_logo_url", policy.get("logo_selectors", [])),
        ("company_banner_url", policy.get("banner_selectors", [])),
    ):
        for selector in selectors:
            image = soup.select_one(selector)
            if not image:
                continue
            candidate = approved_asset_url(image.get("src") or image.get("data-src"), source_url, allowed_hosts)
            if candidate:
                result[field] = candidate
                break
    if result:
        result.update(
            branding_reuse_allowed=True, branding_source_url=source_url,
            branding_license_url=license_url,
        )
    return result


def page_job_metadata(
    soup: BeautifulSoup, source_url: str, company_name: str, recipe: dict[str, Any]
) -> dict[str, Any]:
    posting = job_structured_data(soup)
    result = collect_company_branding(soup, source_url, company_name, recipe)
    for source_field, field in (("datePosted", "posted_at"), ("validThrough", "expires_at")):
        timestamp = parse_source_datetime(posting.get(source_field))
        if timestamp:
            result[field] = timestamp
    locations = posting.get("jobLocation", [])
    if isinstance(locations, dict):
        locations = [locations]
    location_names = []
    for location in locations if isinstance(locations, list) else []:
        address = location.get("address", {}) if isinstance(location, dict) else {}
        if isinstance(address, str):
            location_names.append(address)
        elif isinstance(address, dict):
            country = address.get("addressCountry", "")
            if isinstance(country, dict):
                country = country.get("name", "")
            parts = [address.get("addressLocality"), address.get("addressRegion"), country]
            location_names.append(", ".join(dict.fromkeys(str(part) for part in parts if part)))
    if any(location_names):
        result["location"] = "; ".join(name for name in location_names if name)
        result["company_location"] = result["location"]
    employment_types = {
        "FULL_TIME": "full_time", "PART_TIME": "part_time", "CONTRACTOR": "contract",
        "CONTRACT": "contract", "INTERN": "internship", "INTERNSHIP": "internship",
    }
    employment_type = posting.get("employmentType")
    if isinstance(employment_type, list):
        employment_type = employment_type[0] if len(employment_type) == 1 else None
    if isinstance(employment_type, str) and employment_type.upper() in employment_types:
        result["employment_type"] = employment_types[employment_type.upper()]
    if posting.get("jobLocationType") == "TELECOMMUTE":
        result["workplace_type"] = "remote"
    return result
