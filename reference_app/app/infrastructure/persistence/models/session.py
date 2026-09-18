from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...orm import Base
from .enums import ExperienceLevel, Language, SessionMode, SessionStatus, TurnSpeaker

if TYPE_CHECKING:
    from .catalog import JobDomain, JobRole, QuestionBank
    from .user import User


class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (
        Index("idx_interview_sessions_candidate_id", "candidate_id"),
        Index("idx_interview_sessions_status", "status"),
    )

    session_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False,
    )
    domain_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("job_domains.domain_id", ondelete="SET NULL"),
    )
    role_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("job_roles.role_id", ondelete="SET NULL"),
    )
    experience_level: Mapped[ExperienceLevel | None] = mapped_column(
        Enum(ExperienceLevel, name="experience_level_enum"),
    )
    language: Mapped[Language] = mapped_column(
        Enum(Language, name="language_enum"), nullable=False, server_default="vi",
    )
    mode: Mapped[SessionMode] = mapped_column(
        Enum(SessionMode, name="session_mode_enum"), nullable=False, server_default="text",
    )
    barge_in_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False,
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status_enum"),
        nullable=False, server_default="in_progress",
    )
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    candidate: Mapped["User"] = relationship(back_populates="sessions")
    domain: Mapped["JobDomain | None"] = relationship(back_populates="sessions")
    role: Mapped["JobRole | None"] = relationship(back_populates="sessions")
    turns: Mapped[list["InterviewTurn"]] = relationship(back_populates="session")
    progress_summary: Mapped["SessionProgressSummary | None"] = relationship(
        back_populates="session", uselist=False,
    )
    pdf_report: Mapped["PdfReport | None"] = relationship(back_populates="session", uselist=False)


class InterviewTurn(Base):
    __tablename__ = "interview_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "turn_number", name="uq_interview_turns_session_turn"),
        Index("idx_interview_turns_session_id", "session_id"),
    )

    turn_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[TurnSpeaker] = mapped_column(
        Enum(TurnSpeaker, name="turn_speaker_enum"), nullable=False,
    )
    question_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("question_bank.question_id", ondelete="SET NULL"),
    )
    message_text: Mapped[str | None] = mapped_column(Text)
    audio_url: Mapped[str | None] = mapped_column(String(500))
    transcribed_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    session: Mapped["InterviewSession"] = relationship(back_populates="turns")
    evaluation: Mapped["AnswerEvaluation | None"] = relationship(
        back_populates="turn", uselist=False,
    )
    speech_analysis: Mapped["SpeechQualityAnalysis | None"] = relationship(
        back_populates="turn", uselist=False,
    )


def _score_check(column: str) -> CheckConstraint:
    return CheckConstraint(f"{column} BETWEEN 0 AND 10", name=f"ck_score_{column}")


class AnswerEvaluation(Base):
    __tablename__ = "answer_evaluations"
    __table_args__ = tuple(
        [_score_check(column) for column in
         ("clarity_score", "logic_score", "example_score", "overall_score")]
    )

    evaluation_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    turn_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview_turns.turn_id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    clarity_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    logic_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    example_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    overall_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    feedback_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    turn: Mapped["InterviewTurn"] = relationship(back_populates="evaluation")


class SpeechQualityAnalysis(Base):
    __tablename__ = "speech_quality_analysis"

    analysis_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    turn_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview_turns.turn_id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    speaking_pace: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    hesitation_count: Mapped[int | None] = mapped_column(Integer, server_default="0")
    filler_word_count: Mapped[int | None] = mapped_column(Integer, server_default="0")
    tips_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    turn: Mapped["InterviewTurn"] = relationship(back_populates="speech_analysis")


class SessionProgressSummary(Base):
    __tablename__ = "session_progress_summary"
    __table_args__ = (
        Index("idx_session_progress_summary_candidate_id", "candidate_id"),
    )

    summary_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview_sessions.session_id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    candidate_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False,
    )
    avg_clarity_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    avg_logic_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    avg_example_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    avg_overall_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    total_turns: Mapped[int | None] = mapped_column(Integer, server_default="0")
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    session: Mapped["InterviewSession"] = relationship(back_populates="progress_summary")


class PdfReport(Base):
    __tablename__ = "pdf_reports"

    report_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview_sessions.session_id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    session: Mapped["InterviewSession"] = relationship(back_populates="pdf_report")
