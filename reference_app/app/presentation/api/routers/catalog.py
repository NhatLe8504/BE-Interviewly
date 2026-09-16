from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ....application.container import ServiceContainer
from ..dependencies import get_container, get_session
from ..schemas.catalog import (
    DomainOut,
    QuestionDetailOut,
    QuestionOut,
    QuestionPageOut,
    RoleOut,
    StarTemplateOut,
)

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


@router.get("/domains", response_model=list[DomainOut])
def list_domains(
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[DomainOut]:
    items = container.catalog_service.get_domains(session)
    return [DomainOut.model_validate(d) for d in items]


@router.get("/roles", response_model=list[RoleOut])
def list_roles(
    domain_id: int | None = Query(None, description="Filter roles by domain"),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[RoleOut]:
    items = container.catalog_service.get_roles(session, domain_id=domain_id)
    return [RoleOut.model_validate(r) for r in items]


@router.get("/star-templates", response_model=list[StarTemplateOut])
def list_star_templates(
    language: str | None = Query(None, pattern="^(vi|en)$"),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[StarTemplateOut]:
    items = container.catalog_service.get_star_templates(session, language=language)
    return [StarTemplateOut.model_validate(t) for t in items]


@router.get("/questions", response_model=QuestionPageOut)
def list_questions(
    domain_id: int | None = Query(None),
    role_id: int | None = Query(None),
    level: str | None = Query(None, alias="level", pattern="^(intern|fresher|junior|mid|middle|senior)$"),
    type: str | None = Query(None, alias="type", pattern="^(behavioral|technical|situational)$"),
    language: str | None = Query(None, pattern="^(vi|en)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionPageOut:
    items, total = container.catalog_service.get_questions(
        session,
        domain_id=domain_id,
        role_id=role_id,
        experience_level=level,
        question_type=type,
        language=language,
        is_active=True,
        limit=limit,
        offset=offset,
    )
    return QuestionPageOut(
        items=[QuestionOut.model_validate(q) for q in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/questions/random", response_model=QuestionOut)
def get_random_question(
    domain_id: int | None = Query(None),
    role_id: int | None = Query(None),
    level: str | None = Query(None, alias="level", pattern="^(intern|fresher|junior|mid|middle|senior)$"),
    language: str = Query("vi", pattern="^(vi|en)$"),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionOut:
    q = container.catalog_service.get_random_question(
        session,
        domain_id=domain_id,
        role_id=role_id,
        experience_level=level,
        language=language,
    )
    return QuestionOut.model_validate(q)


@router.get("/questions/{question_id}", response_model=QuestionDetailOut)
def get_question_detail(
    question_id: int,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionDetailOut:
    q = container.catalog_service.get_question(session, question_id)
    tmpl_out = None
    if q.star_template_id:
        try:
            tmpl = container.catalog_service.get_star_template(session, q.star_template_id)
            tmpl_out = StarTemplateOut.model_validate(tmpl)
        except Exception:
            tmpl_out = None

    base_dict = {
        "question_id": q.question_id,
        "domain_id": q.domain_id,
        "role_id": q.role_id,
        "experience_level": q.experience_level,
        "language": q.language,
        "question_type": q.question_type,
        "question_text": q.question_text,
        "star_template_id": q.star_template_id,
        "is_active": q.is_active,
        "created_by": q.created_by,
        "created_at": q.created_at,
        "updated_at": q.updated_at,
        "star_template": tmpl_out,
    }
    return QuestionDetailOut.model_validate(base_dict)
