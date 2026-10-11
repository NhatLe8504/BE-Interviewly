from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import func

from ....application.admin.commands import CreateModerationCommand
from ....application.catalog.commands import (
    CreateDomainCommand,
    CreateQuestionCommand,
    CreateRoleCommand,
    CreateStarTemplateCommand,
    UpdateDomainCommand,
    UpdateQuestionCommand,
    UpdateRoleCommand,
)
from ....application.container import ServiceContainer
from ....application.skills.taxonomy import get_default_taxonomy
from ....infrastructure.llm.question_tagging import suggest_skill_ids_with_llm
from ....infrastructure.llm.question_generator import generate_interview_questions_with_llm
from ....infrastructure.logging.server_log_store import global_server_log_store
from ....infrastructure.persistence.models.billing import SubscriptionPlan, UserSubscription
from ....infrastructure.persistence.models.enums import BillingCycle, SubStatus
from ....infrastructure.persistence.models.user import User
from ..dependencies import get_container, get_session, require_admin
from ..helpers.cache import invalidate_cache
from ..schemas.admin import (
    AuditLogOut,
    AuditLogPageOut,
    ModerationCreateIn,
    ModerationItemOut,
    ModerationPageOut,
    SystemStatsOut,
    UserAdminCreateIn,
    UserAdminOut,
    UserListPageOut,
    UserRoleUpdateIn,
    UserStatusUpdateIn,
    PaymentAdminOut,
    PaymentListPageOut,
    PaymentStatusUpdateIn,
    XGateSyncOut,
    SubscriptionPlanAdminOut,
    SubscriptionPlanCreateIn,
    SubscriptionPlanUpdateIn,
    UserSubscriptionAdminOut,
    UserSubscriptionPageOut,
    UserSubscriptionUpdateIn,
)
from ..schemas.catalog import (
    DomainCreateIn,
    DomainAdminDetailOut,
    DomainAdminSummaryOut,
    DomainAdminSummaryPageOut,
    DomainOut,
    DomainUpdateIn,
    QuestionCreateIn,
    QuestionOut,
    QuestionDetailOut,
    QuestionUpdateIn,
    QuestionSetOut,
    QuestionSetDetailOut,
    QuestionSetCreateIn,
    QuestionSetUpdateIn,
    RoleCreateIn,
    RoleAdminSummaryOut,
    RoleOut,
    RoleUpdateIn,
    SkillOptionOut,
    SkillSuggestionIn,
    SkillSuggestionOut,
    CatalogStatusUpdateIn,
    StarTemplateCreateIn,
    StarTemplateOut,
    QuestionAiGenerateIn,
    QuestionAiGenerateOut,
)

from ..schemas.course import (
    CourseCreateIn,
    CourseUpdateIn,
    ChapterCreateIn,
    ChapterUpdateIn,
    LessonCreateIn,
    LessonUpdateIn,
    CourseOut,
    CourseDetailOut,
    ChapterOut,
    ChapterDetailOut,
    LessonOut,
)
from .course import _to_course_out, _to_course_detail_out

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


