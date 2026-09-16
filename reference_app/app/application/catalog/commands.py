from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CreateDomainCommand:
    domain_name: str
    description: str | None = None


@dataclass(frozen=True)
class CreateRoleCommand:
    domain_id: int
    role_name: str
    description: str | None = None


@dataclass(frozen=True)
class CreateStarTemplateCommand:
    title: str
    situation_guide: str | None = None
    task_guide: str | None = None
    action_guide: str | None = None
    result_guide: str | None = None
    language: str = "vi"


@dataclass(frozen=True)
class CreateQuestionCommand:
    domain_id: int
    question_text: str
    question_type: str
    language: str = "vi"
    role_id: int | None = None
    experience_level: str | None = None
    star_template_id: int | None = None
    created_by: int | None = None


@dataclass(frozen=True)
class UpdateQuestionCommand:
    question_text: str | None = None
    question_type: str | None = None
    language: str | None = None
    role_id: int | None = None
    experience_level: str | None = None
    star_template_id: int | None = None
    is_active: bool | None = None
    fields_set: frozenset[str] = field(default_factory=frozenset)
