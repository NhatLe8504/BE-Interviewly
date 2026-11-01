from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import pytest

from app.application.billing.commands import CheckQuotaCommand, CreateCheckoutCommand, VerifyPaymentCommand
from app.application.billing.ports import StoredSubscriptionPlan, StoredUserSubscription
from app.application.billing.service import PaymentService, SubscriptionService
from app.infrastructure.persistence.models.enums import BillingCycle


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class MockSubscriptionRepo:
    def __init__(self):
        self.plans = {
            1: StoredSubscriptionPlan(1, "Free", Decimal("0"), "free", {"type": "subscription", "voice_minutes": 15, "cv_generations": 1}, True),
            2: StoredSubscriptionPlan(2, "Pro Monthly", Decimal("99000"), "monthly", {"type": "subscription", "voice_minutes": 300, "cv_generations": 15}, True),
            3: StoredSubscriptionPlan(3, "Pro Yearly", Decimal("899000"), "yearly", {"type": "subscription", "voice_minutes": 4000, "cv_generations": 200}, True),
            4: StoredSubscriptionPlan(4, "Sprint 7 Ngày", Decimal("49000"), "weekly", {"type": "subscription", "voice_minutes": 60, "cv_generations": 3}, True),
            101: StoredSubscriptionPlan(101, "Add-on Voice 30m", Decimal("29000"), "monthly", {"type": "addon", "addon_type": "voice", "voice_minutes": 30}, True),
            104: StoredSubscriptionPlan(104, "Add-on CV 3x", Decimal("19000"), "monthly", {"type": "addon", "addon_type": "cv", "cv_generations": 3}, True),
        }
        self.subscriptions = {}
        self.balances = {}
        self._counter = 1

    def get_plan_by_id(self, session, plan_id):
        return self.plans.get(plan_id)

    def get_active_subscription(self, session, user_id):
        for s in self.subscriptions.values():
            if s.user_id == user_id and s.status == "active":
                return s
        return None

    def get_subscription_by_id(self, session, sub_id):
        return self.subscriptions.get(sub_id)

    def create_subscription(self, session, **kwargs):
        sub_id = self._counter
        self._counter += 1
        plan = self.plans.get(kwargs["plan_id"])
        sub = StoredUserSubscription(
            user_subscription_id=sub_id,
            user_id=kwargs["user_id"],
            plan_id=kwargs["plan_id"],
            status=kwargs.get("status", "active"),
            auto_renew=kwargs.get("auto_renew", False),
            start_date=kwargs.get("start_date", datetime.now(timezone.utc)),
            end_date=kwargs.get("end_date"),
            plan=plan,
        )
        self.subscriptions[sub_id] = sub
        return sub

    def update_subscription(self, session, sub_id, **kwargs):
        sub = self.subscriptions[sub_id]
        new_sub = StoredUserSubscription(
            user_subscription_id=sub.user_subscription_id,
            user_id=sub.user_id,
            plan_id=kwargs.get("plan_id", sub.plan_id),
            status=kwargs.get("status", sub.status),
            auto_renew=sub.auto_renew,
            start_date=kwargs.get("start_date", sub.start_date),
            end_date=kwargs.get("end_date", sub.end_date),
            plan=self.plans.get(kwargs.get("plan_id", sub.plan_id)),
        )
        self.subscriptions[sub_id] = new_sub
        return new_sub

    def get_or_create_usage_balance(self, session, user_id, default_voice_minutes=15, default_cv_generations=1):
        if user_id not in self.balances:
            class Dummy:
                pass
            b = Dummy()
            b.voice_minutes_quota = default_voice_minutes
            b.voice_minutes_addon = 0
            b.voice_minutes_used = 0
            b.cv_generations_quota = default_cv_generations
            b.cv_generations_addon = 0
            b.cv_generations_used = 0
            self.balances[user_id] = b
        return self.balances[user_id]

    def update_plan_balance(self, session, user_id, voice_minutes, cv_generations):
        b = self.get_or_create_usage_balance(session, user_id)
        b.voice_minutes_quota = voice_minutes
        b.voice_minutes_used = 0
        b.cv_generations_quota = cv_generations
        b.cv_generations_used = 0
        return b

    def add_addon_balance(self, session, user_id, addon_type, amount):
        b = self.get_or_create_usage_balance(session, user_id)
        if addon_type == "voice":
            b.voice_minutes_addon += amount
        elif addon_type == "cv":
            b.cv_generations_addon += amount
        return b

    def deduct_voice_minutes(self, session, user_id, minutes):
        b = self.get_or_create_usage_balance(session, user_id)
        total = b.voice_minutes_quota + b.voice_minutes_addon
        remaining = max(0, total - b.voice_minutes_used)
        if remaining < minutes:
            return False
        b.voice_minutes_used += minutes
        return True

    def deduct_cv_generation(self, session, user_id):
        b = self.get_or_create_usage_balance(session, user_id)
        total = b.cv_generations_quota + b.cv_generations_addon
        remaining = max(0, total - b.cv_generations_used)
        if remaining < 1:
            return False
        b.cv_generations_used += 1
        return True

    def refund_cv_generation(self, session, user_id):
        b = self.get_or_create_usage_balance(session, user_id)
        b.cv_generations_used = max(0, b.cv_generations_used - 1)


