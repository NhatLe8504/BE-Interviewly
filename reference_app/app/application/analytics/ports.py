from __future__ import annotations

from typing import Any, Protocol

from ...domain.analytics import (
    CandidateDashboard,
    HistorySessionItem,
    ProgressTrends,
    SessionDetail,
    SessionResultReport,
)


class AnalyticsRepoPort(Protocol):
    def get_dashboard(self, session: Any, candidate_id: int) -> CandidateDashboard: ...

    def get_progress_trends(
        self, session: Any, candidate_id: int, limit: int = 10
    ) -> ProgressTrends: ...

    def get_history(
        self,
        session: Any,
        candidate_id: int,
        page: int = 1,
        page_size: int = 10,
        domain_id: int | None = None,
        role_id: int | None = None,
        mode: str | None = None,
        status: str | None = None,
    ) -> tuple[list[HistorySessionItem], int]: ...

    def get_session_detail(
        self, session: Any, candidate_id: int, session_id: int
    ) -> SessionDetail | None: ...

    def get_session_result(
        self, session: Any, candidate_id: int, session_id: int
    ) -> SessionResultReport | None: ...
