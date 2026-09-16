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
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ...orm import Base
from .enums import BillingCycle, PaymentStatus, SubStatus

if TYPE_CHECKING:
    from .user import User


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    plan_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, server_default="0")
    billing_cycle: Mapped[BillingCycle] = mapped_column(
        Enum(BillingCycle, name="billing_cycle_enum"),
        nullable=False, server_default="free",
    )
    feature_limits: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="TRUE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    subscriptions: Mapped[list["UserSubscription"]] = relationship(back_populates="plan")


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"
    __table_args__ = (
        Index("idx_user_subscriptions_user_id", "user_id"),
        Index("idx_user_subscriptions_status", "status"),
    )

    user_subscription_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False,
    )
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscription_plans.plan_id"), nullable=False,
    )
    status: Mapped[SubStatus] = mapped_column(
        Enum(SubStatus, name="sub_status_enum"), nullable=False, server_default="active",
    )
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="FALSE")
    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="subscriptions")
    plan: Mapped["SubscriptionPlan"] = relationship(back_populates="subscriptions")
    transactions: Mapped[list["PaymentTransaction"]] = relationship(back_populates="subscription")


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint(
            "payment_gateway", "gateway_transaction_id",
            name="uq_payment_gateway_txn",
        ),
        Index("idx_payment_transactions_user_subscription_id", "user_subscription_id"),
    )

    transaction_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
    )
    user_subscription_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("user_subscriptions.user_subscription_id", ondelete="CASCADE"),
        nullable=False,
    )
    payment_gateway: Mapped[str] = mapped_column(String(50), nullable=False)
    gateway_transaction_id: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, server_default="VND")
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status_enum"),
        nullable=False, server_default="pending",
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    subscription: Mapped["UserSubscription"] = relationship(back_populates="transactions")
