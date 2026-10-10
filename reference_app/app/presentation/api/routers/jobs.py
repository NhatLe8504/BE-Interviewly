from __future__ import annotations

import asyncio
import logging
import math
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ....application.container import ServiceContainer
from ....application.job_aggregator.service import JobAggregatorService
from ....application.skills.service import UserSkillService
from ....application.skills.readiness import JobReadinessEvaluator
from ....domain.jd_interview import JDSourceType, NormalizedJD
from ..dependencies import get_container, get_optional_user_id, get_session
from ..schemas.jobs import (
    JobCompanyOut,
    JobDetailOut,
    JobFilterMetadataOut,
    JobItemOut,
    JobListResponse,
    JobSkillMatchOut,
    StartJobPracticeOut,
)
from ..schemas.user_skills import JobReadinessAssessmentOut, JobReadinessRequirementOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def _format_salary(salary_min: float | None, salary_max: float | None, currency: str = "VND") -> str:
    if not salary_min and not salary_max:
        return "Chưa công bố"
    divisor = 1_000_000 if currency == "VND" and (salary_min or salary_max or 0) >= 1_000_000 else 1
    unit = f"triệu {currency}" if divisor > 1 else currency
    if salary_min and salary_max:
        return f"{salary_min / divisor:,.0f} – {salary_max / divisor:,.0f} {unit}"
    if salary_min:
        return f"Từ {salary_min / divisor:,.0f} {unit}"
    return f"Đến {salary_max / divisor:,.0f} {unit}"


def _build_jd_text_and_checksums(job: Any) -> tuple[str, list[str]]:
    comp_name = job.company.company_name if job.company else "Doanh nghiệp"
    body = (getattr(job, "cleaned_jd_text", None) or getattr(job, "raw_description", None) or "").strip()
    jd_text = f"Vị trí: {job.title} tại {comp_name}\n\n{body}"
    c1 = NormalizedJD.calculate_checksum(jd_text)
    checksums = [c1]
    if body:
        c2 = NormalizedJD.calculate_checksum(body)
        if c2 not in checksums:
            checksums.append(c2)
    return jd_text, checksums


def _find_existing_practice_session(session: Session, job: Any) -> str | None:
    from ....infrastructure.persistence.models.jd_interview import JDGenerationJob, NormalizedJDRecord
    from ....domain.jd_interview import JDJobStatus

    _, checksums = _build_jd_text_and_checksums(job)
    existing = (
        session.query(JDGenerationJob)
        .filter(
            JDGenerationJob.checksum.in_(checksums),
            JDGenerationJob.status == JDJobStatus.COMPLETED.value,
        )
        .order_by(JDGenerationJob.created_at.desc())
        .first()
    )
    if not existing:
        existing = (
            session.query(JDGenerationJob)
            .join(NormalizedJDRecord, NormalizedJDRecord.job_id == JDGenerationJob.job_id)
            .filter(
                NormalizedJDRecord.original_url == f"job:{job.job_id}",
                JDGenerationJob.status == JDJobStatus.COMPLETED.value,
            )
            .order_by(JDGenerationJob.created_at.desc())
            .first()
        )
    return existing.job_id if existing else None


def _to_job_item_out(job: Any, existing_interview_id: str | None = None) -> JobItemOut:
    comp_out = None
    if job.company:
        branding_allowed = job.company.branding_reuse_allowed
        comp_out = JobCompanyOut(
            company_id=job.company.company_id,
            company_name=job.company.company_name,
            slug=job.company.slug,
            logo_url=job.company.logo_url if branding_allowed else None,
            company_logo_url=job.company.logo_url if branding_allowed else None,
            company_banner_url=job.company.banner_url if branding_allowed else None,
            branding_source_url=job.company.branding_source_url,
            branding_license_url=job.company.branding_license_url,
            branding_reuse_allowed=branding_allowed,
            branding_candidates=getattr(job.company, "branding_candidates", {}) or {},
            location=job.company.location,
        )
    return JobItemOut(
        job_id=job.job_id,
        source_id=job.source_id,
        title=job.title,
        slug=job.slug,
        seniority=job.seniority,
        employment_type=job.employment_type,
        workplace_type=job.workplace_type,
        location=job.location,
        salary_display=_format_salary(job.salary_min, job.salary_max, job.salary_currency),
        salary_currency=job.salary_currency,
        salary_min=float(job.salary_min) if job.salary_min is not None else None,
        salary_max=float(job.salary_max) if job.salary_max is not None else None,
        skills_required=job.skills_required or [],
        thumbnail_url=comp_out.company_banner_url if comp_out else None,
        technologies=job.technologies or [],
        via_source=job.via_source or "via Web",
        original_apply_url=job.original_apply_url,
        posted_at=job.posted_at,
        updated_at=getattr(job, "updated_at", None) or getattr(job, "last_seen_at", None) or job.created_at,
        created_at=job.created_at,
        first_seen_at=job.first_seen_at,
        last_synced_at=job.last_seen_at,
        expires_at=job.expires_at,
        country_codes=job.country_codes or [],
        is_global_remote=job.is_global_remote,
        company=comp_out,
        has_practice_session=bool(existing_interview_id),
        practice_interview_id=existing_interview_id,
    )


