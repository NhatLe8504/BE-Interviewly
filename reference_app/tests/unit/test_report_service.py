from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import pytest

from app.application.report.ports import InterviewSessionReportData
from app.application.report.service import PdfReportService
from app.domain.errors import NotFoundError


class FakePdfGenerator:
    def generate(self, data: InterviewSessionReportData) -> bytes:
        return b"%PDF-1.4 Fake PDF Content"


class FakeSessionDataRepo:
    def __init__(self) -> None:
        self.sessions: dict[int, InterviewSessionReportData] = {}
        self.meta: dict[int, str] = {}

    def get_session_report_data(self, session: Any, session_id: int):
        return self.sessions.get(session_id)

    def save_pdf_report_meta(self, session: Any, session_id: int, file_url: str):
        self.meta[session_id] = file_url

    def get_pdf_report_meta(self, session: Any, session_id: int):
        return self.meta.get(session_id)


def test_pdf_report_service_generate(tmp_path):
    repo = FakeSessionDataRepo()
    repo.sessions[1] = InterviewSessionReportData(
        session_id=1,
        candidate_name="Test User",
        candidate_email="test@example.com",
        job_role="Engineer",
        job_domain="Tech",
        total_score=Decimal("8.0"),
        avg_clarity_score=Decimal("8.0"),
        avg_logic_score=Decimal("8.0"),
        avg_example_score=Decimal("8.0"),
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    svc = PdfReportService(generator=FakePdfGenerator(), repo=repo, storage_dir=tmp_path)

    pdf_bytes, filename = svc.generate_and_store(None, 1)
    assert pdf_bytes == b"%PDF-1.4 Fake PDF Content"
    assert filename == "session_1_report.pdf"
    assert (tmp_path / filename).exists()
    assert repo.meta[1] == "/reports/session_1_report.pdf"

    # Subsequent get_pdf reads cached file
    cached_bytes, cached_name = svc.get_pdf(None, 1)
    assert cached_bytes == pdf_bytes
    assert cached_name == filename


def test_pdf_report_service_not_found(tmp_path):
    repo = FakeSessionDataRepo()
    svc = PdfReportService(generator=FakePdfGenerator(), repo=repo, storage_dir=tmp_path)
    with pytest.raises(NotFoundError):
        svc.generate_and_store(None, 999)
