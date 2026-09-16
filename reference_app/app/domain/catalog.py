from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .errors import DomainValidationError

VALID_QUESTION_TYPES = frozenset({"behavioral", "technical", "situational"})
VALID_LANGUAGES = frozenset({"vi", "en"})
VALID_EXPERIENCE_LEVELS = frozenset({"intern", "fresher", "junior", "mid", "middle", "senior"})


def validate_not_blank(val: str, field_name: str) -> str:
    cleaned = val.strip()
    if not cleaned:
        raise DomainValidationError(f"{field_name} must not be blank")
    return cleaned


def validate_question_type(qtype: str) -> str:
    cleaned = qtype.strip().lower()
    if cleaned not in VALID_QUESTION_TYPES:
        allowed = ", ".join(sorted(VALID_QUESTION_TYPES))
        raise DomainValidationError(f"invalid question_type: {qtype}. Allowed: {allowed}")
    return cleaned


def validate_catalog_language(lang: str) -> str:
    cleaned = lang.strip().lower()
    if cleaned not in VALID_LANGUAGES:
        allowed = ", ".join(sorted(VALID_LANGUAGES))
        raise DomainValidationError(f"invalid language: {lang}. Allowed: {allowed}")
    return cleaned


def validate_catalog_experience_level(level: str | None) -> str | None:
    if level is None:
        return None
    cleaned = level.strip().lower()
    if cleaned not in VALID_EXPERIENCE_LEVELS:
        allowed = ", ".join(sorted(VALID_EXPERIENCE_LEVELS))
        raise DomainValidationError(f"invalid experience_level: {level}. Allowed: {allowed}")
    return cleaned


@dataclass(frozen=True)
class JobDomain:
    domain_id: int
    domain_name: str
    description: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_not_blank(self.domain_name, "domain_name")


@dataclass(frozen=True)
class JobRole:
    role_id: int
    domain_id: int
    role_name: str
    description: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_not_blank(self.role_name, "role_name")


@dataclass(frozen=True)
class StarGuidanceTemplate:
    star_template_id: int
    title: str
    situation_guide: str | None = None
    task_guide: str | None = None
    action_guide: str | None = None
    result_guide: str | None = None
    language: str = "vi"
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_not_blank(self.title, "title")
        validate_catalog_language(self.language)


@dataclass(frozen=True)
class QuestionBankItem:
    question_id: int
    domain_id: int
    role_id: int | None
    experience_level: str | None
    language: str
    question_type: str
    question_text: str
    star_template_id: int | None = None
    is_active: bool = True
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_not_blank(self.question_text, "question_text")
        validate_question_type(self.question_type)
        validate_catalog_language(self.language)
        if self.experience_level is not None:
            validate_catalog_experience_level(self.experience_level)