class MockTxRepo:
    def __init__(self):
        self.txs = {}
        self._c = 1

    def create_transaction(self, session, **kwargs):
        from app.application.billing.ports import StoredPaymentTransaction
        tx_id = self._c
        self._c += 1
        tx = StoredPaymentTransaction(
            transaction_id=tx_id,
            user_subscription_id=kwargs["user_subscription_id"],
            payment_gateway=kwargs["payment_gateway"],
            gateway_transaction_id=kwargs["gateway_transaction_id"],
            amount=kwargs["amount"],
            currency=kwargs.get("currency", "VND"),
            status=kwargs.get("status", "pending"),
            paid_at=None,
        )
        self.txs[tx.gateway_transaction_id] = tx
        return tx

    def get_by_gateway_ref(self, session, gateway, ref):
        return self.txs.get(ref)

    def update_status(self, session, tx_id, status, paid_at=None):
        for k, t in list(self.txs.items()):
            if t.transaction_id == tx_id:
                new_t = dataclasses.replace(t, status=status, paid_at=paid_at)
                self.txs[k] = new_t
                return new_t


class MockGateway:
    def generate_payment_info(self, **kwargs):
        ref = kwargs["transaction_ref"]
        return {
            "transfer_content": ref,
            "bank_name": "mb",
            "account_number": "9394441571",
            "account_name": "LE VAN NHAT",
            "qr_code_url": f"https://img.vietqr.io/image/mb-9394441571-compact2.png?addInfo={ref}",
            "payment_url": "",
        }

    def verify_transaction(self, **kwargs):
        return True, "TX_MOCK_1", kwargs.get("expected_amount")


def test_sprint_7_days_activation():
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    clock = FakeClock(now)
    sub_repo = MockSubscriptionRepo()
    tx_repo = MockTxRepo()
    gateway = MockGateway()
    svc = PaymentService(sub_repo, tx_repo, gateway, clock)

    init_res = svc.create_checkout(None, CreateCheckoutCommand(user_id=1, plan_id=4))
    assert init_res.transaction_ref.startswith("IC")

    verify_res = svc.verify_payment(None, VerifyPaymentCommand(user_id=1, transaction_ref=init_res.transaction_ref))
    assert verify_res["status"] == "success"
    sub = verify_res["subscription"]
    assert sub.status == "active"
    # Sprint MUST be 7 days
    assert sub.end_date == now + timedelta(days=7)
    # Balance must be initialized with 60 voice minutes and 3 CVs
    balance = sub_repo.get_or_create_usage_balance(None, 1)
    assert balance.voice_minutes_quota == 60
    assert balance.cv_generations_quota == 3


def test_addon_purchase_credits_balance():
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    clock = FakeClock(now)
    sub_repo = MockSubscriptionRepo()
    tx_repo = MockTxRepo()
    gateway = MockGateway()
    svc = PaymentService(sub_repo, tx_repo, gateway, clock)

    # 1. User on Sprint (60m)
    c1 = svc.create_checkout(None, CreateCheckoutCommand(user_id=2, plan_id=4))
    svc.verify_payment(None, VerifyPaymentCommand(user_id=2, transaction_ref=c1.transaction_ref))
    b = sub_repo.get_or_create_usage_balance(None, 2)
    assert b.voice_minutes_quota == 60
    assert b.voice_minutes_addon == 0

    # 2. Buy Addon Voice 30m (plan_id = 101)
    c2 = svc.create_checkout(None, CreateCheckoutCommand(user_id=2, plan_id=101))
    v2 = svc.verify_payment(None, VerifyPaymentCommand(user_id=2, transaction_ref=c2.transaction_ref))
    assert v2["status"] == "success"
    b_after = sub_repo.get_or_create_usage_balance(None, 2)
    assert b_after.voice_minutes_addon == 30
    assert (b_after.voice_minutes_quota + b_after.voice_minutes_addon) == 90


def test_deduction_and_refund():
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    clock = FakeClock(now)
    sub_repo = MockSubscriptionRepo()
    sub_svc = SubscriptionService(sub_repo, clock)

    # Deduct 145 seconds = ceil(145/60) = 3 minutes
    res = sub_svc.deduct_voice_minutes(None, user_id=3, duration_seconds=145)
    assert res["success"] is True
    assert res["remaining"] == 12 # 15 - 3 = 12

    # Deduct 1 CV
    res_cv = sub_svc.deduct_cv_generation(None, user_id=3)
    assert res_cv["success"] is True
    assert res_cv["remaining"] == 0 # 1 - 1 = 0

    # Next CV deduction should fail (0 remaining)
    res_cv_fail = sub_svc.deduct_cv_generation(None, user_id=3)
    assert res_cv_fail["success"] is False

    # Refund CV on failed job
    res_refund = sub_svc.refund_cv_generation(None, user_id=3)
    assert res_refund["remaining"] == 1
