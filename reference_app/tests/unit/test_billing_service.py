from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import pytest

from app.application.billing.commands import CheckQuotaCommand, CreateCheckoutCommand, VerifyPaymentCommand
from app.application.billing.ports import (
    StoredPaymentTransaction,
    StoredSubscriptionPlan,
    StoredUserSubscription,
)
from app.application.billing.service import PaymentService, SubscriptionService
from app.application.common import ClockPort
from app.domain.errors import DomainValidationError, NotFoundError


class FakeClock(ClockPort):
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeSubscriptionRepo:
    def __init__(self) -> None:
        self.plans = {
            1: StoredSubscriptionPlan(1, "Free", Decimal("0"), "free", {"turns": 5}, True),
            2: StoredSubscriptionPlan(2, "Pro Monthly", Decimal("99000"), "monthly", {"turns": 100}, True),
            3: StoredSubscriptionPlan(3, "Pro Inactive", Decimal("50000"), "monthly", {}, False),
        }
        self.subscriptions: dict[int, StoredUserSubscription] = {}
        self._sub_counter = 1

    def list_active_plans(self, session: Any):
        return [p for p in self.plans.values() if p.is_active]

    def get_plan_by_id(self, session: Any, plan_id: int):
        return self.plans.get(plan_id)

    def get_active_subscription(self, session: Any, user_id: int):
        for s in self.subscriptions.values():
            if s.user_id == user_id and s.status == "active":
                return s
        return None

    def create_subscription(self, session: Any, **kwargs):
        sub_id = self._sub_counter
        self._sub_counter += 1
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

    def update_subscription(self, session: Any, user_subscription_id: int, **kwargs):
        sub = self.subscriptions[user_subscription_id]
        new_sub = StoredUserSubscription(
            user_subscription_id=sub.user_subscription_id,
            user_id=sub.user_id,
            plan_id=kwargs.get("plan_id", sub.plan_id),
            status=kwargs.get("status", sub.status),
            auto_renew=sub.auto_renew,
            start_date=kwargs.get("start_date", sub.start_date),
            end_date=kwargs.get("end_date", sub.end_date),
            plan=sub.plan,
        )
        self.subscriptions[user_subscription_id] = new_sub
        return new_sub

    def get_subscription_by_id(self, session: Any, user_subscription_id: int):
        return self.subscriptions.get(user_subscription_id)

    def get_or_create_usage_balance(self, session: Any, user_id: int, default_voice_minutes=15, default_cv_generations=1):
        if not hasattr(self, "_balances"):
            self._balances = {}
        if user_id not in self._balances:
            class DummyBalance:
                def __init__(self):
                    self.voice_minutes_quota = default_voice_minutes
                    self.voice_minutes_addon = 0
                    self.voice_minutes_used = 0
                    self.cv_generations_quota = default_cv_generations
                    self.cv_generations_addon = 0
                    self.cv_generations_used = 0
            self._balances[user_id] = DummyBalance()
        return self._balances[user_id]

    def update_plan_balance(self, session: Any, user_id: int, voice_minutes: int, cv_generations: int):
        b = self.get_or_create_usage_balance(session, user_id)
        b.voice_minutes_quota = voice_minutes
        b.voice_minutes_used = 0
        b.cv_generations_quota = cv_generations
        b.cv_generations_used = 0
        return b

    def add_addon_balance(self, session: Any, user_id: int, addon_type: str, amount: int):
        b = self.get_or_create_usage_balance(session, user_id)
        if addon_type == "voice":
            b.voice_minutes_addon += amount
        elif addon_type == "cv":
            b.cv_generations_addon += amount
        return b

    def deduct_voice_minutes(self, session: Any, user_id: int, minutes: int):
        b = self.get_or_create_usage_balance(session, user_id)
        b.voice_minutes_used += minutes
        return True

    def deduct_cv_generation(self, session: Any, user_id: int):
        b = self.get_or_create_usage_balance(session, user_id)
        b.cv_generations_used += 1
        return True

    def refund_cv_generation(self, session: Any, user_id: int):
        b = self.get_or_create_usage_balance(session, user_id)
        b.cv_generations_used = max(0, b.cv_generations_used - 1)