@router.get("", response_model=JobListResponse)
async def list_jobs(
    keyword: str = Query("", description="Search by keyword in title, location or skills"),
    domain_id: int | None = Query(None, description="Filter by domain ID"),
    seniority: str = Query("", description="Filter by seniority level"),
    workplace_type: str = Query("", description="Filter by workplace type (remote, hybrid, on_site)"),
    technology: str = Query("", description="Filter by specific technology"),
    location: str = Query("", description="Filter by location, city, or country"),
    source_id: str = Query("", description="Filter by source ID (topcv, itviec, vietnamworks, etc.)"),
    country_code: str = Query("VN", pattern="^(?:|[A-Z]{2}|GLOBAL)$", description="VN includes Vietnam and explicitly worldwide remote jobs; empty searches all countries"),
    sort_by: str = Query("recent", description="Sort order: recent, posted, match, salary_desc, title_asc"),
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=50),
    user_id: int | None = Depends(get_optional_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> JobListResponse:
    effective_tech = technology

    service = JobAggregatorService(
        session=session,
        serper_api_key=container.settings.serper_api_key if hasattr(container.settings, "serper_api_key") else "",
        redis_client=getattr(container, "redis_client", None),
    )

    items, total = service.list_jobs(
        keyword=keyword,
        domain_id=domain_id,
        seniority=seniority,
        workplace_type=workplace_type,
        technology=effective_tech,
        location=location,
        source_id=source_id,
        country_code=country_code,
        sort_by=sort_by,
        page=page,
        limit=limit,
    )

    total_pages = math.ceil(total / limit) if total > 0 else 1

    from ....infrastructure.persistence.models.jd_interview import JDGenerationJob
    from ....domain.jd_interview import JDJobStatus

    completed_checksum_rows = (
        session.query(JDGenerationJob.checksum, JDGenerationJob.job_id)
        .filter(JDGenerationJob.status == JDJobStatus.COMPLETED.value)
        .all()
    )
    checksum_map = {row[0]: row[1] for row in completed_checksum_rows}

    job_items: list[JobItemOut] = []
    for j in items:
        _, checksums = _build_jd_text_and_checksums(j)
        found_job_id = next((checksum_map[c] for c in checksums if c in checksum_map), None)
        job_items.append(_to_job_item_out(j, existing_interview_id=found_job_id))

    return JobListResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        items=job_items,
    )


@router.get("/metadata/filters", response_model=JobFilterMetadataOut)
def get_filter_metadata(
    country_code: str = Query("VN", pattern="^(?:|[A-Z]{2}|GLOBAL)$"),
    session: Session = Depends(get_session),
) -> JobFilterMetadataOut:
    service = JobAggregatorService(session=session)
    filters = service.get_filter_metadata(country_code=country_code)
    # Contract thống nhất với các metadata khác (countries/sources) và FE:
    # mỗi option là {id, name}. Trước đây router trả {value, label} làm FE
    # đọc option.id/option.name ra undefined (LOI P2).
    filters["sort_options"] = [
        {"id": "recent", "name": "Mới cập nhật dữ liệu"},
        {"id": "posted", "name": "Mới đăng tuyển"},
        {"id": "match", "name": "Phù hợp với tôi"},
        {"id": "salary_desc", "name": "Lương cao nhất"},
        {"id": "title_asc", "name": "Tên công việc A – Z"},
    ]
    return JobFilterMetadataOut(**filters)


