from __future__ import annotations

import json
import re
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
    try:
        parsed = urlparse(url)
        if parsed.scheme == "http" and parsed.hostname in allowed_hosts:
            url = parsed._replace(scheme="https").geturl()
            parsed = urlparse(url)
        if parsed.port:
            return None
    except ValueError:
        return None
    if len(url) > 1000 or parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username or parsed.password:
        return None
    return url


def structured_company_branding(soup: BeautifulSoup, source_url: str, company_name: str, policy: dict[str, Any]) -> dict[str, Any]:
    mapping = policy.get("structured_media", {})
    if not mapping:
        return {}
    nodes: list[Any] = []
    decoder = json.JSONDecoder()
    for script in soup.find_all("script"):
        content = script.string or script.get_text()
        try:
            if script.get("id") == "__NEXT_DATA__" or script.get("type") == "application/json":
                nodes.append(json.loads(content))
            elif content.startswith("self.__next_f.push("):
                frame, _offset = decoder.raw_decode(content[len("self.__next_f.push("):])
                if isinstance(frame, list) and len(frame) > 1 and isinstance(frame[1], str):
                    for row in frame[1].splitlines():
                        record = row.partition(":")[2]
                        if record.startswith(("{", "[")):
                            try:
                                payload, _offset = decoder.raw_decode(record)
                                nodes.append(payload)
                            except ValueError:
                                continue
        except (TypeError, ValueError):
            continue
    expected_names = {normalized_text(name.strip()) for name in [company_name, *policy.get("company_aliases", {}).get(normalized_text(company_name), [])]}
    result = {}
    for _node_index in range(10000):
        if not nodes:
            break
        node = nodes.pop()
        if isinstance(node, list):
            nodes.extend(node)
            continue
        if not isinstance(node, dict):
            continue
        name = node.get(mapping.get("company_name_field", "companyName"))
        if isinstance(name, str) and normalized_text(name.strip()) in expected_names:
            for field, keys in (("company_logo_url", mapping.get("logo_fields", [])), ("company_banner_url", mapping.get("banner_fields", []))):
                if field in result:
                    continue
                for key in keys:
                    values = node.get(key, [])
                    for value in values if isinstance(values, list) else [values]:
                        candidate = approved_asset_url(value, source_url, policy.get("allowed_image_hosts", []))
                        patterns = policy.get("asset_path_patterns", {}).get(field, [])
                        if candidate and (not patterns or any(re.search(pattern, urlparse(candidate).path) for pattern in patterns)):
                            result[field] = candidate
                            break
                    if field in result:
                        break
        nodes.extend(value for value in node.values() if isinstance(value, (dict, list)))
    if result:
        result["branding_source_url"] = source_url
    return result


def extract_company_branding(
    soup: BeautifulSoup, source_url: str, company_name: str, recipe: dict[str, Any],
    *, is_company_page: bool = False,
) -> dict[str, Any]:
    policy = recipe.get("company_branding", {})
    structured = structured_company_branding(soup, source_url, company_name, policy)
    if structured:
        return structured
    posting = job_structured_data(soup)
    organization = posting.get("hiringOrganization") or {}
    if not isinstance(organization, dict):
        return {}
    organization_name = organization.get("name", "")
    identity_selectors = policy.get("company_name_selectors", []) if is_company_page else policy.get("detail_company_name_selectors", [])
    if policy.get("company_name_selector"):
        identity_selectors = [policy["company_name_selector"], *identity_selectors]
    if not organization_name:
        for selector in identity_selectors:
            company_heading = soup.select_one(selector)
            if company_heading:
                organization_name = company_heading.get("content") or company_heading.get_text(" ", strip=True)
                if organization_name:
                    break
    identity_pattern = policy.get("identity_clean_pattern")
    if identity_pattern:
        organization_name = re.sub(identity_pattern, "", organization_name, flags=re.I).strip()
    expected_names = [company_name, *policy.get("company_aliases", {}).get(normalized_text(company_name), [])]
    clean_company = re.sub(
        r"^(CÔNG TY|Công ty|TỔNG CÔNG TY|Tổng công ty|TẬP ĐOÀN)\s+(TNHH\s+MTV|TNHH|CỔ PHẦN|Cổ phần|CP|MTV)\s*",
        "",
        company_name,
        flags=re.IGNORECASE,
    ).strip()
    if clean_company and clean_company != company_name:
        expected_names.append(clean_company)
    norm_expected = {normalized_text(name.strip()) for name in expected_names if name.strip()}
    norm_org = normalized_text(organization_name.strip())
    if norm_org not in norm_expected and not any(norm_org in exp or exp in norm_org for exp in norm_expected if len(exp) >= 4):
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
            for image in soup.select(selector):
                values = [image.get(attribute) for attribute in ("data-src", "data-original", "src", "content")]
                background = re.search(r"url\([\"\']?([^\"\')]+)", image.get("style", ""))
                if background:
                    values.append(background.group(1))
                for value in values:
                    candidate = approved_asset_url(value, source_url, allowed_hosts)
                    if candidate and not any(re.search(pattern, candidate, re.I) for pattern in policy.get("reject_asset_patterns", [])):
                        path_patterns = policy.get("asset_path_patterns", {}).get(field, [])
                        if not path_patterns or any(re.search(pattern, urlparse(candidate).path) for pattern in path_patterns):
                            result[field] = candidate
                            break
                if field in result:
                    break
            if field in result:
                break
    if result:
        result["branding_source_url"] = source_url
    return result


def collect_company_branding(
    soup: BeautifulSoup, source_url: str, company_name: str, recipe: dict[str, Any]
) -> dict[str, Any]:
    policy = recipe.get("company_branding", {})
    license_url = policy.get("license_url", "")
    if policy.get("reuse_allowed") is not True or not license_url.startswith("https://"):
        return {}
    result = extract_company_branding(soup, source_url, company_name, recipe)
    if result:
        result.update(branding_reuse_allowed=True, branding_license_url=license_url)
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
