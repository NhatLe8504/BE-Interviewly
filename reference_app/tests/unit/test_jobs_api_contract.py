import pytest
from app.presentation.api.routers import jobs as jobs_router


class _StubJobService:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def get_filter_metadata(self, country_code: str = "VN") -> dict:
        return {
            "seniorities": [],
            "workplace_types": [],
            "top_technologies": [],
            "locations": [],
            "countries": [],
            "sources": [],
            "sort_options": [{"id": "recent", "name": "stale"}],
        }


def test_filter_metadata_sort_options_use_id_and_name(monkeypatch):
    """FE dọc option.id/option.name; BE phải trả đúng contract này (LOI P2)."""
    monkeypatch.setattr(jobs_router, "JobAggregatorService", _StubJobService)

    out = jobs_router.get_filter_metadata(country_code="VN", session=None)

    assert out.sort_options[0] == {"id": "recent", "name": "Mới cập nhật dữ liệu"}
    assert {option["id"] for option in out.sort_options} == {"recent", "posted", "match", "salary_desc", "title_asc"}
    assert all("value" not in option and "label" not in option for option in out.sort_options)


def test_build_jd_text_and_checksums_structure():
    from types import SimpleNamespace

    job = SimpleNamespace(
        title="Senior Python Engineer",
        company=SimpleNamespace(company_name="Tech Corp"),
        location="Hà Nội",
        seniority="senior",
        skills_required=["Python", "FastAPI", "PostgreSQL"],
        technologies=["Docker"],
        cleaned_jd_text="Thiết kế và xây dựng microservices hiệu năng cao.",
        raw_description=None,
    )

    jd_text, checksums = jobs_router._build_jd_text_and_checksums(job)
    assert "Vị trí: Senior Python Engineer tại Tech Corp" in jd_text
    assert "Địa điểm: Hà Nội" in jd_text
    assert "Cấp bậc: senior" in jd_text
    assert "Python, FastAPI, PostgreSQL" in jd_text
    assert "Thiết kế và xây dựng microservices" in jd_text
    assert len(checksums) >= 1
    assert all(len(c) == 64 for c in checksums)


@pytest.mark.anyio
async def test_start_practice_from_job_pro_creates_and_schedules(monkeypatch):
    from types import SimpleNamespace

    job = SimpleNamespace(
        job_id="job-123",
        title="Frontend Lead",
        company=SimpleNamespace(company_name="VNG"),
        location="TP Hồ Chí Minh",
        seniority="lead",
        skills_required=["React", "Next.js"],
        technologies=[],
        cleaned_jd_text="Leading frontend team in building web applications.",
        raw_description=None,
    )

    class _MockJobService:
        def __init__(self, *args, **kwargs) -> None:
            pass
        def get_job_by_id(self, job_id):
            return job

    class _MockSession:
        def get(self, model, user_id):
            return SimpleNamespace(role=SimpleNamespace(value="pro"))

    class _MockQueueManager:
        def __init__(self):
            self.enqueued = []
        def enqueue(self, job_id, payload):
            self.enqueued.append((job_id, payload))

    class _MockOrchestrator:
        def __init__(self):
            self.queue_manager = _MockQueueManager()

    scheduled_jobs = []
    init_job_calls = []

    def _mock_init_job(session, user_id, source_type, checksum, request_payload, is_public=False):
        init_job_calls.append((user_id, source_type, checksum, request_payload, is_public))
        return "jd_test_123"

    def _mock_schedule_jd_job(container, job_id):
        scheduled_jobs.append(job_id)

    mock_container = SimpleNamespace()
    mock_orchestrator = _MockOrchestrator()

    monkeypatch.setattr(jobs_router, "JobAggregatorService", _MockJobService)
    monkeypatch.setattr(jobs_router, "_find_existing_practice_session", lambda session, job: None)

    from app.presentation.api.routers import jd_interview
    monkeypatch.setattr(jd_interview, "_init_job", _mock_init_job)
    monkeypatch.setattr(jd_interview, "_get_or_create_orchestrator", lambda container: mock_orchestrator)
    monkeypatch.setattr(jd_interview, "schedule_jd_job", _mock_schedule_jd_job)

    result = await jobs_router.start_practice_from_job(
        job_id="job-123",
        user_id=1,
        session=_MockSession(),
        container=mock_container,
    )

    assert result.interview_id == "jd_test_123"
    assert result.job_id == "job-123"
    assert result.redirect_url == "/practice/new?job_id=jd_test_123"
    assert result.has_existing_session is False

    assert len(init_job_calls) == 1
    assert init_job_calls[0][0] == 1
    assert init_job_calls[0][3]["input_data"]["url"] == "job:job-123"
    assert len(scheduled_jobs) == 1
    assert scheduled_jobs[0] == "jd_test_123"
    assert len(mock_orchestrator.queue_manager.enqueued) == 1

