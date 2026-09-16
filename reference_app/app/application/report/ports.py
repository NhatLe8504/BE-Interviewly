from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class TurnFeedbackData:
    turn_number: int
    question: str
    answer: str
    clarity_score: Decimal | None = None
    logic_score: Decimal | None = None
    example_score: Decimal | None = None
    overall_score: Decimal | None = None
    feedback_text: str | None = None
    speaking_pace: Decimal | None = None
    filler_word_count: int | None = None


@dataclass(frozen=True)
class InterviewSessionReportData:
    session_id: int
    candidate_name: str
    candidate_email: str
    job_role: str
    job_domain: str
    total_score: Decimal | None
    avg_clarity_score: Decimal | None
    avg_logic_score: Decimal | None
    avg_example_score: Decimal | None
    started_at: datetime
    completed_at: datetime | None
    turns: list[TurnFeedbackData] = field(default_factory=list)


class PdfReportGeneratorPort(Protocol):
    def generate(self, data: InterviewSessionReportData) -> bytes:
        ...


class SessionDataRepoPort(Protocol):
    def get_session_report_data(
        self, session: Any, session_id: int,
    ) -> InterviewSessionReportData | None:
        ...

    def save_pdf_report_meta(
        self, session: Any, session_id: int, file_url: str,
    ) -> None:
        ...

    def get_pdf_report_meta(
        self, session: Any, session_id: int,
    ) -> str | None:
        ...
