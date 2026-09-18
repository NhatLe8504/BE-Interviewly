from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...orm import Base
from .enums import ExperienceLevel, Language, UserRole, UserStatus

if TYPE_CHECKING:
    from .billing import UserSubscription
    from .catalog import QuestionBank
    from .session import InterviewSession
    from .system import AuditLog, ModerationLog


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"), nullable=False,
        server_default="candidate",
    )
    preferred_language: Mapped[Language] = mapped_column(
        Enum(Language, name="language_enum"), nullable=False, server_default="vi",
    )
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status_enum"), nullable=False, server_default="active",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    profile: Mapped["CandidateProfile | None"] = relationship(back_populates="user", uselist=False)
    sessions: Mapped[list["InterviewSession"]] = relationship(back_populates="candidate")
    subscriptions: Mapped[list["UserSubscription"]] = relationship(back_populates="user")
    questions_created: Mapped[list["QuestionBank"]] = relationship(back_populates="creator", foreign_keys="[QuestionBank.created_by]")
    moderation_actions: Mapped[list["ModerationLog"]] = relationship(back_populates="admin")
    audit_entries: Mapped[list["AuditLog"]] = relationship(back_populates="user")


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True,
    )
    experience_level: Mapped[ExperienceLevel | None] = mapped_column(
        Enum(ExperienceLevel, name="experience_level_enum"),
    )
    target_domain_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("job_domains.domain_id", ondelete="SET NULL"),
    )
    bio: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="profile")
