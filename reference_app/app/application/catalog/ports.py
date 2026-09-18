from __future__ import annotations

from typing import Any, Protocol

from ...domain.catalog import (
    JobDomain,
    JobRole,
    QuestionBankItem,
    StarGuidanceTemplate,
)


class CatalogRepositoryPort(Protocol):
    def list_domains(self, session: Any) -> list[JobDomain]:
        ...

    def get_domain_by_id(self, session: Any, domain_id: int) -> JobDomain | None:
        ...

    def add_domain(
        self, session: Any, *, domain_name: str, description: str | None = None,
    ) -> JobDomain:
        ...

    def update_domain(
        self,
        session: Any,
        domain_id: int,
        *,
        domain_name: str | None = None,
        description: str | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> JobDomain:
        ...

    def delete_domain(self, session: Any, domain_id: int) -> None:
        ...

    def list_roles(self, session: Any, *, domain_id: int | None = None) -> list[JobRole]:
        ...

    def get_role_by_id(self, session: Any, role_id: int) -> JobRole | None:
        ...

    def add_role(
        self, session: Any, *, domain_id: int, role_name: str, description: str | None = None,
    ) -> JobRole:
        ...

    def update_role(
        self,
        session: Any,
        role_id: int,
        *,
        role_name: str | None = None,
        description: str | None = None,
        domain_id: int | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> JobRole:
        ...

    def delete_role(self, session: Any, role_id: int) -> None:
        ...

    def list_star_templates(
        self, session: Any, *, language: str | None = None,
    ) -> list[StarGuidanceTemplate]:
        ...

    def get_star_template_by_id(
        self, session: Any, star_template_id: int,
    ) -> StarGuidanceTemplate | None:
        ...

    def add_star_template(
        self,
        session: Any,
        *,
        title: str,
        situation_guide: str | None = None,
        task_guide: str | None = None,
        action_guide: str | None = None,
        result_guide: str | None = None,
        language: str = "vi",
    ) -> StarGuidanceTemplate:
        ...

    def list_questions(
        self,
        session: Any,
        *,
        domain_id: int | None = None,
        role_id: int | None = None,
        experience_level: str | None = None,
        question_type: str | None = None,
        language: str | None = None,
        is_active: bool | None = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[QuestionBankItem]:
        ...

    def count_questions(
        self,
        session: Any,
        *,
        domain_id: int | None = None,
        role_id: int | None = None,
        experience_level: str | None = None,
        question_type: str | None = None,
        language: str | None = None,
        is_active: bool | None = True,
    ) -> int:
        ...

    def get_question_by_id(
        self, session: Any, question_id: int,
    ) -> QuestionBankItem | None:
        ...

    def add_question(
        self,
        session: Any,
        *,
        domain_id: int,
        question_text: str,
        question_type: str,
        language: str = "vi",
        role_id: int | None = None,
        experience_level: str | None = None,
        star_template_id: int | None = None,
        created_by: int | None = None,
    ) -> QuestionBankItem:
        ...

    def update_question(
        self,
        session: Any,
        question_id: int,
        *,
        question_text: str | None = None,
        question_type: str | None = None,
        language: str | None = None,
        role_id: int | None = None,
        experience_level: str | None = None,
        star_template_id: int | None = None,
        is_active: bool | None = None,
        fields_set: frozenset[str] | None = None,
    ) -> QuestionBankItem:
        ...

    def delete_question(self, session: Any, question_id: int) -> None:
        ...
