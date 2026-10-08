from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata

from .job_aggregator import JobEmploymentType, JobSeniority, JobWorkplaceType


def normalized_text(value: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKD", value.lower().replace("đ", "d"))
        if not unicodedata.combining(character)
    )


def detect_seniority(title: str, text: str = "") -> JobSeniority:
    patterns = (
        (JobSeniority.intern, r"\b(?:intern|internship|trainee|thuc tap)\b"),
        (JobSeniority.fresher, r"\b(?:fresher|graduate|moi tot nghiep)\b"),
        (JobSeniority.lead, r"\b(?:principal|staff|head|lead|truong nhom)\b"),
        (JobSeniority.senior, r"\b(?:senior|sr\.?|chuyen vien cao cap)\b"),
        (JobSeniority.junior, r"\b(?:junior|jr\.?)\b"),
        (JobSeniority.mid, r"\b(?:middle|mid[- ]?level|intermediate)\b"),
    )
    for seniority, pattern in patterns:
        if re.search(pattern, normalized_text(title)):
            return seniority
    explicit_levels = re.findall(
        r"(?:seniority|experience level|cap bac)\s*[:\-]\s*([^\n.;]+)", normalized_text(text)
    )
    for level_text in explicit_levels:
        for seniority, pattern in patterns:
            if re.search(pattern, level_text):
                return seniority
    return JobSeniority.unknown


def detect_workplace_type(title: str, location: str = "", text: str = "") -> JobWorkplaceType:
    combined = normalized_text(f"{title} {location} {text}")
    if re.search(r"\b(?:hybrid|linh hoat)\b", combined):
        return JobWorkplaceType.hybrid
    if re.search(r"\b(?:remote|tu xa|work from home|home[- ]based)\b", combined):
        return JobWorkplaceType.remote
    if re.search(r"\b(?:on[- ]?site|office[- ]based|tai van phong)\b", combined):
        return JobWorkplaceType.on_site
    return JobWorkplaceType.unknown


def detect_employment_type(title: str, text: str = "") -> JobEmploymentType:
    combined = normalized_text(f"{title} {text}")
    if re.search(r"\b(?:part[- ]time|ban thoi gian)\b", combined):
        return JobEmploymentType.part_time
    if re.search(r"\b(?:contract|hop dong|freelance)\b", combined):
        return JobEmploymentType.contract
    if re.search(r"\b(?:intern|internship|thuc tap)\b", normalized_text(title)):
        return JobEmploymentType.internship
    if re.search(r"\b(?:full[- ]time|toan thoi gian)\b", combined):
        return JobEmploymentType.full_time
    return JobEmploymentType.unknown


COUNTRY_PATTERNS = {
    "VN": r"\b(?:vn|viet ?nam|hanoi|ha noi|ho chi minh|hcmc?|sai gon|saigon|da nang|danang|hai phong|can tho)\b",
    "US": r"\b(?:united states|usa|new york|san francisco|palo alto|san diego|washington|colorado springs|miami|honolulu|kitsap|fayetteville)\b|,\s*(?:CA|NY|WA|CO|HI|NC|DC|FL|TX)\b",
    "GB": r"\b(?:united kingdom|uk|london)\b",
    "SG": r"\b(?:singapore)\b",
    "JP": r"\b(?:japan|tokyo|osaka)\b",
    "DE": r"\b(?:germany|berlin)\b",
    "ES": r"\b(?:spain|madrid|barcelona)\b",
    "IN": r"\b(?:india|bangalore|bengaluru)\b",
    "CA": r"\b(?:canada|toronto|vancouver)\b",
    "AU": r"\b(?:australia|sydney|melbourne)\b",
    "IE": r"\b(?:ireland|dublin)\b",
    "PL": r"\b(?:poland|warsaw)\b",
    "BR": r"\b(?:brazil)\b",
    "MX": r"\b(?:mexico)\b",
    "FR": r"\b(?:france|paris)\b",
}


def detect_countries(location: str | None) -> list[str]:
    if not location:
        return []
    normalized = normalized_text(location)
    return [code for code, pattern in COUNTRY_PATTERNS.items() if re.search(pattern, normalized, re.I)]


def is_global_remote(location: str | None, workplace_type: str) -> bool:
    return workplace_type == "remote" and bool(
        re.search(r"\b(?:worldwide|world[- ]wide|global|anywhere|toan cau)\b", normalized_text(location or ""))
    )


def parse_source_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, (int, float)):
            parsed = datetime.fromtimestamp(value / 1000 if value > 100_000_000_000 else value, timezone.utc)
        else:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    except (ValueError, TypeError, OverflowError, OSError):
        return None
