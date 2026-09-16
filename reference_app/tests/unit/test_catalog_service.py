from __future__ import annotations

import pytest

from app.application.catalog.commands import (
    CreateDomainCommand,
    CreateQuestionCommand,
    CreateRoleCommand,
    CreateStarTemplateCommand,
    UpdateQuestionCommand,
)
from app.application.catalog.service import CatalogService
from app.domain.catalog import (
    JobDomain,
    JobRole,
    QuestionBankItem,
    StarGuidanceTemplate,
)
from app.domain.errors import DomainValidationError, NotFoundError


class FakeCatalogRepo:
    def __init__(self) -> None:
        self.domains: dict[int, JobDomain] = {}
        self.roles: dict[int, JobRole] = {}
        self.star_templates: dict[int, StarGuidanceTemplate] = {}
        self.questions: dict[int, QuestionBankItem] = {}
        self.next_domain_id = 1
        self.next_role_id = 1
        self.next_template_id = 1
        self.next_question_id = 1

    def list_domains(self, session):
        return list(self.domains.values())

    def get_domain_by_id(self, session, domain_id: int):
        return self.domains.get(domain_id)

    def add_domain(self, session, *, domain_name: str, description: str | None = None):
        item = JobDomain(domain_id=self.next_domain_id, domain_name=domain_name, description=description)
        self.domains[self.next_domain_id] = item
        self.next_domain_id += 1
        return item

    def list_roles(self, session, *, domain_id: int | None = None):
        if domain_id is not None:
            return [r for r in self.roles.values() if r.domain_id == domain_id]
        return list(self.roles.values())

    def get_role_by_id(self, session, role_id: int):
        return self.roles.get(role_id)

    def add_role(self, session, *, domain_id: int, role_name: str, description: str | None = None):
        item = JobRole(role_id=self.next_role_id, domain_id=domain_id, role_name=role_name, description=description)
        self.roles[self.next_role_id] = item
        self.next_role_id += 1
        return item

    def list_star_templates(self, session, *, language: str | None = None):
        if language:
            return [t for t in self.star_templates.values() if t.language == language]
        return list(self.star_templates.values())

    def get_star_template_by_id(self, session, star_template_id: int):
        return self.star_templates.get(star_template_id)

    def add_star_template(self, session, *, title: str, situation_guide=None, task_guide=None, action_guide=None, result_guide=None, language="vi"):
        item = StarGuidanceTemplate(
            star_template_id=self.next_template_id,
            title=title,
            situation_guide=situation_guide,
            task_guide=task_guide,
            action_guide=action_guide,
            result_guide=result_guide,
            language=language,
        )
        self.star_templates[self.next_template_id] = item
        self.next_template_id += 1
        return item

    def list_questions(self, session, *, domain_id=None, role_id=None, experience_level=None, question_type=None, language=None, is_active=True, limit=50, offset=0):
        items = list(self.questions.values())
        if domain_id is not None:
            items = [q for q in items if q.domain_id == domain_id]
        if role_id is not None:
            items = [q for q in items if q.role_id == role_id]
        if experience_level is not None:
            items = [q for q in items if q.experience_level == experience_level]
        if question_type is not None:
            items = [q for q in items if q.question_type == question_type]
        if language is not None:
            items = [q for q in items if q.language == language]
        if is_active is not None:
            items = [q for q in items if q.is_active == is_active]
        return items[offset:offset + limit]

    def count_questions(self, session, *, domain_id=None, role_id=None, experience_level=None, question_type=None, language=None, is_active=True):
        return len(self.list_questions(session, domain_id=domain_id, role_id=role_id, experience_level=experience_level, question_type=question_type, language=language, is_active=is_active, limit=1000, offset=0))

    def get_question_by_id(self, session, question_id: int):
        return self.questions.get(question_id)

    def add_question(self, session, *, domain_id, question_text, question_type, language="vi", role_id=None, experience_level=None, star_template_id=None, created_by=None):
        item = QuestionBankItem(
            question_id=self.next_question_id,
            domain_id=domain_id,
            role_id=role_id,
            experience_level=experience_level,
            language=language,
            question_type=question_type,
            question_text=question_text,
            star_template_id=star_template_id,
            created_by=created_by,
        )
        self.questions[self.next_question_id] = item
        self.next_question_id += 1
        return item

    def update_question(self, session, question_id, *, question_text=None, question_type=None, language=None, role_id=None, experience_level=None, star_template_id=None, is_active=None, fields_set=None):
        q = self.questions[question_id]
        updated = QuestionBankItem(
            question_id=q.question_id,
            domain_id=q.domain_id,
            role_id=role_id if (fields_set and "role_id" in fields_set) else (role_id or q.role_id),
            experience_level=experience_level if (fields_set and "experience_level" in fields_set) else (experience_level or q.experience_level),
            language=language or q.language,
            question_type=question_type or q.question_type,
            question_text=question_text or q.question_text,
            star_template_id=star_template_id if (fields_set and "star_template_id" in fields_set) else (star_template_id or q.star_template_id),
            is_active=is_active if (fields_set and "is_active" in fields_set) else (is_active if is_active is not None else q.is_active),
            created_by=q.created_by,
        )
        self.questions[question_id] = updated
        return updated

    def delete_question(self, session, question_id: int):
        self.questions.pop(question_id, None)


@pytest.fixture
def catalog_env():
    repo = FakeCatalogRepo()
    service = CatalogService(repo=repo)
    d = service.create_domain(None, CreateDomainCommand(domain_name="IT", description="Tech"))
    r = service.create_role(None, CreateRoleCommand(domain_id=d.domain_id, role_name="Backend"))
    t = service.create_star_template(None, CreateStarTemplateCommand(title="General STAR", language="vi"))
    return service, repo, d.domain_id, r.role_id, t.star_template_id


def test_domain_and_role_crud(catalog_env):
    service, _, domain_id, role_id, _ = catalog_env
    domains = service.get_domains(None)
    assert len(domains) == 1
    assert domains[0].domain_name == "IT"

    roles = service.get_roles(None, domain_id=domain_id)
    assert len(roles) == 1
    assert roles[0].role_name == "Backend"


def test_create_role_domain_not_found(catalog_env):
    service, _, _, _, _ = catalog_env
    with pytest.raises(NotFoundError):
        service.create_role(None, CreateRoleCommand(domain_id=999, role_name="Ghost"))


def test_question_crud_and_filter(catalog_env):
    service, _, domain_id, role_id, tmpl_id = catalog_env
    q = service.create_question(
        None,
        CreateQuestionCommand(
            domain_id=domain_id,
            role_id=role_id,
            experience_level="junior",
            language="vi",
            question_type="behavioral",
            question_text="Tell me about a challenge you solved.",
            star_template_id=tmpl_id,
        ),
    )
    assert q.question_id == 1
    assert q.question_text == "Tell me about a challenge you solved."

    items, total = service.get_questions(None, domain_id=domain_id, experience_level="junior")
    assert total == 1
    assert items[0].question_id == q.question_id

    # Random question
    rand_q = service.get_random_question(None, domain_id=domain_id)
    assert rand_q.question_id == q.question_id

    # Update question
    updated = service.update_question(
        None,
        q.question_id,
        UpdateQuestionCommand(question_text="Updated text challenge"),
    )
    assert updated.question_text == "Updated text challenge"

    # Delete question
    service.delete_question(None, q.question_id)
    with pytest.raises(NotFoundError):
        service.get_question(None, q.question_id)
