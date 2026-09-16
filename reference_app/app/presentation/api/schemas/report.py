from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PdfReportMetaOut(BaseModel):
    session_id: int
    file_url: str
    generated_at: datetime | None = None
