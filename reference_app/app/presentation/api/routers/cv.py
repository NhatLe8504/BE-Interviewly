from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ....application.container import ServiceContainer
from ..dependencies import get_container, get_current_user_id, get_session
from ..schemas.cv import (
    CvAtsScoreIn,
    CvAtsScoreOut,
    CvCreateIn,
    CvGenerateDraftIn,
    CvListItemOut,
    CvOut,
    CvSelectionRefineIn,
    CvSelectionRefineOut,
    CvUpdateIn,
    UserSkillsSummaryOut,
)

router = APIRouter(prefix="/api/v1/cvs", tags=["cv"])


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


@router.delete("/{cv_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cv(
    cv_id: int,
    user_id: int = Depends(get_current_user_id),
    session: Session = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> None:
    container.cv_service.delete_cv(session, user_id, cv_id)


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