@router.post("/users", response_model=UserAdminOut, status_code=201)
def create_user(
    data: UserAdminCreateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> UserAdminOut:
    user = container.admin_service.create_user(session, admin_id, data, container.auth_service.hasher)
    return UserAdminOut.model_validate(user)


@router.get("/users/{user_id}", response_model=UserAdminOut)
def get_user_detail(
    user_id: int,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> UserAdminOut:
    user = container.admin_service.get_user(session, user_id)
    return UserAdminOut.model_validate(user)


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



@router.get("/payments", response_model=PaymentListPageOut)
def list_payments(
    status: str | None = Query(None, pattern="^(pending|success|failed|refunded)$"),
    gateway: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> PaymentListPageOut:
    items, total = container.admin_service.get_payments(
        session, status=status, gateway=gateway, limit=limit, offset=offset
    )
    return PaymentListPageOut(
        items=[PaymentAdminOut.model_validate(p) for p in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/payments/{transaction_id}", response_model=PaymentAdminOut)
def get_payment_detail(
    transaction_id: int,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> PaymentAdminOut:
    payment = container.admin_service.get_payment(session, transaction_id)
    return PaymentAdminOut.model_validate(payment)

@router.post("/payments/sync-xgate", response_model=XGateSyncOut)
def sync_xgate_payments(
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> XGateSyncOut:
    res = container.payment_service.sync_xgate_transactions(session)
    return XGateSyncOut(**res)


@router.patch("/payments/{transaction_id}/status", response_model=PaymentAdminOut)
def update_payment_status(
    transaction_id: int,
    data: PaymentStatusUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> PaymentAdminOut:
    payment = container.admin_service.update_payment_status(session, admin_id, transaction_id, data.status)
    return PaymentAdminOut.model_validate(payment)

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


@router.get("/server-logs")
def get_server_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    level: str | None = Query(None),
    search: str | None = Query(None),
    method: str | None = Query(None),
    status_code: int | None = Query(None),
    tail_lines: int = Query(60, ge=1, le=200),
    admin_id: int = Depends(require_admin),
) -> dict[str, Any]:
    """
    Get live server terminal lines and API route logs recorded within the last 24 hours.
    Old logs beyond 24h are automatically pruned.
    """
    routes, total = global_server_log_store.get_route_logs(
        limit=limit,
        offset=offset,
        level=level,
        search=search,
        method=method,
        status_code=status_code,
    )
    lines = global_server_log_store.get_terminal_lines(tail=tail_lines, level=level)
    stats = global_server_log_store.get_stats()
    return {
        "terminal_lines": lines,
        "routes": routes,
        "total": total,
        "limit": limit,
        "offset": offset,
        "stats": stats,
    }


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


@router.get("/domains", response_model=DomainAdminSummaryPageOut)
def list_admin_domains(
    status: str = Query("active", pattern="^(active|archived|all)$"),
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> DomainAdminSummaryPageOut:
    status_filter = {"active": True, "archived": False, "all": None}[status]
    items = container.catalog_service.get_domain_summaries(session, is_active=status_filter)
    all_items = container.catalog_service.get_domain_summaries(session, is_active=None)
    return DomainAdminSummaryPageOut(
        items=[DomainAdminSummaryOut.model_validate(item) for item in items],
        total=len(items),
        active_domains=sum(1 for item in all_items if item["is_active"]),
        archived_domains=sum(1 for item in all_items if not item["is_active"]),
        active_roles=sum(item["active_role_count"] for item in all_items),
        total_questions=sum(item["question_count"] for item in all_items),
    )


@router.get("/domains/{domain_id}", response_model=DomainAdminDetailOut)
def get_admin_domain_detail(
    domain_id: int,
    status: str = Query("all", pattern="^(active|archived|all)$"),
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> DomainAdminDetailOut:
    domain_items = container.catalog_service.get_domain_summaries(session, is_active=None)
    domain = next((item for item in domain_items if item["domain_id"] == domain_id), None)
    if domain is None:
        container.catalog_service.get_domain(session, domain_id)
    status_filter = {"active": True, "archived": False, "all": None}[status]
    roles = container.catalog_service.get_role_summaries(
        session, domain_id=domain_id, is_active=status_filter,
    )
    return DomainAdminDetailOut(
        domain=DomainAdminSummaryOut.model_validate(domain),
        roles=[RoleAdminSummaryOut.model_validate(item) for item in roles],
    )


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


@router.put("/domains/{domain_id}", response_model=DomainOut)
def update_domain(
    domain_id: int,
    data: DomainUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> DomainOut:
    domain = container.catalog_service.update_domain(
        session,
        domain_id,
        UpdateDomainCommand(
            domain_name=data.domain_name,
            description=data.description,
            fields_set=frozenset(data.model_fields_set),
        ),
    )
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="job_domains",
        record_id=domain_id,
        action="update",
        new_value={"domain_name": domain.domain_name},
    )
    invalidate_cache(container, "catalog:")
    return DomainOut.model_validate(domain)


@router.patch("/domains/{domain_id}/status", response_model=DomainOut)
def update_domain_status(
    domain_id: int,
    data: CatalogStatusUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> DomainOut:
    domain = container.catalog_service.set_domain_active(
        session, domain_id, is_active=data.is_active,
    )
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="job_domains",
        record_id=domain_id,
        action="update",
        new_value={"is_active": data.is_active},
    )
    invalidate_cache(container, "catalog:")
    return DomainOut.model_validate(domain)


@router.delete("/domains/{domain_id}", status_code=204)
def delete_domain(
    domain_id: int,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> None:
    container.catalog_service.delete_domain(session, domain_id)
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="job_domains",
        record_id=domain_id,
        action="delete",
    )
    invalidate_cache(container, "catalog:")


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


@router.put("/roles/{role_id}", response_model=RoleOut)
def update_role(
    role_id: int,
    data: RoleUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> RoleOut:
    role = container.catalog_service.update_role(
        session,
        role_id,
        UpdateRoleCommand(
            role_name=data.role_name,
            description=data.description,
            domain_id=data.domain_id,
            fields_set=frozenset(data.model_fields_set),
        ),
    )
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="job_roles",
        record_id=role_id,
        action="update",
        new_value={"role_name": role.role_name},
    )
    invalidate_cache(container, "catalog:")
    return RoleOut.model_validate(role)


@router.patch("/roles/{role_id}/status", response_model=RoleOut)
def update_role_status(
    role_id: int,
    data: CatalogStatusUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> RoleOut:
    role = container.catalog_service.set_role_active(
        session, role_id, is_active=data.is_active,
    )
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="job_roles",
        record_id=role_id,
        action="update",
        new_value={"is_active": data.is_active},
    )
    invalidate_cache(container, "catalog:")
    return RoleOut.model_validate(role)


@router.delete("/roles/{role_id}", status_code=204)
def delete_role(
    role_id: int,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> None:
    container.catalog_service.delete_role(session, role_id)
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="job_roles",
        record_id=role_id,
        action="delete",
    )
    invalidate_cache(container, "catalog:")


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


@router.post("/questions", response_model=QuestionDetailOut, status_code=201)
def create_question(
    data: QuestionCreateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionDetailOut:
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
            quiz_data=data.quiz_data,
            sample_answer=data.sample_answer,
            follow_up_questions=data.follow_up_questions,
            tips=data.tips,
            skill_ids=data.skill_ids,
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
    return QuestionDetailOut.model_validate(q)


@router.put("/questions/{question_id}", response_model=QuestionDetailOut)
def update_question(
    question_id: int,
    data: QuestionUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionDetailOut:
    q = container.catalog_service.update_question(
        session,
        question_id,
        UpdateQuestionCommand(
            domain_id=data.domain_id,
            question_text=data.question_text,
            question_type=data.question_type,
            language=data.language,
            role_id=data.role_id,
            experience_level=data.experience_level,
            star_template_id=data.star_template_id,
            is_active=data.is_active,
            quiz_data=data.quiz_data,
            sample_answer=data.sample_answer,
            follow_up_questions=data.follow_up_questions,
            tips=data.tips,
            skill_ids=data.skill_ids,
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
    return QuestionDetailOut.model_validate(q)


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


@router.get("/skills", response_model=list[SkillOptionOut])
def list_skill_options(
    admin_id: int = Depends(require_admin),
) -> list[SkillOptionOut]:
    """Danh mục nhãn kỹ năng để UI admin tìm kiếm và gán nhãn câu hỏi."""
    taxonomy = get_default_taxonomy()
    return [
        SkillOptionOut(
            id=skill.id,
            name=skill.name,
            category=skill.category,
            role_tracks=list(skill.role_tracks),
        )
        for skill in taxonomy.all_skills()
    ]


@router.post("/questions/skill-suggestions", response_model=SkillSuggestionOut)
def suggest_question_skills(
    data: SkillSuggestionIn,
    admin_id: int = Depends(require_admin),
    container: ServiceContainer = Depends(get_container),
) -> SkillSuggestionOut:
    """LLM gợi ý nhãn kỹ năng cho nội dung câu hỏi; chỉ để admin rà lại, không ghi DB."""
    api_key = container.settings.openai_api_key or ""
    if not api_key.startswith("gsk_"):
        return SkillSuggestionOut(reason="llm_not_configured")
    try:
        suggested = suggest_skill_ids_with_llm(
            data.question_text.strip(),
            base_url=container.settings.openai_base_url,
            api_key=api_key,
            model=container.settings.openai_model,
            timeout=20.0,
        )
    except Exception:
        return SkillSuggestionOut(reason="llm_error")
    return SkillSuggestionOut(suggested_skill_ids=suggested)


@router.post("/questions/ai-generate", response_model=QuestionAiGenerateOut)
def ai_generate_questions(
    data: QuestionAiGenerateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionAiGenerateOut:
    """Sinh ngân hàng câu hỏi phỏng vấn chuẩn hóa bằng LLM (Groq / OpenAI)."""
    domain_name = data.domain_name or ""
    role_name = data.role_name or ""

    if not domain_name and data.domain_id:
        domain = container.catalog_service.get_domain(session, data.domain_id)
        if domain:
            domain_name = domain.domain_name

    if not role_name and data.role_id:
        role = container.catalog_service.get_role(session, data.role_id)
        if role:
            role_name = role.role_name

    questions = generate_interview_questions_with_llm(
        domain_name=domain_name or "Công nghệ thông tin (IT)",
        role_name=role_name or "Software Engineer",
        experience_level=data.experience_level or "junior",
        tech_stack=data.tech_stack or "",
        question_count=data.question_count or 3,
        question_distribution=data.question_distribution or "balanced",
        custom_prompt=data.custom_prompt or "",
        source_type=data.source_type or "prompt",
        source_value=data.source_value or "",
        base_url=container.settings.openai_base_url,
        api_key=container.settings.openai_api_key,
        model=container.settings.openai_model,
    )
    return QuestionAiGenerateOut(questions=questions)


@router.post("/question-sets", response_model=QuestionSetDetailOut, status_code=201)
def create_question_set(
    data: QuestionSetCreateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionSetDetailOut:
    s = container.catalog_service.create_question_set(
        session,
        title=data.title,
        description=data.description,
        domain_id=data.domain_id,
        role_id=data.role_id,
        experience_level=data.experience_level or "junior",
        tech_stack=data.tech_stack or [],
        language=data.language,
        target_difficulty=data.target_difficulty,
        estimated_duration_minutes=data.estimated_duration_minutes,
        is_curated=data.is_curated,
        is_active=data.is_active,
        question_ids=data.question_ids,
    )
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="question_sets",
        record_id=s.set_id,
        action="insert",
        new_value={"title": s.title, "domain_id": s.domain_id},
    )
    invalidate_cache(container, "catalog:")
    return container.catalog_service.repo.get_question_set_by_id(session, s.set_id)  # type: ignore


@router.put("/question-sets/{set_id}", response_model=QuestionSetDetailOut)
def update_question_set(
    set_id: int,
    data: QuestionSetUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuestionSetDetailOut:
    up_kwargs = data.model_dump(exclude_unset=True)
    q_ids = up_kwargs.pop("question_ids", None)
    s = container.catalog_service.update_question_set(
        session,
        set_id,
        question_ids=q_ids,
        **up_kwargs,
    )
    if not s:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Question set not found")
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="question_sets",
        record_id=s.set_id,
        action="update",
        new_value={"set_id": s.set_id},
    )
    invalidate_cache(container, "catalog:")
    return s


@router.delete("/question-sets/{set_id}", status_code=204)
def delete_question_set(
    set_id: int,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> None:
    success = container.catalog_service.delete_question_set(session, set_id)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Question set not found")
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="question_sets",
        record_id=set_id,
        action="delete",
    )
    invalidate_cache(container, "catalog:")


# =========================================================================
# Course, Chapter, and Lesson Management
# =========================================================================

@router.get("/courses", response_model=dict[str, Any])
def admin_list_courses(
    category: str | None = Query(None),
    level: str | None = Query(None),
    role: str | None = Query(None),
    search: str | None = Query(None),
    is_active: bool | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    items, total = container.course_service.list_courses(
        session,
        category=category,
        level=level,
        role=role,
        search=search,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [_to_course_out(c) for c in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/courses", response_model=CourseDetailOut, status_code=201)
def admin_create_course(
    data: CourseCreateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CourseDetailOut:
    course = container.course_service.create_course(session, data.model_dump())
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="courses",
        record_id=course.course_id,
        action="insert",
        new_value={"title": course.title, "slug": course.slug},
    )
    return _to_course_detail_out(course)


@router.get("/courses/{course_id}", response_model=CourseDetailOut)
def admin_get_course(
    course_id: int,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CourseDetailOut:
    c = container.course_service.get_course_by_id(session, course_id)
    if not c:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Khóa học không tồn tại")
    return _to_course_detail_out(c)


@router.put("/courses/{course_id}", response_model=CourseDetailOut)
def admin_update_course(
    course_id: int,
    data: CourseUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CourseDetailOut:
    updated = container.course_service.update_course(
        session, course_id, data.model_dump(exclude_unset=True),
    )
    if not updated:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Khóa học không tồn tại")
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="courses",
        record_id=course_id,
        action="update",
        new_value={"course_id": course_id},
    )
    return _to_course_detail_out(updated)


@router.delete("/courses/{course_id}", status_code=204)
def admin_delete_course(
    course_id: int,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> None:
    success = container.course_service.delete_course(session, course_id)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Khóa học không tồn tại")
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="courses",
        record_id=course_id,
        action="delete",
    )


@router.post("/courses/{course_id}/chapters", response_model=ChapterDetailOut, status_code=201)
def admin_create_chapter(
    course_id: int,
    data: ChapterCreateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> ChapterDetailOut:
    chapter = container.course_service.create_chapter(session, course_id, data.model_dump())
    if not chapter:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Khóa học không tồn tại")
    return ChapterDetailOut(
        chapter_id=chapter.chapter_id,
        course_id=chapter.course_id,
        title=chapter.title,
        title_en=chapter.title_en,
        description=chapter.description,
        order_index=chapter.order_index,
        lesson_count=0,
        lessons=[],
    )


@router.put("/courses/chapters/{chapter_id}", response_model=ChapterDetailOut)
def admin_update_chapter(
    chapter_id: int,
    data: ChapterUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> ChapterDetailOut:
    ch = container.course_service.update_chapter(
        session, chapter_id, data.model_dump(exclude_unset=True),
    )
    if not ch:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Chương học không tồn tại")
    lessons_out = [LessonOut.model_validate(ls) for ls in ch.lessons] if hasattr(ch, "lessons") and ch.lessons else []
    return ChapterDetailOut(
        chapter_id=ch.chapter_id,
        course_id=ch.course_id,
        title=ch.title,
        title_en=ch.title_en,
        description=ch.description,
        order_index=ch.order_index,
        lesson_count=len(lessons_out),
        lessons=lessons_out,
    )


@router.delete("/courses/chapters/{chapter_id}", status_code=204)
def admin_delete_chapter(
    chapter_id: int,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> None:
    success = container.course_service.delete_chapter(session, chapter_id)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Chương học không tồn tại")


@router.post("/courses/chapters/{chapter_id}/lessons", response_model=LessonOut, status_code=201)
def admin_create_lesson(
    chapter_id: int,
    data: LessonCreateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> LessonOut:
    lesson = container.course_service.create_lesson(session, chapter_id, data.model_dump())
    if not lesson:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Chương học không tồn tại")
    return LessonOut.model_validate(lesson)


@router.put("/courses/lessons/{lesson_id}", response_model=LessonOut)
def admin_update_lesson(
    lesson_id: int,
    data: LessonUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> LessonOut:
    ls = container.course_service.update_lesson(
        session, lesson_id, data.model_dump(exclude_unset=True),
    )
    if not ls:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Bài học không tồn tại")
    return LessonOut.model_validate(ls)


@router.delete("/courses/lessons/{lesson_id}", status_code=204)
def admin_delete_lesson(
    lesson_id: int,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> None:
    success = container.course_service.delete_lesson(session, lesson_id)
    if not success:
        raise HTTPException(status_code=404, detail="Bài học không tồn tại")


# --- Subscription & Plan Management Endpoints ---

@router.get("/plans", response_model=list[SubscriptionPlanAdminOut])
def admin_list_plans(
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
) -> list[SubscriptionPlanAdminOut]:
    plans = session.query(SubscriptionPlan).order_by(SubscriptionPlan.plan_id.asc()).all()
    results = []
    for p in plans:
        sub_count = (
            session.query(func.count(UserSubscription.user_subscription_id))
            .filter(UserSubscription.plan_id == p.plan_id, UserSubscription.status == SubStatus.active)
            .scalar()
            or 0
        )
        cycle_val = p.billing_cycle.value if hasattr(p.billing_cycle, "value") else str(p.billing_cycle)
        results.append(
            SubscriptionPlanAdminOut(
                plan_id=p.plan_id,
                plan_name=p.plan_name,
                price=float(p.price),
                billing_cycle=cycle_val,
                feature_limits=p.feature_limits or {},
                is_active=p.is_active,
                created_at=p.created_at,
                subscribers_count=sub_count,
            )
        )
    return results


@router.post("/plans", response_model=SubscriptionPlanAdminOut, status_code=201)
def admin_create_plan(
    data: SubscriptionPlanCreateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> SubscriptionPlanAdminOut:
    cycle_enum = BillingCycle(data.billing_cycle)
    new_plan = SubscriptionPlan(
        plan_name=data.plan_name,
        price=data.price,
        billing_cycle=cycle_enum,
        feature_limits=data.feature_limits,
        is_active=data.is_active,
    )
    session.add(new_plan)
    session.commit()
    session.refresh(new_plan)

    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="subscription_plans",
        record_id=new_plan.plan_id,
        action="create",
        new_value={"plan_name": new_plan.plan_name, "price": float(new_plan.price)},
    )

    return SubscriptionPlanAdminOut(
        plan_id=new_plan.plan_id,
        plan_name=new_plan.plan_name,
        price=float(new_plan.price),
        billing_cycle=new_plan.billing_cycle.value if hasattr(new_plan.billing_cycle, "value") else str(new_plan.billing_cycle),
        feature_limits=new_plan.feature_limits or {},
        is_active=new_plan.is_active,
        created_at=new_plan.created_at,
        subscribers_count=0,
    )


@router.put("/plans/{plan_id}", response_model=SubscriptionPlanAdminOut)
def admin_update_plan(
    plan_id: int,
    data: SubscriptionPlanUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> SubscriptionPlanAdminOut:
    plan = session.query(SubscriptionPlan).filter(SubscriptionPlan.plan_id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Gói cước không tồn tại")
    
    old_data = {"plan_name": plan.plan_name, "price": float(plan.price), "is_active": plan.is_active}

    if data.plan_name is not None:
        plan.plan_name = data.plan_name
    if data.price is not None:
        plan.price = data.price
    if data.billing_cycle is not None:
        plan.billing_cycle = BillingCycle(data.billing_cycle)
    if data.feature_limits is not None:
        plan.feature_limits = data.feature_limits
    if data.is_active is not None:
        plan.is_active = data.is_active

    session.commit()
    session.refresh(plan)

    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="subscription_plans",
        record_id=plan.plan_id,
        action="update",
        old_value=old_data,
        new_value={"plan_name": plan.plan_name, "price": float(plan.price), "is_active": plan.is_active},
    )

    sub_count = (
        session.query(func.count(UserSubscription.user_subscription_id))
        .filter(UserSubscription.plan_id == plan.plan_id, UserSubscription.status == SubStatus.active)
        .scalar()
        or 0
    )

    return SubscriptionPlanAdminOut(
        plan_id=plan.plan_id,
        plan_name=plan.plan_name,
        price=float(plan.price),
        billing_cycle=plan.billing_cycle.value if hasattr(plan.billing_cycle, "value") else str(plan.billing_cycle),
        feature_limits=plan.feature_limits or {},
        is_active=plan.is_active,
        created_at=plan.created_at,
        subscribers_count=sub_count,
    )


@router.delete("/plans/{plan_id}", status_code=204)
def admin_delete_plan(
    plan_id: int,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> None:
    plan = session.query(SubscriptionPlan).filter(SubscriptionPlan.plan_id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Gói cước không tồn tại")
    plan.is_active = False
    session.commit()
    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="subscription_plans",
        record_id=plan_id,
        action="update",
        new_value={"is_active": False},
    )


@router.get("/user-subscriptions", response_model=UserSubscriptionPageOut)
def admin_list_user_subscriptions(
    status: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
) -> UserSubscriptionPageOut:
    query = (
        session.query(UserSubscription)
        .join(User, UserSubscription.user_id == User.user_id)
        .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.plan_id)
    )
    if status:
        query = query.filter(UserSubscription.status == SubStatus(status))
    if search:
        s = f"%{search.strip()}%"
        query = query.filter((User.full_name.ilike(s)) | (User.email.ilike(s)))
    
    total = query.count()
    rows = query.order_by(UserSubscription.created_at.desc()).offset(offset).limit(limit).all()
    items = []
    for r in rows:
        st_val = r.status.value if hasattr(r.status, "value") else str(r.status)
        items.append(
            UserSubscriptionAdminOut(
                user_subscription_id=r.user_subscription_id,
                user_id=r.user_id,
                user_email=r.user.email if r.user else None,
                user_name=r.user.full_name if r.user else None,
                plan_id=r.plan_id,
                plan_name=r.plan.plan_name if r.plan else None,
                status=st_val,
                auto_renew=r.auto_renew,
                start_date=r.start_date,
                end_date=r.end_date,
                created_at=r.created_at,
            )
        )
    return UserSubscriptionPageOut(items=items, total=total, limit=limit, offset=offset)


@router.patch("/user-subscriptions/{user_subscription_id}", response_model=UserSubscriptionAdminOut)
def admin_update_user_subscription(
    user_subscription_id: int,
    data: UserSubscriptionUpdateIn,
    admin_id: int = Depends(require_admin),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> UserSubscriptionAdminOut:
    sub = session.query(UserSubscription).filter(UserSubscription.user_subscription_id == user_subscription_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Thuê bao không tồn tại")
    
    old_status = sub.status.value if hasattr(sub.status, "value") else str(sub.status)
    if data.status is not None:
        sub.status = SubStatus(data.status)
    if data.auto_renew is not None:
        sub.auto_renew = data.auto_renew
    if data.end_date is not None:
        sub.end_date = data.end_date
    
    session.commit()
    session.refresh(sub)

    container.admin_service.repo.record_audit(
        session,
        user_id=admin_id,
        table_name="user_subscriptions",
        record_id=sub.user_subscription_id,
        action="update",
        old_value={"status": old_status},
        new_value={"status": sub.status.value if hasattr(sub.status, "value") else str(sub.status)},
    )

    st_val = sub.status.value if hasattr(sub.status, "value") else str(sub.status)
    return UserSubscriptionAdminOut(
        user_subscription_id=sub.user_subscription_id,
        user_id=sub.user_id,
        user_email=sub.user.email if sub.user else None,
        user_name=sub.user.full_name if sub.user else None,
        plan_id=sub.plan_id,
        plan_name=sub.plan.plan_name if sub.plan else None,
        status=st_val,
        auto_renew=sub.auto_renew,
        start_date=sub.start_date,
        end_date=sub.end_date,
        created_at=sub.created_at,
    )