class FakeTransactionRepo:
    def __init__(self) -> None:
        self.transactions: dict[int, StoredPaymentTransaction] = {}
        self._tx_counter = 1

    def create_transaction(self, session: Any, **kwargs):
        tx_id = self._tx_counter
        self._tx_counter += 1
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
        self.transactions[tx_id] = tx
        return tx

    def get_by_gateway_ref(self, session: Any, payment_gateway: str, gateway_transaction_id: str):
        for tx in self.transactions.values():
            if tx.payment_gateway == payment_gateway and tx.gateway_transaction_id == gateway_transaction_id:
                return tx
        return None

    def get_by_id(self, session: Any, transaction_id: int):
        return self.transactions.get(transaction_id)

    def update_status(self, session: Any, transaction_id: int, **kwargs):
        tx = self.transactions[transaction_id]
        new_tx = StoredPaymentTransaction(
            transaction_id=tx.transaction_id,
            user_subscription_id=tx.user_subscription_id,
            payment_gateway=tx.payment_gateway,
            gateway_transaction_id=tx.gateway_transaction_id,
            amount=tx.amount,
            currency=tx.currency,
            status=kwargs.get("status", tx.status),
            paid_at=kwargs.get("paid_at", tx.paid_at),
        )
        self.transactions[transaction_id] = new_tx
        return new_tx

    def list_by_user(self, session: Any, user_id: int, limit: int = 50):
        return list(self.transactions.values())[:limit]


class FakeXGateGateway:
    def __init__(self, should_verify: bool = True) -> None:
        self.should_verify = should_verify

    def generate_payment_info(self, *, transaction_ref: str, amount: Decimal, order_info: str = ""):
        return {
            "transaction_ref": transaction_ref,
            "transfer_content": transaction_ref,
            "amount": amount,
            "currency": "VND",
            "bank_name": "bidv",
            "account_number": "9876543210",
            "account_name": "INTERVIEW COACH",
            "qr_code_url": f"https://img.vietqr.io/image/bidv-9876543210.png?amount={amount}&addInfo={transaction_ref}",
            "payment_url": f"https://img.vietqr.io/image/bidv-9876543210.png?amount={amount}&addInfo={transaction_ref}",
        }

    def verify_transaction(self, *, transaction_ref: str, expected_amount: Decimal):
        if self.should_verify:
            return True, "xgate_tx_123", expected_amount
        return False, None, None


class FakeAuditService:
    def __init__(self) -> None:
        self.logs = []

    def record(self, session: Any, **kwargs):
        self.logs.append(kwargs)


@pytest.fixture
def setup_services():
    clock = FakeClock(datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc))
    sub_repo = FakeSubscriptionRepo()
    tx_repo = FakeTransactionRepo()
    gateway = FakeXGateGateway(should_verify=True)
    audit = FakeAuditService()
    payment_svc = PaymentService(
        subscription_repo=sub_repo,
        transaction_repo=tx_repo,
        xgate_gateway=gateway,
        clock=clock,
        audit_service=audit,
    )
    sub_svc = SubscriptionService(subscription_repo=sub_repo, clock=clock)
    return sub_svc, payment_svc, sub_repo, tx_repo, gateway, audit


def test_create_checkout_free_plan(setup_services):
    sub_svc, payment_svc, sub_repo, tx_repo, _, _ = setup_services
    res = payment_svc.create_checkout(
        session=None,
        cmd=CreateCheckoutCommand(user_id=10, plan_id=1),
    )
    assert res.amount == Decimal("0")
    # Free plan creates active subscription immediately
    sub = sub_repo.get_active_subscription(None, 10)
    assert sub is not None
    assert sub.status == "active"


def test_create_checkout_paid_plan(setup_services):
    sub_svc, payment_svc, sub_repo, tx_repo, _, audit = setup_services
    res = payment_svc.create_checkout(
        session=None,
        cmd=CreateCheckoutCommand(user_id=11, plan_id=2, payment_gateway="xgate"),
    )
    assert res.amount == Decimal("99000")
    assert res.transaction_ref.startswith("IC")
    assert res.bank_name == "bidv"
    assert res.account_number == "9876543210"
    assert "https://img.vietqr.io/image/bidv-9876543210.png" in res.qr_code_url
    assert len(tx_repo.transactions) == 1
    assert len(audit.logs) == 1


