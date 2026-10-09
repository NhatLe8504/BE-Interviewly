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
