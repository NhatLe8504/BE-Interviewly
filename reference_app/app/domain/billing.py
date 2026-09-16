from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from .errors import DomainValidationError

VALID_BILLING_CYCLES = {"free", "monthly", "yearly"}
VALID_SUB_STATUSES = {"active", "expired", "cancelled"}
VALID_PAYMENT_STATUSES = {"pending", "success", "failed", "refunded"}


@dataclass(frozen=True)
class SubscriptionPlan:
    plan_name: str
    price: Decimal
    billing_cycle: str = "monthly"
    feature_limits: dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    plan_id: int | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.plan_name or not self.plan_name.strip():
            raise DomainValidationError("plan_name must not be blank")
        if not isinstance(self.price, Decimal):
            try:
                object.__setattr__(self, "price", Decimal(str(self.price)))
            except Exception:
                raise DomainValidationError("invalid price")
        if self.price < Decimal("0"):
            raise DomainValidationError("price must be non-negative")
        if self.billing_cycle not in VALID_BILLING_CYCLES:
            raise DomainValidationError(f"invalid billing_cycle: {self.billing_cycle}")


@dataclass(frozen=True)
class UserSubscription:
    user_id: int
    plan_id: int
    status: str = "active"
    auto_renew: bool = False
    start_date: datetime | None = None
    end_date: datetime | None = None
    user_subscription_id: int | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise DomainValidationError("user_id must be positive")
        if self.plan_id <= 0:
            raise DomainValidationError("plan_id must be positive")
        if self.status not in VALID_SUB_STATUSES:
            raise DomainValidationError(f"invalid status: {self.status}")

    def is_active(self, now: datetime) -> bool:
        if self.status != "active":
            return False
        if self.end_date is not None and now > self.end_date:
            return False
        return True


@dataclass(frozen=True)
class PaymentTransaction:
    user_subscription_id: int
    payment_gateway: str
    gateway_transaction_id: str
    amount: Decimal
    currency: str = "VND"
    status: str = "pending"
    paid_at: datetime | None = None
    transaction_id: int | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.user_subscription_id <= 0:
            raise DomainValidationError("user_subscription_id must be positive")
        if not self.payment_gateway or not self.payment_gateway.strip():
            raise DomainValidationError("payment_gateway must not be blank")
        if not self.gateway_transaction_id or not self.gateway_transaction_id.strip():
            raise DomainValidationError("gateway_transaction_id must not be blank")
        if not isinstance(self.amount, Decimal):
            try:
                object.__setattr__(self, "amount", Decimal(str(self.amount)))
            except Exception:
                raise DomainValidationError("invalid amount")
        if self.amount < Decimal("0"):
            raise DomainValidationError("amount must be non-negative")
        if self.status not in VALID_PAYMENT_STATUSES:
            raise DomainValidationError(f"invalid payment status: {self.status}")
