from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class PlanOut(BaseModel):
    plan_id: int
    plan_name: str
    price: Decimal
    billing_cycle: str
    feature_limits: dict[str, Any] = Field(default_factory=dict)
    is_active: bool


class CheckoutIn(BaseModel):
    plan_id: int
    payment_gateway: str = "xgate"
    return_url: str | None = None


class CheckoutUrlOut(BaseModel):
    transaction_ref: str
    amount: Decimal
    currency: str = "VND"
    transfer_content: str = ""
    bank_name: str = ""
    account_number: str = ""
    account_name: str = ""
    qr_code_url: str = ""
    payment_url: str = ""


class VerifyPaymentIn(BaseModel):
    transaction_ref: str


class PaymentTransactionOut(BaseModel):
    transaction_id: int
    user_subscription_id: int
    payment_gateway: str
    gateway_transaction_id: str
    amount: Decimal
    currency: str
    status: str
    paid_at: datetime | None = None
    created_at: datetime | None = None


class SubscriptionOut(BaseModel):
    user_subscription_id: int
    user_id: int
    plan_id: int
    status: str
    auto_renew: bool
    start_date: datetime
    end_date: datetime | None = None
    plan: PlanOut | None = None


class VerifyPaymentOut(BaseModel):
    status: str
    message: str
    transaction_ref: str
    subscription: SubscriptionOut | None = None


class QuotaOut(BaseModel):
    has_active_subscription: bool
    plan_name: str
    quota_allowed: bool
    remaining_quota: int
    feature: str


class WebhookResponseOut(BaseModel):
    success: bool
    message: str