def test_create_checkout_inactive_plan_raises(setup_services):
    _, payment_svc, _, _, _, _ = setup_services
    with pytest.raises(DomainValidationError, match="inactive"):
        payment_svc.create_checkout(
            session=None,
            cmd=CreateCheckoutCommand(user_id=11, plan_id=3),
        )


def test_verify_payment_success_and_idempotency(setup_services):
    _, payment_svc, sub_repo, tx_repo, gateway, audit = setup_services

    # 1. Create checkout
    res = payment_svc.create_checkout(
        session=None,
        cmd=CreateCheckoutCommand(user_id=20, plan_id=2, payment_gateway="xgate"),
    )
    txn_ref = res.transaction_ref

    # 2. Verify payment
    result = payment_svc.verify_payment(None, VerifyPaymentCommand(user_id=20, transaction_ref=txn_ref))
    assert result["status"] == "success"
    assert "thành công" in result["message"]

    tx = tx_repo.get_by_gateway_ref(None, "xgate", txn_ref)
    assert tx.status == "success"
    sub = sub_repo.get_active_subscription(None, 20)
    assert sub is not None
    assert sub.status == "active"

    # 3. IDEMPOTENCY: verify payment again
    log_count_before = len(audit.logs)
    dup_result = payment_svc.verify_payment(None, VerifyPaymentCommand(user_id=20, transaction_ref=txn_ref))
    assert dup_result["status"] == "success"
    assert len(audit.logs) == log_count_before


def test_verify_payment_pending(setup_services):
    _, payment_svc, _, _, gateway, _ = setup_services
    gateway.should_verify = False

    res = payment_svc.create_checkout(
        session=None,
        cmd=CreateCheckoutCommand(user_id=25, plan_id=2, payment_gateway="xgate"),
    )
    txn_ref = res.transaction_ref

    result = payment_svc.verify_payment(None, VerifyPaymentCommand(user_id=25, transaction_ref=txn_ref))
    assert result["status"] == "pending"


def test_verify_payment_not_found(setup_services):
    _, payment_svc, _, _, _, _ = setup_services
    with pytest.raises(NotFoundError):
        payment_svc.verify_payment(None, VerifyPaymentCommand(user_id=1, transaction_ref="NON_EXIST"))


def test_process_xgate_webhook(setup_services):
    _, payment_svc, sub_repo, tx_repo, _, _ = setup_services
    res = payment_svc.create_checkout(
        session=None,
        cmd=CreateCheckoutCommand(user_id=30, plan_id=2, payment_gateway="xgate"),
    )
    txn_ref = res.transaction_ref

    webhook_payload = {
        "id": "webhook_event_1",
        "amount": 99000,
        "content": f"Chuyen tien {txn_ref}",
    }
    result = payment_svc.process_xgate_webhook(None, webhook_payload)
    assert result["success"] is True

    tx = tx_repo.get_by_gateway_ref(None, "xgate", txn_ref)
    assert tx.status == "success"
    sub = sub_repo.get_active_subscription(None, 30)
    assert sub.status == "active"


def test_quota_check(setup_services):
    sub_svc, _, sub_repo, _, _, _ = setup_services
    # User without subscription
    q = sub_svc.check_quota(None, CheckQuotaCommand(user_id=99))
    assert q["has_active_subscription"] is False
    assert q["remaining_quota"] == 15
    assert q["voice_minutes"]["remaining"] == 15
    assert q["cv_generations"]["remaining"] == 1

    # User with active Pro subscription
    sub_repo.create_subscription(None, user_id=100, plan_id=2, status="active")
    sub_repo.update_plan_balance(None, user_id=100, voice_minutes=300, cv_generations=15)
    q_pro = sub_svc.check_quota(None, CheckQuotaCommand(user_id=100))
    assert q_pro["has_active_subscription"] is True
    assert q_pro["remaining_quota"] == 300
    assert q_pro["voice_minutes"]["remaining"] == 300
    assert q_pro["cv_generations"]["remaining"] == 15
