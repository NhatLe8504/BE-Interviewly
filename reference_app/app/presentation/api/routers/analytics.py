from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ....application.common import PageRequest
from ....application.container import ServiceContainer
from ..dependencies import get_container, get_current_user_id, get_session
from ..schemas.analytics import (
    CandidateDashboardOut,
    HistoryPageOut,
    HistorySessionItemOut,
    ProgressTrendsOut,
    SessionDetailOut,
    SessionResultOut,
)

router = APIRouter(tags=["analytics"])


@router.get("/api/v1/analytics/dashboard", response_model=CandidateDashboardOut)
def get_dashboard(
    user_id: int = Depends(get_current_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CandidateDashboardOut:
    data = container.analytics_service.get_dashboard(session, user_id)
    return CandidateDashboardOut.model_validate(data, from_attributes=True)


@router.get("/api/v1/analytics/progress", response_model=ProgressTrendsOut)
def get_progress_trends(
    limit: int = Query(10, ge=1, le=50),
    user_id: int = Depends(get_current_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> ProgressTrendsOut:
    data = container.analytics_service.get_progress_trends(session, user_id, limit=limit)
    return ProgressTrendsOut.model_validate(data, from_attributes=True)


@router.get("/api/v1/analytics/history", response_model=HistoryPageOut)
@router.get("/api/v1/interviews/history", response_model=HistoryPageOut)
def get_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    domain_id: int | None = Query(None),
    role_id: int | None = Query(None),
    mode: str | None = Query(None),
    status: str | None = Query(None),
    user_id: int = Depends(get_current_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> HistoryPageOut:
    res = container.analytics_service.get_history(
        session=session,
        candidate_id=user_id,
        page_request=PageRequest(page=page, size=page_size),
        domain_id=domain_id,
        role_id=role_id,
        mode=mode,
        status=status,
    )
    total_pages = (res.total + page_size - 1) // page_size if res.total > 0 else 0
    return HistoryPageOut(
        items=[HistorySessionItemOut.model_validate(it, from_attributes=True) for it in res.items],
        total=res.total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/api/v1/analytics/sessions/{session_id}", response_model=SessionDetailOut)
@router.get("/api/v1/interviews/sessions/{session_id}", response_model=SessionDetailOut)
def get_session_detail(
    session_id: int,
    user_id: int = Depends(get_current_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> SessionDetailOut:
    data = container.analytics_service.get_session_detail(session, user_id, session_id)
    return SessionDetailOut.model_validate(data, from_attributes=True)


@router.get("/api/v1/analytics/sessions/{session_id}/result", response_model=SessionResultOut)
@router.get("/api/v1/interviews/sessions/{session_id}/result", response_model=SessionResultOut, operation_id="get_interview_session_result_analytics")
def get_session_result(
    session_id: int,
    user_id: int = Depends(get_current_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> SessionResultOut:
    data = container.analytics_service.get_session_result(session, user_id, session_id)
    return SessionResultOut.model_validate(data, from_attributes=True)
