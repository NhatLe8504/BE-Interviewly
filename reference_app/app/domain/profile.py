from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .errors import DomainValidationError

VALID_EXPERIENCE_LEVELS = frozenset({
    "intern",
    "fresher",
    "junior",
    "mid",
    "middle",
    "senior",
    "lead",
})

VALID_LANGUAGES = frozenset({"vi", "en"})


def validate_experience_level(level: str | None) -> None:
    if level is not None and level not in VALID_EXPERIENCE_LEVELS:
        allowed = ", ".join(sorted(VALID_EXPERIENCE_LEVELS))
        raise DomainValidationError(f"invalid experience level: {level}. Allowed: {allowed}")


def validate_language(lang: str | None) -> None:
    if lang is not None and lang not in VALID_LANGUAGES:
        allowed = ", ".join(sorted(VALID_LANGUAGES))
        raise DomainValidationError(f"invalid preferred language: {lang}. Allowed: {allowed}")


def validate_phone(phone: str | None) -> str | None:
    if phone is None:
        return None
    cleaned = phone.strip()
    if len(cleaned) > 20:
        raise DomainValidationError("phone must not exceed 20 characters")
    return cleaned


def validate_bio(bio: str | None) -> str | None:
    if bio is None:
        return None
    if len(bio) > 5000:
        raise DomainValidationError("bio must not exceed 5000 characters")
    return bio


def validate_avatar_url(url: str | None) -> str | None:
    if url is None:
        return None
    cleaned = url.strip()
    if len(cleaned) > 500:
        raise DomainValidationError("avatar_url must not exceed 500 characters")
    return cleaned


@dataclass(frozen=True)
class UserProfile:
    user_id: int
    full_name: str
    email: str
    phone: str | None
    role: str
    preferred_language: str
    status: str
    experience_level: str | None = None
    target_domain_id: int | None = None
    target_domain_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_language(self.preferred_language)
        if self.experience_level is not None:
            validate_experience_level(self.experience_level)
