from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...orm import Base

if TYPE_CHECKING:
    from .user import User


class UserSkillEvidenceRecord(Base):
    __tablename__ = "user_skill_evidence"
    __table_args__ = (
        UniqueConstraint("source_type", "source_id", "skill_id", name="uq_user_skill_evidence_source_skill"),
        Index("idx_user_skill_evidence_user_skill", "user_id", "skill_id"),
        Index("idx_user_skill_evidence_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False,
    )
    skill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    question_difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    score: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    grader_confidence: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0.80"))
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    rubric_scores: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    flags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class UserSkillLevelRecord(Base):
    __tablename__ = "user_skill_levels"
    __table_args__ = (
        Index("idx_user_skill_levels_user_id", "user_id"),
        Index("idx_user_skill_levels_level", "level"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True,
    )
    skill_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ability_score: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("1.00"))
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0.00"))
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_difficulty_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_evidence_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class UserCareerProfileRecord(Base):
    __tablename__ = "user_career_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True,
    )
    primary_role_track: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    secondary_role_track: Mapped[str | None] = mapped_column(String(50), nullable=True)
    role_confidence: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=Decimal("0.00"))
    overall_level: Mapped[str] = mapped_column(String(20), nullable=False, default="none")
    top_skills: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    weak_skills: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )


class JobReadinessRecord(Base):
    __tablename__ = "job_readiness_checks"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_job_readiness_user_job"),
        Index("idx_job_readiness_user_id", "user_id"),
        Index("idx_job_readiness_job_id", "job_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False,
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("job_postings.job_id", ondelete="CASCADE"), nullable=False,
    )
    match_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    data_coverage: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    requirements_breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class PracticeEvaluationRecord(Base):
    """Đánh giá do SERVER tạo cho một câu trả lời luyện tập.

    Đây là nguồn bằng chứng duy nhất cho module luyện tập: điểm phải do backend
    tạo ra (LLM evaluator), gắn user + câu hỏi, kèm chính văn bản câu trả lời.
    Điểm do client gửi lên (practice_history.questions_summary[].score) không
    bao giờ được dùng làm bằng chứng.
    """

    __tablename__ = "practice_evaluations"
    __table_args__ = (
        Index("idx_practice_evaluations_user_question", "user_id", "question_id"),
        Index("idx_practice_evaluations_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False,
    )
    question_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("question_bank.question_id", ondelete="CASCADE"), nullable=False,
    )
    # "content" = đánh giá nội dung câu trả lời (quiz đã xác minh + tự luận LLM)
    # "voice"   = đánh giá nội dung + độ luyến láy khi nói (LLM voice evaluator)
    part: Mapped[str] = mapped_column(String(16), nullable=False)
    part_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    part_max: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False, default="llm")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
