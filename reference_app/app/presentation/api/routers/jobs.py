from __future__ import annotations

import asyncio
import logging
import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ....application.container import ServiceContainer
from ....application.job_aggregator.service import JobAggregatorService
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def _format_salary(salary_min: float | None, salary_max: float | None, currency: str = "VND") -> str:
    if not salary_min and not salary_max:
        return "Thỏa thuận"
    if salary_min and salary_max:
        min_tr = salary_min / 1_000_000
        max_tr = salary_max / 1_000_000
        return f"{min_tr:.0f} - {max_tr:.0f} triệu {currency}"
    if salary_min:
        return f"Từ {salary_min / 1_000_000:.0f} triệu {currency}"
    return f"Lên tới {salary_max / 1_000_000:.0f} triệu {currency}"


def _to_job_item_out(job: Any) -> JobItemOut:
    comp_out = None
    if job.company:
        comp_out = JobCompanyOut(
            company_id=job.company.company_id,
            company_name=job.company.company_name,
            slug=job.company.slug,
            logo_url=job.company.logo_url,
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
        salary_min=float(job.salary_min) if job.salary_min is not None else None,
        salary_max=float(job.salary_max) if job.salary_max is not None else None,
        skills_required=job.skills_required or [],
        thumbnail_url=job.company.logo_url if job.company and job.company.logo_url else None,
        technologies=job.technologies or [],
        via_source=job.via_source or "via Web",
        original_apply_url=job.original_apply_url,
        posted_at=job.posted_at,
        updated_at=getattr(job, "updated_at", None) or getattr(job, "last_seen_at", None) or job.created_at,
        created_at=job.created_at,
        company=comp_out,
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
    sort_by: str = Query("recent", description="Sort order: recent, posted, salary_desc, title_asc"),
    page: int = Query(1, ge=1),
    limit: int = Query(12, ge=1, le=50),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> JobListResponse:
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
        technology=technology,
        location=location,
        source_id=source_id,
        sort_by=sort_by,
        page=page,
        limit=limit,
    )

    # If database is empty on initial load, trigger real crawler cycle
    if total == 0 and not keyword and not seniority and not technology:
        if getattr(container, "job_worker", None):
            await container.job_worker.run_cycle()
        else:
            await service.run_ingestion()
        items, total = service.list_jobs(page=page, limit=limit)

    total_pages = math.ceil(total / limit) if total > 0 else 1
    return JobListResponse(
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
        items=[_to_job_item_out(j) for j in items],
    )


@router.get("/metadata/filters", response_model=JobFilterMetadataOut)
def get_filter_metadata(
    session: Session = Depends(get_session),
) -> JobFilterMetadataOut:
    service = JobAggregatorService(session=session)
    data = service.get_filter_metadata()
    return JobFilterMetadataOut(
        seniorities=data.get("seniorities", []),
        workplace_types=data.get("workplace_types", []),
        top_technologies=data.get("top_technologies", []),
        locations=data.get("locations", []),
        sources=data.get("sources", []),
        sort_options=data.get("sort_options", []),
    )


@router.get("/sync/status")
def get_sync_status(
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    if getattr(container, "job_worker", None):
        return container.job_worker.last_run_stats
    return {"status": "unsupported", "message": "Worker not attached"}


@router.post("/sync", status_code=status.HTTP_200_OK)
async def sync_jobs(
    query: str = Query("", description="Optional custom query"),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    if getattr(container, "job_worker", None):
        stats = await container.job_worker.run_cycle(query=query)
        return {"status": "ok", "stats": stats}

    api_key = getattr(container.settings, "serper_api_key", "")
    if not api_key:
        import os
        api_key = os.environ.get("SERPER_API_KEY", "")

    service = JobAggregatorService(
        session=session,
        serper_api_key=api_key,
        redis_client=getattr(container, "redis_client", None),
    )
    saved = await service.run_ingestion(query=query)
    return {"status": "ok", "synced_jobs": saved}


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

    base_item = _to_job_item_out(job)
    item_dict = base_item.model_dump()
    item_dict["raw_description"] = job.raw_description or ""
    item_dict["cleaned_jd_text"] = job.cleaned_jd_text or ""
    item_dict["created_at"] = job.created_at
    return JobDetailOut(**item_dict)


@router.get("/{job_id}/skill-match", response_model=JobSkillMatchOut)
def get_job_skill_match(
    job_id: str,
    user_id: int | None = Depends(get_optional_user_id),
    session: Session = Depends(get_session),
) -> JobSkillMatchOut:
    service = JobAggregatorService(session=session)
    candidate_skills: list[str] = []

    if user_id:
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

    from .jd_interview import _init_job, _get_or_create_orchestrator

    effective_user_id = user_id if user_id and user_id > 0 else 1
    jd_text = f"Vị trí: {job.title} tại {job.company.company_name if job.company else 'Doanh nghiệp'}\n\n{job.cleaned_jd_text}"
    checksum = NormalizedJD.calculate_checksum(jd_text)
    generation_job_id = _init_job(session, effective_user_id, JDSourceType.text.value, checksum)

    orchestrator = _get_or_create_orchestrator(container)
    orchestrator.queue_manager.enqueue(
        job_id=generation_job_id,
        payload={"source_type": "text", "text_length": len(jd_text), "job_title": job.title},
    )

    asyncio.create_task(
        orchestrator.execute_pipeline(
            job_id=generation_job_id,
            user_id=effective_user_id,
            source_type=JDSourceType.text.value,
            input_data={"text": jd_text},
            options={
                "duration_minutes": 30,
                "difficulty": "medium",
                "language": "vi",
            },
        )
    )

    return StartJobPracticeOut(
        interview_id=generation_job_id,
        job_id=job.job_id,
        redirect_url=f"/practice/new?jobId={generation_job_id}",
    )
