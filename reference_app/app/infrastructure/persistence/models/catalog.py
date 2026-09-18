from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
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
from .enums import ExperienceLevel, Language, QuestionType, QuestionModerationStatus, QuestionSource

if TYPE_CHECKING:
    from .session import InterviewSession
    from .user import CandidateProfile, User


class JobDomain(Base):
    __tablename__ = "job_domains"

    domain_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    roles: Mapped[list["JobRole"]] = relationship(back_populates="domain")
    questions: Mapped[list["QuestionBank"]] = relationship(back_populates="domain")
    sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="domain")
    profiles_targeting: Mapped[list["CandidateProfile"]] = relationship()


class JobRole(Base):
    __tablename__ = "job_roles"
    __table_args__ = (
        UniqueConstraint("domain_id", "role_name", name="uq_job_roles_domain_role"),
        Index("idx_job_roles_domain_id", "domain_id"),
    )

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job_domains.domain_id", ondelete="CASCADE"), nullable=False,
    )
    role_name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    domain: Mapped["JobDomain"] = relationship(back_populates="roles")
    questions: Mapped[list["QuestionBank"]] = relationship(back_populates="role")
    sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="role")


class StarGuidanceTemplate(Base):
    __tablename__ = "star_guidance_templates"

    star_template_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    situation_guide: Mapped[str | None] = mapped_column(Text)
    task_guide: Mapped[str | None] = mapped_column(Text)
    action_guide: Mapped[str | None] = mapped_column(Text)
    result_guide: Mapped[str | None] = mapped_column(Text)
    language: Mapped[Language] = mapped_column(
        Enum(Language, name="language_enum"), nullable=False, server_default="vi",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    questions: Mapped[list["QuestionBank"]] = relationship(back_populates="star_template")


class QuestionBank(Base):
    __tablename__ = "question_bank"
    __table_args__ = (
        Index("idx_question_bank_domain_role", "domain_id", "role_id"),
        Index("idx_question_bank_language", "language"),
    )

    question_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    domain_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job_domains.domain_id", ondelete="CASCADE"), nullable=False,
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
    question_type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType, name="question_type_enum"), nullable=False,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    star_template_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("star_guidance_templates.star_template_id", ondelete="SET NULL"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="TRUE")
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"),
    )
    moderation_status: Mapped[QuestionModerationStatus] = mapped_column(
        Enum(QuestionModerationStatus, name="question_moderation_status_enum"),
        nullable=False,
        server_default="approved",
        default=QuestionModerationStatus.approved,
    )
    moderated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"),
    )
    moderated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    moderation_reason: Mapped[str | None] = mapped_column(Text)
    source: Mapped[QuestionSource] = mapped_column(
        Enum(QuestionSource, name="question_source_enum"),
        nullable=False,
        server_default="admin_manual",
        default=QuestionSource.admin_manual,
    )
    practice_id: Mapped[int | None] = mapped_column(BigInteger)
    intent: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[int | None] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    domain: Mapped["JobDomain"] = relationship(back_populates="questions")
    role: Mapped["JobRole | None"] = relationship(back_populates="questions")
    star_template: Mapped["StarGuidanceTemplate | None"] = relationship(back_populates="questions")
    creator: Mapped["User | None"] = relationship(back_populates="questions_created", foreign_keys=[created_by])
