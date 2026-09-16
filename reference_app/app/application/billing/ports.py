from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class StoredSubscriptionPlan:
    plan_id: int
    plan_name: str
    price: Decimal
    billing_cycle: str
    feature_limits: dict[str, Any]
    is_active: bool
    created_at: datetime | None = None


@dataclass(frozen=True)
class StoredUserSubscription:
    user_subscription_id: int
    user_id: int
    plan_id: int
    status: str
    auto_renew: bool
    start_date: datetime
    end_date: datetime | None
    created_at: datetime | None = None
    plan: StoredSubscriptionPlan | None = None


@dataclass(frozen=True)
class StoredPaymentTransaction:
    transaction_id: int
    user_subscription_id: int
    payment_gateway: str
    gateway_transaction_id: str
    amount: Decimal
    currency: str
    status: str
    paid_at: datetime | None
    created_at: datetime | None = None


@dataclass(frozen=True)
class PaymentInitResult:
    transaction_ref: str
    payment_url: str
    amount: Decimal
    currency: str


class SubscriptionRepoPort(Protocol):
    def list_active_plans(self, session: Any) -> list[StoredSubscriptionPlan]:
        ...

    def get_plan_by_id(self, session: Any, plan_id: int) -> StoredSubscriptionPlan | None:
        ...

    def get_active_subscription(
        self, session: Any, user_id: int
    ) -> StoredUserSubscription | None:
        ...

    def create_subscription(
        self,
        session: Any,
        *,
        user_id: int,
        plan_id: int,
        status: str = "active",
        auto_renew: bool = False,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> StoredUserSubscription:
        ...

    def update_subscription(
        self,
        session: Any,
        user_subscription_id: int,
        *,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        plan_id: int | None = None,
    ) -> StoredUserSubscription:
        ...


class PaymentTransactionRepoPort(Protocol):
    def create_transaction(
        self,
        session: Any,
        *,
        user_subscription_id: int,
        payment_gateway: str,
        gateway_transaction_id: str,
        amount: Decimal,
        currency: str = "VND",
        status: str = "pending",
    ) -> StoredPaymentTransaction:
        ...

    def get_by_gateway_ref(
        self,
        session: Any,
        payment_gateway: str,
        gateway_transaction_id: str,
    ) -> StoredPaymentTransaction | None:
        ...

    def get_by_id(
        self, session: Any, transaction_id: int
    ) -> StoredPaymentTransaction | None:
        ...

    def update_status(
        self,
        session: Any,
        transaction_id: int,
        *,
        status: str,
        paid_at: datetime | None = None,
    ) -> StoredPaymentTransaction:
        ...

    def list_by_user(
        self, session: Any, user_id: int, limit: int = 50
    ) -> list[StoredPaymentTransaction]:
        ...


class PaymentGatewayPort(Protocol):
    def generate_payment_url(
        self,
        *,
        transaction_ref: str,
        amount: Decimal,
        order_info: str,
        ip_address: str,
        return_url: str | None = None,
    ) -> str:
        ...

    def verify_response(
        self, params: dict[str, Any]
    ) -> tuple[bool, str, str, Decimal]:
        """Returns (is_valid, txn_ref, status_code, amount)."""
        ...
