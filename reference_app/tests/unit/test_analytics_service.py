from __future__ import annotations

from datetime import datetime, timezone
import pytest

from app.application.analytics.service import AnalyticsService
from app.application.common import PageRequest
from app.domain.analytics import (
    CandidateDashboard,
    CandidateKpiStats,
    HistorySessionItem,
    ProgressTrendPoint,
    ProgressTrends,
    RecentSessionSummary,
    SessionDetail,
    SessionResultReport,
    SkillRadarScore,
    TurnDetailItem,
    WeakPointRecommendation,
)
from app.domain.errors import NotFoundError


class FakeAnalyticsRepo:
    def __init__(self) -> None:
        self.dashboard = CandidateDashboard(
            candidate_id=1,
            kpi=CandidateKpiStats(
                total_interviews=3,
                completed_interviews=2,
                avg_score=82.5,
                total_practice_minutes=45,
                streak_days=2,
            ),
            skill_radar=SkillRadarScore(
                clarity=80.0,
                logic=85.0,
                evidence=75.0,
                delivery=88.0,
                star_method=80.0,
            ),
            recent_sessions=[
                RecentSessionSummary(
                    session_id=101,
                    domain_name="Công nghệ thông tin",
                    role_name="Backend Developer",
                    mode="voice",
                    score=85.0,
                    status="completed",
                    started_at=datetime.now(timezone.utc),
                )
            ],
            recommendations=[
                WeakPointRecommendation(
                    weak_area="Dẫn chứng thực tế",
                    score=75.0,
                    recommendation="Thêm số liệu định lượng",
                    suggested_question="Kể về tối ưu hiệu năng",
                )
            ],
        )
        self.trends = ProgressTrends(
            candidate_id=1,
            trends=[
                ProgressTrendPoint(
                    session_id=101,
                    date="15/09",
                    overall_score=85.0,
                    clarity_score=80.0,
                    logic_score=85.0,
                    example_score=75.0,
                    speaking_pace_wpm=135.0,
                    filler_words_count=2,
                    star_completion_rate=80.0,
                )
            ],
            avg_wpm=135.0,
            avg_filler_count=2.0,
            star_mastery_rate=80.0,
        )
        self.sessions: dict[int, SessionDetail] = {}
        self.results: dict[int, SessionResultReport] = {}

    def get_dashboard(self, session, candidate_id: int) -> CandidateDashboard:
        return self.dashboard

    def get_progress_trends(
        self, session, candidate_id: int, limit: int = 10
    ) -> ProgressTrends:
        return self.trends

    def get_history(
        self,
        session,
        candidate_id: int,
        page: int = 1,
        page_size: int = 10,
        domain_id: int | None = None,
        role_id: int | None = None,
        mode: str | None = None,
        status: str | None = None,
    ) -> tuple[list[HistorySessionItem], int]:
        item = HistorySessionItem(
            session_id=101,
            candidate_id=candidate_id,
            domain_id=1,
            domain_name="IT",
            role_id=2,
            role_name="Backend Developer",
            experience_level="junior",
            language="vi",
            mode="voice",
            status="completed",
            total_score=85.0,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            total_turns=4,
        )
        return [item], 1

    def get_session_detail(
        self, session, candidate_id: int, session_id: int
    ) -> SessionDetail | None:
        return self.sessions.get(session_id)

    def get_session_result(
        self, session, candidate_id: int, session_id: int
    ) -> SessionResultReport | None:
        return self.results.get(session_id)


def test_kpi_invariants() -> None:
    with pytest.raises(ValueError):
        CandidateKpiStats(
            total_interviews=-1,
            completed_interviews=0,
            avg_score=50.0,
            total_practice_minutes=10,
            streak_days=0,
        )

    with pytest.raises(ValueError):
        CandidateKpiStats(
            total_interviews=1,
            completed_interviews=0,
            avg_score=105.0,
            total_practice_minutes=10,
            streak_days=0,
        )


def test_skill_radar_invariants() -> None:
    with pytest.raises(ValueError):
        SkillRadarScore(
            clarity=110.0,
            logic=80.0,
            evidence=80.0,
            delivery=80.0,
            star_method=80.0,
        )


def test_analytics_service_get_dashboard() -> None:
    repo = FakeAnalyticsRepo()
    svc = AnalyticsService(repo)
    dash = svc.get_dashboard(None, candidate_id=1)
    assert dash.kpi.total_interviews == 3
    assert dash.kpi.avg_score == 82.5
    assert dash.skill_radar.clarity == 80.0
    assert len(dash.recent_sessions) == 1
    assert len(dash.recommendations) == 1


def test_analytics_service_get_progress_trends() -> None:
    repo = FakeAnalyticsRepo()
    svc = AnalyticsService(repo)
    trends = svc.get_progress_trends(None, candidate_id=1, limit=5)
    assert len(trends.trends) == 1
    assert trends.avg_wpm == 135.0


def test_analytics_service_get_history() -> None:
    repo = FakeAnalyticsRepo()
    svc = AnalyticsService(repo)
    page_res = svc.get_history(None, candidate_id=1, page_request=PageRequest(page=1, size=10))
    assert page_res.total == 1
    assert len(page_res.items) == 1
    assert page_res.items[0].session_id == 101


def test_analytics_service_get_session_detail_not_found() -> None:
    repo = FakeAnalyticsRepo()
    svc = AnalyticsService(repo)
    with pytest.raises(NotFoundError):
        svc.get_session_detail(None, candidate_id=1, session_id=999)


def test_analytics_service_get_session_result_found_and_not_found() -> None:
    repo = FakeAnalyticsRepo()
    svc = AnalyticsService(repo)
    with pytest.raises(NotFoundError):
        svc.get_session_result(None, candidate_id=1, session_id=999)

    repo.results[101] = SessionResultReport(
        session_id=101,
        candidate_id=1,
        status="completed",
        total_score=88.0,
        readiness_badge="Sẵn sàng ứng tuyển (Interview Ready)",
        clarity_score=85.0,
        structure_score=88.0,
        evidence_score=82.0,
        speaking_pace_wpm=130.0,
        pace_rating="Lý tưởng (Ideal)",
        filler_count=1,
        filler_words=["à"],
        pause_duration=1.5,
        star_analysis={"situation": True, "task": True, "action": True, "result": True},
        turns=[],
    )
    res = svc.get_session_result(None, candidate_id=1, session_id=101)
    assert res.total_score == 88.0
    assert res.pace_rating == "Lý tưởng (Ideal)"
