from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...orm import Base

if TYPE_CHECKING:
    from .session import InterviewSession
    from .user import User


class JDGenerationJob(Base):
    __tablename__ = "jd_generation_jobs"
    __table_args__ = (
        Index("idx_jd_jobs_user_id", "user_id"),
        Index("idx_jd_jobs_checksum", "checksum"),
        Index("idx_jd_jobs_status", "status"),
    )

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    stage: Mapped[str] = mapped_column(String(64), nullable=False, default="INITIALIZED")
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("interview_sessions.session_id", ondelete="SET NULL"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    # Relationships
    normalized_jd: Mapped[NormalizedJDRecord | None] = relationship(
        "NormalizedJDRecord", back_populates="job", cascade="all, delete-orphan", uselist=False,
    )
    analysis: Mapped[JobAnalysisRecord | None] = relationship(
        "JobAnalysisRecord", back_populates="job", cascade="all, delete-orphan", uselist=False,
    )
    blueprint: Mapped[InterviewBlueprintRecord | None] = relationship(
        "InterviewBlueprintRecord", back_populates="job", cascade="all, delete-orphan", uselist=False,
    )
    script: Mapped[InterviewScriptRecord | None] = relationship(
        "InterviewScriptRecord", back_populates="job", cascade="all, delete-orphan", uselist=False,
    )


class NormalizedJDRecord(Base):
    __tablename__ = "normalized_jds"
    __table_args__ = (
        Index("idx_normalized_jds_checksum", "checksum"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jd_generation_jobs.job_id", ondelete="CASCADE"), nullable=False, unique=True, index=True,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="vi")
    warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    job: Mapped[JDGenerationJob] = relationship("JDGenerationJob", back_populates="normalized_jd")


class JobAnalysisRecord(Base):
    __tablename__ = "job_analyses"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jd_generation_jobs.job_id", ondelete="CASCADE"), nullable=False, unique=True, index=True,
    )
    job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seniority: Mapped[str] = mapped_column(String(32), nullable=False)
    employment_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    responsibilities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    required_skills: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    preferred_skills: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    technologies: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    domain_knowledge: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    soft_skills: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    technical_signals: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    behavioral_signals: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    job: Mapped[JDGenerationJob] = relationship("JDGenerationJob", back_populates="analysis")


class InterviewBlueprintRecord(Base):
    __tablename__ = "interview_blueprints"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jd_generation_jobs.job_id", ondelete="CASCADE"), nullable=False, unique=True, index=True,
    )
    target_role: Mapped[str] = mapped_column(String(255), nullable=False)
    seniority: Mapped[str] = mapped_column(String(32), nullable=False)
    total_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    target_difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    objectives: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    competencies: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    scoring_dimensions: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    job: Mapped[JDGenerationJob] = relationship("JDGenerationJob", back_populates="blueprint")


class InterviewScriptRecord(Base):
    __tablename__ = "interview_scripts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jd_generation_jobs.job_id", ondelete="CASCADE"), nullable=False, unique=True, index=True,
    )
    script_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=45)
    items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    job: Mapped[JDGenerationJob] = relationship("JDGenerationJob", back_populates="script")
