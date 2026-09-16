from __future__ import annotations

from typing import Any

from ...domain.analytics import (
    CandidateDashboard,
    HistorySessionItem,
    ProgressTrends,
    SessionDetail,
    SessionResultReport,
)
from ...domain.errors import NotFoundError
from ..common import PageRequest, PageResult
from .ports import AnalyticsRepoPort


class AnalyticsService:
    def __init__(self, repo: AnalyticsRepoPort) -> None:
        self._repo = repo

    def get_dashboard(self, session: Any, candidate_id: int) -> CandidateDashboard:
        return self._repo.get_dashboard(session, candidate_id)

    def get_progress_trends(
        self, session: Any, candidate_id: int, limit: int = 10
    ) -> ProgressTrends:
        return self._repo.get_progress_trends(session, candidate_id, limit=limit)

    def get_history(
        self,
        session: Any,
        candidate_id: int,
        page_request: PageRequest,
        domain_id: int | None = None,
        role_id: int | None = None,
        mode: str | None = None,
        status: str | None = None,
    ) -> PageResult[HistorySessionItem]:
        items, total = self._repo.get_history(
            session=session,
            candidate_id=candidate_id,
            page=page_request.page,
            page_size=page_request.size,
            domain_id=domain_id,
            role_id=role_id,
            mode=mode,
            status=status,
        )
        return PageResult(
            items=tuple(items),
            total=total,
        )

    def get_session_detail(
        self, session: Any, candidate_id: int, session_id: int
    ) -> SessionDetail:
        detail = self._repo.get_session_detail(session, candidate_id, session_id)
        if detail is None:
            raise NotFoundError(f"interview session {session_id} not found")
        return detail

    def get_session_result(
        self, session: Any, candidate_id: int, session_id: int
    ) -> SessionResultReport:
        result = self._repo.get_session_result(session, candidate_id, session_id)
        if result is None:
            raise NotFoundError(f"result for session {session_id} not found")
        return result
