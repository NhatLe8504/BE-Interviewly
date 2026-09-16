from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import pytest

from app.domain.billing import PaymentTransaction, SubscriptionPlan, UserSubscription
from app.domain.errors import DomainValidationError


def test_subscription_plan_valid():
    plan = SubscriptionPlan(
        plan_name="Pro Monthly",
        price=Decimal("99000"),
        billing_cycle="monthly",
        feature_limits={"interviews": 30},
    )
    assert plan.plan_name == "Pro Monthly"
    assert plan.price == Decimal("99000")
    assert plan.billing_cycle == "monthly"
    assert plan.feature_limits == {"interviews": 30}


def test_subscription_plan_negative_price():
    with pytest.raises(DomainValidationError, match="price must be non-negative"):
        SubscriptionPlan(plan_name="Invalid", price=Decimal("-1000"))


def test_subscription_plan_blank_name():
    with pytest.raises(DomainValidationError, match="plan_name must not be blank"):
        SubscriptionPlan(plan_name="   ", price=Decimal("0"))


def test_subscription_plan_invalid_cycle():
    with pytest.raises(DomainValidationError, match="invalid billing_cycle"):
        SubscriptionPlan(plan_name="Pro", price=Decimal("100"), billing_cycle="daily")


def test_user_subscription_lifecycle():
    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    sub = UserSubscription(
        user_id=1,
        plan_id=2,
        status="active",
        start_date=datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc),
        end_date=datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc),
    )
    assert sub.is_active(now) is True

    later = datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc)
    assert sub.is_active(later) is False

    cancelled = UserSubscription(
        user_id=1,
        plan_id=2,
        status="cancelled",
    )
    assert cancelled.is_active(now) is False


def test_user_subscription_invalid_user_id():
    with pytest.raises(DomainValidationError, match="user_id must be positive"):
        UserSubscription(user_id=0, plan_id=1)


def test_payment_transaction_validation():
    tx = PaymentTransaction(
        user_subscription_id=1,
        payment_gateway="vnpay",
        gateway_transaction_id="VNP123456",
        amount=Decimal("99000"),
        status="pending",
    )
    assert tx.amount == Decimal("99000")
    assert tx.status == "pending"

    with pytest.raises(DomainValidationError, match="amount must be non-negative"):
        PaymentTransaction(
            user_subscription_id=1,
            payment_gateway="vnpay",
            gateway_transaction_id="VNP1",
            amount=Decimal("-50"),
        )

    with pytest.raises(DomainValidationError, match="invalid payment status"):
        PaymentTransaction(
            user_subscription_id=1,
            payment_gateway="vnpay",
            gateway_transaction_id="VNP1",
            amount=Decimal("100"),
            status="unknown",
        )
