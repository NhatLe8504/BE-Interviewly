from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import pytest

from app.application.billing.commands import CheckQuotaCommand, CreateCheckoutCommand
from app.application.billing.ports import (
    PaymentGatewayPort,
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
            start_date=sub.start_date,
            end_date=kwargs.get("end_date", sub.end_date),
            plan=sub.plan,
        )
        self.subscriptions[user_subscription_id] = new_sub
        return new_sub


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


class FakeGateway:
    def __init__(self, valid: bool = True, return_code: str = "00") -> None:
        self.valid = valid
        self.return_code = return_code

    def generate_payment_url(self, **kwargs) -> str:
        return f"https://vnpay.test/pay?ref={kwargs['transaction_ref']}"

    def verify_response(self, params: dict[str, Any]):
        txn_ref = params.get("vnp_TxnRef", "")
        amount = Decimal(str(params.get("vnp_Amount", "99000")))
        return self.valid, txn_ref, self.return_code, amount


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
    gateway = FakeGateway()
    audit = FakeAuditService()
    payment_svc = PaymentService(
        subscription_repo=sub_repo,
        transaction_repo=tx_repo,
        gateways={"vnpay": gateway},
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
    assert res.payment_url == ""
    # Should create active subscription
    sub = sub_repo.get_active_subscription(None, 10)
    assert sub is not None
    assert sub.status == "active"


def test_create_checkout_paid_plan(setup_services):
    sub_svc, payment_svc, sub_repo, tx_repo, _, audit = setup_services
    res = payment_svc.create_checkout(
        session=None,
        cmd=CreateCheckoutCommand(user_id=11, plan_id=2, payment_gateway="vnpay"),
    )
    assert res.amount == Decimal("99000")
    assert "https://vnpay.test/pay?ref=" in res.payment_url
    assert len(tx_repo.transactions) == 1
    assert len(audit.logs) == 1


def test_create_checkout_inactive_plan_raises(setup_services):
    _, payment_svc, _, _, _, _ = setup_services
    with pytest.raises(DomainValidationError, match="inactive"):
        payment_svc.create_checkout(
            session=None,
            cmd=CreateCheckoutCommand(user_id=11, plan_id=3),
        )


def test_process_vnpay_ipn_flow_and_idempotency(setup_services):
    _, payment_svc, sub_repo, tx_repo, gateway, audit = setup_services

    # 1. Create checkout
    res = payment_svc.create_checkout(
        session=None,
        cmd=CreateCheckoutCommand(user_id=20, plan_id=2, payment_gateway="vnpay"),
    )
    txn_ref = res.transaction_ref

    # 2. Process valid IPN
    ipn_params = {"vnp_TxnRef": txn_ref, "vnp_Amount": "99000", "vnp_ResponseCode": "00"}
    result = payment_svc.process_vnpay_ipn(None, ipn_params)
    assert result == {"RspCode": "00", "Message": "Confirm Success"}

    # Check that transaction is success and sub is active
    tx = tx_repo.get_by_gateway_ref(None, "vnpay", txn_ref)
    assert tx.status == "success"
    sub = sub_repo.get_active_subscription(None, 20)
    assert sub is not None
    assert sub.status == "active"

    # 3. IDEMPOTENCY: send duplicate IPN again
    log_count_before = len(audit.logs)
    dup_result = payment_svc.process_vnpay_ipn(None, ipn_params)
    assert dup_result == {"RspCode": "00", "Message": "Confirm Success"}
    # No extra audit log should be added for duplicate processing
    assert len(audit.logs) == log_count_before


def test_process_vnpay_ipn_invalid_checksum(setup_services):
    _, payment_svc, _, _, gateway, _ = setup_services
    gateway.valid = False
    result = payment_svc.process_vnpay_ipn(None, {"vnp_TxnRef": "UNKNOWN"})
    assert result["RspCode"] == "97"


def test_process_vnpay_ipn_not_found(setup_services):
    _, payment_svc, _, _, _, _ = setup_services
    result = payment_svc.process_vnpay_ipn(None, {"vnp_TxnRef": "NOT_EXIST"})
    assert result["RspCode"] == "01"


def test_quota_check(setup_services):
    sub_svc, _, sub_repo, _, _, _ = setup_services
    # User without subscription
    q = sub_svc.check_quota(None, CheckQuotaCommand(user_id=99))
    assert q["has_active_subscription"] is False
    assert q["remaining_quota"] == 3

    # User with active Pro subscription
    sub_repo.create_subscription(None, user_id=100, plan_id=2, status="active")
    q_pro = sub_svc.check_quota(None, CheckQuotaCommand(user_id=100))
    assert q_pro["has_active_subscription"] is True
    assert q_pro["remaining_quota"] == 100
