from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...orm import Base

if TYPE_CHECKING:
    from .user import User


class OnboardingResponse(Base):
    __tablename__ = "onboarding_responses"
    __table_args__ = (
        Index("idx_onboarding_user_id", "user_id"),
        Index("idx_onboarding_channel", "acquisition_channel"),
        Index("idx_onboarding_domain", "current_domain"),
    )

    response_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), unique=True, nullable=True
    )
    preferred_language: Mapped[str] = mapped_column(String(10), nullable=False, default="vi")
    acquisition_channel: Mapped[str] = mapped_column(String(50), nullable=False, default="other")
    current_domain: Mapped[str] = mapped_column(String(150), nullable=False)
    current_role: Mapped[str] = mapped_column(String(150), nullable=False)
    target_role: Mapped[str] = mapped_column(String(150), nullable=False)
    target_level: Mapped[str] = mapped_column(String(50), nullable=False, default="junior")
    target_goal: Mapped[str | None] = mapped_column(Text)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User | None"] = relationship(back_populates="onboarding")