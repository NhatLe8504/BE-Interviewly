from __future__ import annotations

import uuid
from typing import Any

from ...domain.catalog import (
    JobDomain,
    JobRole,
    QuestionBankItem,
    StarGuidanceTemplate,
    validate_catalog_experience_level,
    validate_catalog_language,
    validate_not_blank,
    validate_question_type,
)
from ...domain.errors import ConflictError, NotFoundError
from .commands import (
    CreateDomainCommand,
    CreateQuestionCommand,
    CreateRoleCommand,
    CreateStarTemplateCommand,
    UpdateQuestionCommand,
)
from .ports import CatalogRepositoryPort


class CatalogService:
    def __init__(self, repo: CatalogRepositoryPort) -> None:
        self.repo = repo

    def get_domains(self, session: Any) -> list[JobDomain]:
        return self.repo.list_domains(session)

    def get_domain(self, session: Any, domain_id: int) -> JobDomain:
        domain = self.repo.get_domain_by_id(session, domain_id)
        if domain is None:
            raise NotFoundError(f"domain {domain_id} not found")
        return domain

    def create_domain(self, session: Any, cmd: CreateDomainCommand) -> JobDomain:
        validate_not_blank(cmd.domain_name, "domain_name")
        return self.repo.add_domain(
            session, domain_name=cmd.domain_name.strip(), description=cmd.description,
        )

    def get_roles(self, session: Any, domain_id: int | None = None) -> list[JobRole]:
        if domain_id is not None and not self.repo.get_domain_by_id(session, domain_id):
            raise NotFoundError(f"domain {domain_id} not found")
        return self.repo.list_roles(session, domain_id=domain_id)

    def get_role(self, session: Any, role_id: int) -> JobRole:
        role = self.repo.get_role_by_id(session, role_id)
        if role is None:
            raise NotFoundError(f"role {role_id} not found")
        return role

    def create_role(self, session: Any, cmd: CreateRoleCommand) -> JobRole:
        if not self.repo.get_domain_by_id(session, cmd.domain_id):
            raise NotFoundError(f"domain {cmd.domain_id} not found")
        validate_not_blank(cmd.role_name, "role_name")
        return self.repo.add_role(
            session,
            domain_id=cmd.domain_id,
            role_name=cmd.role_name.strip(),
            description=cmd.description,
        )

    def get_star_templates(
        self, session: Any, language: str | None = None,
    ) -> list[StarGuidanceTemplate]:
        if language is not None:
            validate_catalog_language(language)
        return self.repo.list_star_templates(session, language=language)

    def get_star_template(
        self, session: Any, star_template_id: int,
    ) -> StarGuidanceTemplate:
        tmpl = self.repo.get_star_template_by_id(session, star_template_id)
        if tmpl is None:
            raise NotFoundError(f"star template {star_template_id} not found")
        return tmpl

    def create_star_template(
        self, session: Any, cmd: CreateStarTemplateCommand,
    ) -> StarGuidanceTemplate:
        validate_not_blank(cmd.title, "title")
        validate_catalog_language(cmd.language)
        return self.repo.add_star_template(
            session,
            title=cmd.title.strip(),
            situation_guide=cmd.situation_guide,
            task_guide=cmd.task_guide,
            action_guide=cmd.action_guide,
            result_guide=cmd.result_guide,
            language=cmd.language,
        )

    def get_questions(
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
    ) -> tuple[list[QuestionBankItem], int]:
        if language is not None:
            validate_catalog_language(language)
        if question_type is not None:
            validate_question_type(question_type)
        if experience_level is not None:
            validate_catalog_experience_level(experience_level)

        items = self.repo.list_questions(
            session,
            domain_id=domain_id,
            role_id=role_id,
            experience_level=experience_level,
            question_type=question_type,
            language=language,
            is_active=is_active,
            limit=limit,
            offset=offset,
        )
        total = self.repo.count_questions(
            session,
            domain_id=domain_id,
            role_id=role_id,
            experience_level=experience_level,
            question_type=question_type,
            language=language,
            is_active=is_active,
        )
        return items, total

    def get_question(self, session: Any, question_id: int) -> QuestionBankItem:
        q = self.repo.get_question_by_id(session, question_id)
        if q is None:
            raise NotFoundError(f"question {question_id} not found")
        return q

    def get_random_question(
        self,
        session: Any,
        *,
        domain_id: int | None = None,
        role_id: int | None = None,
        experience_level: str | None = None,
        language: str = "vi",
    ) -> QuestionBankItem:
        items, _ = self.get_questions(
            session,
            domain_id=domain_id,
            role_id=role_id,
            experience_level=experience_level,
            language=language,
            is_active=True,
            limit=100,
            offset=0,
        )
        if not items:
            raise NotFoundError("no active question found matching criteria")
        idx = int(uuid.uuid4().hex[:8], 16) % len(items)
        return items[idx]

    def create_question(
        self, session: Any, cmd: CreateQuestionCommand,
    ) -> QuestionBankItem:
        if not self.repo.get_domain_by_id(session, cmd.domain_id):
            raise NotFoundError(f"domain {cmd.domain_id} not found")
        if cmd.role_id is not None and not self.repo.get_role_by_id(session, cmd.role_id):
            raise NotFoundError(f"role {cmd.role_id} not found")
        if cmd.star_template_id is not None and not self.repo.get_star_template_by_id(session, cmd.star_template_id):
            raise NotFoundError(f"star template {cmd.star_template_id} not found")

        validate_not_blank(cmd.question_text, "question_text")
        validate_question_type(cmd.question_type)
        validate_catalog_language(cmd.language)
        if cmd.experience_level is not None:
            validate_catalog_experience_level(cmd.experience_level)

        return self.repo.add_question(
            session,
            domain_id=cmd.domain_id,
            question_text=cmd.question_text.strip(),
            question_type=cmd.question_type,
            language=cmd.language,
            role_id=cmd.role_id,
            experience_level=cmd.experience_level,
            star_template_id=cmd.star_template_id,
            created_by=cmd.created_by,
        )

    def update_question(
        self, session: Any, question_id: int, cmd: UpdateQuestionCommand,
    ) -> QuestionBankItem:
        existing = self.repo.get_question_by_id(session, question_id)
        if existing is None:
            raise NotFoundError(f"question {question_id} not found")

        if cmd.question_text is not None:
            validate_not_blank(cmd.question_text, "question_text")
        if cmd.question_type is not None:
            validate_question_type(cmd.question_type)
        if cmd.language is not None:
            validate_catalog_language(cmd.language)
        if cmd.experience_level is not None:
            validate_catalog_experience_level(cmd.experience_level)
        if cmd.role_id is not None and not self.repo.get_role_by_id(session, cmd.role_id):
            raise NotFoundError(f"role {cmd.role_id} not found")
        if cmd.star_template_id is not None and not self.repo.get_star_template_by_id(session, cmd.star_template_id):
            raise NotFoundError(f"star template {cmd.star_template_id} not found")

        return self.repo.update_question(
            session,
            question_id,
            question_text=cmd.question_text,
            question_type=cmd.question_type,
            language=cmd.language,
            role_id=cmd.role_id,
            experience_level=cmd.experience_level,
            star_template_id=cmd.star_template_id,
            is_active=cmd.is_active,
            fields_set=cmd.fields_set if cmd.fields_set else None,
        )

    def delete_question(self, session: Any, question_id: int) -> None:
        existing = self.repo.get_question_by_id(session, question_id)
        if existing is None:
            raise NotFoundError(f"question {question_id} not found")
        self.repo.delete_question(session, question_id)
