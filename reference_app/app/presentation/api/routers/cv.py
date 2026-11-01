from __future__ import annotations

import asyncio
from typing import Any
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ....application.container import ServiceContainer
from ....application.cv.generation import _owned_job, edit_failed_answers, job_out, process_job, retry_job, start_job, submit_answers
from ....domain.errors import ConflictError
from ....infrastructure.persistence.models.cv import CvGenerationJob
from ..dependencies import get_container, get_current_user_id, get_session
from ..schemas.cv import (
    CvAtsScoreIn,
    CvAtsScoreOut,
    CvCreateIn,
    CvGenerateDraftIn,
    CvGenerationJobOut,
    CvJobAnswerIn,
    CvJobNotificationOut,
    CvJobStartIn,
    CvListItemOut,
    CvOut,
    CvSelectionRefineIn,
    CvSelectionRefineOut,
    CvUpdateIn,
    UserSkillsSummaryOut,
)

router = APIRouter(prefix="/api/v1/cvs", tags=["cv"])

_running_cv_jobs: dict[str, asyncio.Task] = {}


def schedule_cv_job(container: ServiceContainer, job_id: str) -> None:
    if job_id in _running_cv_jobs:
        return
    task = asyncio.create_task(asyncio.to_thread(process_job, container, job_id))
    _running_cv_jobs[job_id] = task
    task.add_done_callback(lambda completed: _running_cv_jobs.pop(job_id, None))


@router.post("/generation-jobs", response_model=CvGenerationJobOut, status_code=202)
async def create_generation_job(
    payload: CvJobStartIn,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CvGenerationJobOut:
    job = start_job(session, user_id, payload.target_job_id)
    if job.status in ("PREPARING", "GENERATING"):
        schedule_cv_job(container, job.job_id)
    return job_out(job)


@router.get("/generation-jobs/notifications", response_model=list[CvJobNotificationOut])
def get_generation_notifications(
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
) -> list[CvJobNotificationOut]:
    jobs = session.scalars(select(CvGenerationJob).where(
        CvGenerationJob.user_id == user_id,
        CvGenerationJob.notification_pending.is_(True),
        CvGenerationJob.status.in_(("QUESTIONS_READY", "COMPLETED", "FAILED")),
    ).order_by(CvGenerationJob.created_at.desc()).limit(20)).all()
    return [CvJobNotificationOut(job_id=job.job_id, job_title=job.job_title, status=job.status, cv_id=job.cv_id) for job in jobs]


@router.get("/generation-jobs/{job_id}", response_model=CvGenerationJobOut)
def get_generation_job(
    job_id: str,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
) -> CvGenerationJobOut:
    return job_out(_owned_job(session, user_id, job_id))


@router.post("/generation-jobs/{job_id}/answers", response_model=CvGenerationJobOut, status_code=202)
async def answer_generation_job(
    job_id: str,
    payload: CvJobAnswerIn,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CvGenerationJobOut:
    job = submit_answers(session, user_id, job_id, payload)
    schedule_cv_job(container, job.job_id)
    return job_out(job)


@router.post("/generation-jobs/{job_id}/retry", response_model=CvGenerationJobOut, status_code=202)
async def retry_generation_job(
    job_id: str,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CvGenerationJobOut:
    job = retry_job(session, user_id, job_id)
    schedule_cv_job(container, job.job_id)
    return job_out(job)


@router.post("/generation-jobs/{job_id}/edit-answers", response_model=CvGenerationJobOut)
def edit_generation_answers(
    job_id: str,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
) -> CvGenerationJobOut:
    return job_out(edit_failed_answers(session, user_id, job_id))


@router.post("/generation-jobs/{job_id}/notification-read", status_code=204, response_class=Response)
def read_generation_notification(
    job_id: str,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
) -> Response:
    job = _owned_job(session, user_id, job_id)
    if job.status not in ("QUESTIONS_READY", "COMPLETED", "FAILED"):
        raise ConflictError("Tác vụ chưa hoàn tất")
    job.notification_pending = False
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/user-skills-summary", response_model=UserSkillsSummaryOut)
def get_user_skills_summary(
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> UserSkillsSummaryOut:
    return container.cv_service.get_user_skills_summary(session, user_id)


@router.post("", response_model=CvOut, status_code=status.HTTP_201_CREATED)
def create_cv(
    data: CvCreateIn,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CvOut:
    return container.cv_service.create_cv(session, user_id, data)


@router.get("", response_model=list[CvListItemOut])
def list_user_cvs(
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[CvListItemOut]:
    return container.cv_service.list_user_cvs(session, user_id)


@router.post("/generate-draft")
def generate_ai_draft(
    data: CvGenerateDraftIn,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> dict[str, Any]:
    return container.cv_service.generate_ai_draft(session, user_id, data)


@router.post("/refine-selection", response_model=CvSelectionRefineOut)
def refine_selection(
    data: CvSelectionRefineIn,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CvSelectionRefineOut:
    return container.cv_service.refine_selection(session, user_id, data)


@router.get("/{cv_id}", response_model=CvOut)
def get_cv(
    cv_id: int,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CvOut:
    return container.cv_service.get_cv(session, user_id, cv_id)


@router.put("/{cv_id}", response_model=CvOut)
def update_cv(
    cv_id: int,
    data: CvUpdateIn,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CvOut:
    return container.cv_service.update_cv(session, user_id, cv_id, data)


@router.delete("/{cv_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_cv(
    cv_id: int,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> Response:
    container.cv_service.delete_cv(session, user_id, cv_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{cv_id}/ats-score", response_model=CvAtsScoreOut)
def calculate_ats_score(
    cv_id: int,
    payload: CvAtsScoreIn | None = None,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CvAtsScoreOut:
    target_job_id = payload.target_job_id if payload else None
    target_jd_text = payload.target_jd_text if payload else None
    return container.cv_service.calculate_ats_match(
        session=session,
        user_id=user_id,
        cv_id=cv_id,
        target_job_id=target_job_id,
        target_jd_text=target_jd_text,
    )