@router.get("/sync/status")
def get_sync_status(
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    if getattr(container, "job_worker", None):
        return container.job_worker.last_run_stats
    return {"status": "unsupported", "message": "Worker not attached"}


@router.post("/sync", status_code=status.HTTP_200_OK)
async def sync_jobs_now(
    query: str = Query("java developer", description="Search query for live ingestion"),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    api_key = getattr(container.settings, "serper_api_key", "") or os.environ.get("SERPER_API_KEY", "")
    service = JobAggregatorService(
        session=session,
        serper_api_key=api_key,
        redis_client=getattr(container, "redis_client", None),
    )
    if getattr(container, "job_worker", None):
        stats = await container.job_worker.run_cycle(query=query)
        enriched = await service.backfill_missing_branding(limit=50)
        return {"status": "ok", "stats": stats, "enriched_companies": enriched}

    saved = await service.run_ingestion(query=query)
    enriched = await service.backfill_missing_branding(limit=50)
    return {"status": "ok", "synced_jobs": saved, "enriched_companies": enriched}


@router.post("/backfill-branding", status_code=status.HTTP_200_OK)
async def backfill_branding(
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    api_key = getattr(container.settings, "serper_api_key", "") or os.environ.get("SERPER_API_KEY", "")
    service = JobAggregatorService(
        session=session,
        serper_api_key=api_key,
        redis_client=getattr(container, "redis_client", None),
    )
    enriched = await service.backfill_missing_branding(limit=50)
    return {"status": "ok", "enriched_companies": enriched}


@router.get("/{job_id}", response_model=JobDetailOut)
def get_job_detail(
    job_id: str,
    session: Session = Depends(get_session),
) -> JobDetailOut:
    service = JobAggregatorService(session=session)
    job = service.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tin tuyển dụng này đã hết hạn hoặc không còn nhận ứng tuyển.",
        )

    existing_interview_id = _find_existing_practice_session(session, job)
    base_item = _to_job_item_out(job, existing_interview_id=existing_interview_id)
    item_dict = base_item.model_dump()
    item_dict["raw_description"] = job.raw_description or ""
    item_dict["cleaned_jd_text"] = job.cleaned_jd_text or ""
    item_dict["created_at"] = job.created_at
    return JobDetailOut(**item_dict)


@router.post("/{job_id}/readiness", response_model=JobReadinessAssessmentOut)
@router.get("/{job_id}/readiness", response_model=JobReadinessAssessmentOut)
def check_job_readiness(
    job_id: str,
    force: bool = Query(False, description="Force recompute"),
    user_id: int | None = Depends(get_optional_user_id),
    session: Session = Depends(get_session),
) -> JobReadinessAssessmentOut:
    service = JobAggregatorService(session=session)
    job = service.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if not user_id or user_id <= 0:
        assessment = JobReadinessEvaluator.evaluate(
            job_id=job.job_id,
            job_title=job.title,
            job_seniority=job.seniority,
            skills_required=job.skills_required or [],
            technologies=job.technologies or [],
            cleaned_jd_text=job.cleaned_jd_text or "",
            user_skills={},
        )
        return JobReadinessAssessmentOut(
            job_id=job.job_id,
            match_percent=0,
            verdict="insufficient_data",
            data_coverage=0.0,
            requirements=[
                JobReadinessRequirementOut(
                    skill_id=r.skill_id,
                    name=r.name,
                    importance=r.importance,
                    required_level=r.required_level,
                    user_level=r.user_level,
                    status=r.status,
                    confidence=r.confidence,
                    level_assumed=r.level_assumed,
                )
                for r in assessment.requirements
            ],
            explanation="Đăng nhập và hoàn thành các buổi luyện tập để AI phân tích mức độ phù hợp của bạn với vị trí này.",
            recommended_skills=assessment.recommended_skills,
            analysis_engine="heuristic",
        )

    skill_svc = UserSkillService(session=session)
    assessment = skill_svc.evaluate_job_readiness(user_id=user_id, job_id=job_id, force_refresh=force)
    return JobReadinessAssessmentOut(
        job_id=assessment.job_id,
        match_percent=assessment.match_percent,
        verdict=assessment.verdict,
        data_coverage=assessment.data_coverage,
        requirements=[
            JobReadinessRequirementOut(
                skill_id=r.skill_id,
                name=r.name,
                importance=r.importance,
                required_level=r.required_level,
                user_level=r.user_level,
                status=r.status,
                confidence=r.confidence,
                level_assumed=r.level_assumed,
            )
            for r in assessment.requirements
        ],
        explanation=assessment.explanation,
        recommended_skills=assessment.recommended_skills,
        analysis_engine=assessment.analysis_engine,
    )


@router.get("/{job_id}/skill-match", response_model=JobSkillMatchOut)
def get_job_skill_match(
    job_id: str,
    user_id: int | None = Depends(get_optional_user_id),
    session: Session = Depends(get_session),
) -> JobSkillMatchOut:
    service = JobAggregatorService(session=session)
    candidate_skills: list[str] = []

    if user_id and user_id > 0:
        skill_svc = UserSkillService(session=session)
        user_skills_dict = skill_svc.get_user_skills_dict(user_id)
        candidate_skills = [
            sid for sid, est in user_skills_dict.items()
            if est.level != "none" and est.confidence >= 0.20
        ]
        if not candidate_skills:
            from ....infrastructure.persistence.models.user import CandidateProfile
            profile = session.get(CandidateProfile, user_id)
            if profile and profile.bio:
                candidate_skills = [w.strip() for w in profile.bio.replace("\n", ",").split(",") if w.strip()]

    result = service.calculate_skill_match(job_id=job_id, candidate_skills=candidate_skills)
    return JobSkillMatchOut(
        job_id=result.job_id,
        match_score_pct=result.match_score_pct,
        matched_skills=result.matched_skills,
        missing_skills=result.missing_skills,
        recommendation=result.recommendation,
        has_candidate_skills=bool(candidate_skills),
    )


@router.post("/{job_id}/start-practice", response_model=StartJobPracticeOut)
async def start_practice_from_job(
    job_id: str,
    user_id: int | None = Depends(get_optional_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> StartJobPracticeOut:
    service = JobAggregatorService(session=session)
    job = service.get_job_by_id(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    # 1. If an interview script already exists for this JD -> Start practicing right away!
    existing_job_id = _find_existing_practice_session(session, job)
    if existing_job_id:
        return StartJobPracticeOut(
            interview_id=existing_job_id,
            job_id=job.job_id,
            redirect_url=f"/practice/setup/{existing_job_id}",
            has_existing_session=True,
        )

    # 2. No session exists yet -> Must be Pro to generate a new AI interview from JD
    effective_user_id = user_id if user_id and user_id > 0 else None
    if not effective_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vui lòng đăng nhập để tạo kịch bản phỏng vấn AI cho tin tuyển dụng này.",
        )

    from ....infrastructure.persistence.models.user import User
    from ....infrastructure.persistence.models.enums import UserRole
    from ....application.voice.entitlement import check_user_voice_entitlement

    is_pro = False
    user = session.get(User, effective_user_id)
    if user:
        role_val = getattr(user.role, "value", str(user.role)) if user.role else ""
        if role_val.lower() in ("admin", "pro"):
            is_pro = True
    if not is_pro and check_user_voice_entitlement(session, effective_user_id):
        is_pro = True

    if not is_pro:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tài khoản Pro mới có quyền tạo kịch bản phỏng vấn AI từ tin tuyển dụng mới. Vui lòng nâng cấp tài khoản để sử dụng.",
        )

    # 3. User is Pro -> Initialize and start generation
    from .jd_interview import _init_job, _get_or_create_orchestrator

    jd_text, checksums = _build_jd_text_and_checksums(job)
    primary_checksum = checksums[0]
    generation_job_id = _init_job(session, effective_user_id, JDSourceType.text.value, primary_checksum, is_public=True)

    orchestrator = _get_or_create_orchestrator(container)
    orchestrator.queue_manager.enqueue(
        job_id=generation_job_id,
        payload={
            "source_type": "text",
            "text_length": len(jd_text),
            "job_title": job.title,
            "url": f"job:{job.job_id}",
        },
    )

    asyncio.create_task(
        orchestrator.execute_pipeline(
            job_id=generation_job_id,
            user_id=effective_user_id,
            source_type=JDSourceType.text.value,
            input_data={"text": jd_text, "url": f"job:{job.job_id}"},
            options={
                "duration_minutes": 30,
                "difficulty": 3,
                "language": "vi",
            },
        )
    )

    return StartJobPracticeOut(
        interview_id=generation_job_id,
        job_id=job.job_id,
        redirect_url=f"/practice/new?job_id={generation_job_id}",
        has_existing_session=False,
    )
