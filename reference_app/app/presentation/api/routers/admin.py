from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ....application.admin.commands import CreateModerationCommand
from ....application.catalog.commands import (
    CreateDomainCommand,
    CreateQuestionCommand,
    CreateRoleCommand,
    CreateStarTemplateCommand,
    UpdateQuestionCommand,
)
from ....application.container import ServiceContainer
from ..dependencies import get_container, get_session, require_admin
from ..helpers.cache import invalidate_cache
from ..schemas.admin import (
    AuditLogOut,
    AuditLogPageOut,
    ModerationCreateIn,
    ModerationItemOut,
    ModerationPageOut,
    SystemStatsOut,
    UserAdminOut,
    UserListPageOut,
    UserRoleUpdateIn,
    UserStatusUpdateIn,
)
from ..schemas.catalog import (
    DomainCreateIn,
    DomainOut,
    QuestionCreateIn,
    QuestionOut,
    QuestionUpdateIn,
    RoleCreateIn,
    RoleOut,
    StarTemplateCreateIn,
    StarTemplateOut,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/users", response_model=UserListPageOut)
def list_users(
    search: str | None = Query(None),
    role: str | None = Query(None, pattern="^(candidate|admin)$"),
    status: str | None = Query(None, pattern="^(active|suspended|deleted)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> UserListPageOut:
    items, total = container.admin_service.get_users(
        session, search=search, role=role, status=status, limit=limit, offset=offset,
    )
    return UserListPageOut(
        items=[UserAdminOut.model_validate(u) for u in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/users/{user_id}/status", response_model=UserAdminOut)
def update_user_status(
    user_id: int,
    data: UserStatusUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> UserAdminOut:
    user = container.admin_service.update_user_status(session, admin_id, user_id, data.status)
    return UserAdminOut.model_validate(user)


@router.patch("/users/{user_id}/role", response_model=UserAdminOut)
def update_user_role(
    user_id: int,
    data: UserRoleUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> UserAdminOut:
    user = container.admin_service.update_user_role(session, admin_id, user_id, data.role)
    return UserAdminOut.model_validate(user)


@router.get("/stats", response_model=SystemStatsOut)
def get_stats(
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> SystemStatsOut:
    stats = container.admin_service.get_system_stats(session)
    return SystemStatsOut.model_validate(stats)


@router.get("/audit-logs", response_model=AuditLogPageOut)
def list_audit_logs(
    table_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> AuditLogPageOut:
    items, total = container.admin_service.get_audit_logs(
        session, table_name=table_name, limit=limit, offset=offset,
    )
    return AuditLogPageOut(
        items=[AuditLogOut.model_validate(a) for a in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/moderation", response_model=ModerationPageOut)
def list_moderation_logs(
    target_type: str | None = Query(None, pattern="^(question|answer|user|session|comment)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> ModerationPageOut:
    items, total = container.admin_service.get_moderation_logs(
        session, target_type=target_type, limit=limit, offset=offset,
    )
    return ModerationPageOut(
        items=[ModerationItemOut.model_validate(m) for m in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/moderation", response_model=ModerationItemOut, status_code=201)
def create_moderation_action(
    data: ModerationCreateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> ModerationItemOut:
    item = container.admin_service.create_moderation_action(
        session,
        admin_id,
        CreateModerationCommand(
            target_type=data.target_type,
            action=data.action,
            target_id=data.target_id,
            reason=data.reason,
        ),
    )
    return ModerationItemOut.model_validate(item)


# --- Catalog Management Endpoints ---


@router.post("/domains", response_model=DomainOut, status_code=201)
def create_domain(
    data: DomainCreateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> DomainOut:
    domain = container.catalog_service.create_domain(
        session, CreateDomainCommand(domain_name=data.domain_name, description=data.description),
    )
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="job_domains",
        record_id=domain.domain_id,
        action="insert",
        new_value={"domain_name": domain.domain_name},
    )
    invalidate_cache(container, "catalog:")
    return DomainOut.model_validate(domain)


@router.post("/roles", response_model=RoleOut, status_code=201)
def create_role(
    data: RoleCreateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> RoleOut:
    role = container.catalog_service.create_role(
        session,
        CreateRoleCommand(
            domain_id=data.domain_id, role_name=data.role_name, description=data.description,
        ),
    )
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="job_roles",
        record_id=role.role_id,
        action="insert",
        new_value={"role_name": role.role_name, "domain_id": role.domain_id},
    )
    invalidate_cache(container, "catalog:")
    return RoleOut.model_validate(role)


@router.post("/star-templates", response_model=StarTemplateOut, status_code=201)
def create_star_template(
    data: StarTemplateCreateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> StarTemplateOut:
    tmpl = container.catalog_service.create_star_template(
        session,
        CreateStarTemplateCommand(
            title=data.title,
            situation_guide=data.situation_guide,
            task_guide=data.task_guide,
            action_guide=data.action_guide,
            result_guide=data.result_guide,
            language=data.language,
        ),
    )
    return StarTemplateOut.model_validate(tmpl)


@router.post("/questions", response_model=QuestionOut, status_code=201)
def create_question(
    data: QuestionCreateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionOut:
    q = container.catalog_service.create_question(
        session,
        CreateQuestionCommand(
            domain_id=data.domain_id,
            question_text=data.question_text,
            question_type=data.question_type,
            language=data.language,
            role_id=data.role_id,
            experience_level=data.experience_level,
            star_template_id=data.star_template_id,
            created_by=admin_id,
        ),
    )
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="question_bank",
        record_id=q.question_id,
        action="insert",
        new_value={"question_text": q.question_text, "domain_id": q.domain_id},
    )
    invalidate_cache(container, "catalog:")
    return QuestionOut.model_validate(q)


@router.put("/questions/{question_id}", response_model=QuestionOut)
def update_question(
    question_id: int,
    data: QuestionUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionOut:
    q = container.catalog_service.update_question(
        session,
        question_id,
        UpdateQuestionCommand(
            question_text=data.question_text,
            question_type=data.question_type,
            language=data.language,
            role_id=data.role_id,
            experience_level=data.experience_level,
            star_template_id=data.star_template_id,
            is_active=data.is_active,
            fields_set=frozenset(data.model_fields_set),
        ),
    )
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="question_bank",
        record_id=q.question_id,
        action="update",
        new_value={"question_id": q.question_id},
    )
    invalidate_cache(container, "catalog:")
    return QuestionOut.model_validate(q)


@router.delete("/questions/{question_id}", status_code=204)
def delete_question(
    question_id: int,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> None:
    container.catalog_service.delete_question(session, question_id)
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="question_bank",
        record_id=question_id,
        action="delete",
    )
    invalidate_cache(container, "catalog:")
