from __future__ import annotations

import pathlib
from typing import Any

from ...domain.errors import NotFoundError
from .ports import InterviewSessionReportData, PdfReportGeneratorPort, SessionDataRepoPort


class PdfReportService:
    def __init__(
        self,
        generator: PdfReportGeneratorPort,
        repo: SessionDataRepoPort,
        storage_dir: pathlib.Path,
    ) -> None:
        self.generator = generator
        self.repo = repo
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def generate_and_store(self, session: Any, session_id: int) -> tuple[bytes, str]:
        data = self.repo.get_session_report_data(session, session_id)
        if data is None:
            raise NotFoundError(f"interview session {session_id} not found")
        pdf_bytes = self.generator.generate(data)
        filename = f"session_{session_id}_report.pdf"
        file_path = self.storage_dir / filename
        file_path.write_bytes(pdf_bytes)
        file_url = f"/reports/{filename}"
        self.repo.save_pdf_report_meta(session, session_id, file_url)
        return pdf_bytes, filename

    def get_pdf(self, session: Any, session_id: int) -> tuple[bytes, str]:
        filename = f"session_{session_id}_report.pdf"
        file_path = self.storage_dir / filename
        if file_path.exists():
            return file_path.read_bytes(), filename
        return self.generate_and_store(session, session_id)
