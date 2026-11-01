from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select

from ...application.report.ports import InterviewSessionReportData, TurnFeedbackData
from .analytics_repository import SqlAlchemyAnalyticsRepository
from .models.session import (
    InterviewSession,
    PdfReport,
)


class SqlAlchemySessionReportRepository:
    def get_session_report_data(
        self, session: Any, session_id: int,
    ) -> InterviewSessionReportData | None:
        sess_row = session.get(InterviewSession, session_id)
        if sess_row is None:
            return None

        candidate = sess_row.candidate
        cand_name = candidate.full_name if candidate else "Ứng viên"
        cand_email = candidate.email if candidate else ""
        role_name = sess_row.role.role_name if sess_row.role else "Chung"
        domain_name = sess_row.domain.domain_name if sess_row.domain else "Chung"

        result = SqlAlchemyAnalyticsRepository().get_session_result(session, sess_row.candidate_id, session_id)
        if result is None:
            return None
        avg_clarity = Decimal(str(result.clarity_score / 10)) if result.clarity_score is not None else None
        avg_logic = Decimal(str(result.structure_score / 10)) if result.structure_score is not None else None
        avg_example = Decimal(str(result.evidence_score / 10)) if result.evidence_score is not None else None
        total_score = Decimal(str(result.total_score / 10)) if result.total_score is not None else None
        details = {turn.turn_id: turn for turn in result.turns}

        turns_data: list[TurnFeedbackData] = []
        last_question = ""
        for t in sorted(sess_row.turns or [], key=lambda x: x.turn_number):
            ev = t.evaluation
            sp = t.speech_analysis
            detail = details[t.turn_id]
            is_candidate = getattr(t.speaker, "value", t.speaker) == "candidate"
            if not is_candidate and t.message_text:
                last_question = t.message_text
            turns_data.append(
                TurnFeedbackData(
                    turn_number=t.turn_number,
                    question=(last_question or f"Lượt trả lời {t.turn_number}") if is_candidate else (t.message_text or f"Câu hỏi {t.turn_number}"),
                    answer=t.transcribed_text or (t.message_text if is_candidate else "") or "",
                    clarity_score=Decimal(str(ev.clarity_score)) if ev and ev.clarity_score is not None else None,
                    logic_score=Decimal(str(ev.logic_score)) if ev and ev.logic_score is not None else None,
                    example_score=Decimal(str(ev.example_score)) if ev and ev.example_score is not None else None,
                    overall_score=Decimal(str(ev.overall_score)) if ev and ev.overall_score is not None else None,
                    feedback_text=detail.feedback_text,
                    speaking_pace=Decimal(str(sp.speaking_pace)) if sp and sp.speaking_pace is not None else None,
                    filler_word_count=sp.filler_word_count if sp else None,
                )
            )

        return InterviewSessionReportData(
            session_id=sess_row.session_id,
            candidate_name=cand_name,
            candidate_email=cand_email,
            job_role=role_name,
            job_domain=domain_name,
            total_score=total_score,
            avg_clarity_score=avg_clarity,
            avg_logic_score=avg_logic,
            avg_example_score=avg_example,
            started_at=sess_row.started_at,
            completed_at=sess_row.completed_at,
            turns=turns_data,
        )

    def save_pdf_report_meta(
        self, session: Any, session_id: int, file_url: str,
    ) -> None:
        existing = session.execute(
            select(PdfReport).where(PdfReport.session_id == session_id)
        ).scalar_one_or_none()
        if existing:
            existing.file_url = file_url
        else:
            rep = PdfReport(session_id=session_id, file_url=file_url)
            session.add(rep)
        session.commit()

    def get_pdf_report_meta(
        self, session: Any, session_id: int,
    ) -> str | None:
        existing = session.execute(
            select(PdfReport).where(PdfReport.session_id == session_id)
        ).scalar_one_or_none()
        return existing.file_url if existing else None
