from __future__ import annotations

from datetime import datetime
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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...orm import Base

if TYPE_CHECKING:
    from .user import User
    from .job_aggregator import JobPostingRecord


class CvDocumentRecord(Base):
    __tablename__ = "cv_documents"
    __table_args__ = (
        Index("idx_cv_documents_user_id", "user_id"),
        Index("idx_cv_documents_target_job_id", "target_job_id"),
        Index("idx_cv_documents_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    target_job_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("job_postings.job_id", ondelete="SET NULL"), nullable=True
    )
    template_id: Mapped[str] = mapped_column(String(50), nullable=False, default="modern_tech")
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="My Professional CV")
    color_theme: Mapped[str] = mapped_column(String(50), nullable=False, default="navy")
    font_family: Mapped[str] = mapped_column(String(50), nullable=False, default="inter")

    personal_info: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_experiences: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    projects: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    skills: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    educations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    certifications: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    section_order: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: ["summary", "experience", "projects", "skills", "education", "certifications"],
    )

    ats_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    ats_feedback: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship("User", backref="cv_documents")
    target_job: Mapped[JobPostingRecord | None] = relationship(
        "JobPostingRecord", backref="targeted_cvs"
    )
