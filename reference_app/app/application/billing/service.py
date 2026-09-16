from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
import uuid

from ...domain.errors import DomainValidationError, NotFoundError
from ..common import ClockPort
from .commands import CheckQuotaCommand, CreateCheckoutCommand
from .ports import (
    PaymentGatewayPort,
    PaymentInitResult,
    PaymentTransactionRepoPort,
    StoredPaymentTransaction,
    StoredSubscriptionPlan,
    StoredUserSubscription,
    SubscriptionRepoPort,
)


class SubscriptionService:
    def __init__(
        self,
        subscription_repo: SubscriptionRepoPort,
        clock: ClockPort,
    ) -> None:
        self.subscription_repo = subscription_repo
        self.clock = clock

    def list_plans(self, session: Any) -> list[StoredSubscriptionPlan]:
        return self.subscription_repo.list_active_plans(session)

    def get_user_subscription(
        self, session: Any, user_id: int,
    ) -> StoredUserSubscription | None:
        return self.subscription_repo.get_active_subscription(session, user_id)

    def check_quota(
        self, session: Any, cmd: CheckQuotaCommand,
    ) -> dict[str, Any]:
        sub = self.subscription_repo.get_active_subscription(session, cmd.user_id)
        now = self.clock.now()
        if sub is None or (sub.end_date and now > sub.end_date):
            return {
                "has_active_subscription": False,
                "plan_name": "Free",
                "quota_allowed": True,
                "remaining_quota": 3,
                "feature": cmd.feature_name,
            }
        plan = sub.plan
        limits = plan.feature_limits if plan else {}
        turn_limit = limits.get("turn_limit", limits.get("quota", 100))
        return {
            "has_active_subscription": True,
            "plan_name": plan.plan_name if plan else "Unknown",
            "quota_allowed": True,
            "remaining_quota": turn_limit,
            "feature": cmd.feature_name,
        }


class PaymentService:
    def __init__(
        self,
        subscription_repo: SubscriptionRepoPort,
        transaction_repo: PaymentTransactionRepoPort,
        gateways: dict[str, PaymentGatewayPort],
        clock: ClockPort,
        audit_service: Any = None,
    ) -> None:
        self.subscription_repo = subscription_repo
        self.transaction_repo = transaction_repo
        self.gateways = gateways
        self.clock = clock
        self.audit_service = audit_service

    def create_checkout(
        self, session: Any, cmd: CreateCheckoutCommand,
    ) -> PaymentInitResult:
        plan = self.subscription_repo.get_plan_by_id(session, cmd.plan_id)
        if plan is None:
            raise NotFoundError(f"Subscription plan {cmd.plan_id} not found")
        if not plan.is_active:
            raise DomainValidationError("Subscription plan is inactive")

        gateway_key = cmd.payment_gateway.lower()
        gateway = self.gateways.get(gateway_key)
        if gateway is None and plan.price > Decimal("0"):
            raise DomainValidationError(f"Unsupported payment gateway: {cmd.payment_gateway}")

        now = self.clock.now()

        # If free plan, activate immediately
        if plan.price <= Decimal("0"):
            sub = self.subscription_repo.create_subscription(
                session,
                user_id=cmd.user_id,
                plan_id=plan.plan_id,
                status="active",
                auto_renew=False,
                start_date=now,
                end_date=None,
            )
            if self.audit_service:
                self.audit_service.record(
                    session,
                    table_name="user_subscriptions",
                    action="insert",
                    user_id=cmd.user_id,
                    record_id=sub.user_subscription_id,
                    new_value={"plan_id": plan.plan_id, "status": "active"},
                )
            return PaymentInitResult(
                transaction_ref=f"FREE_{sub.user_subscription_id}",
                payment_url="",
                amount=Decimal("0"),
                currency="VND",
            )

        # For paid plan before payment confirmation, create subscription with status "cancelled" (pending payment)
        sub = self.subscription_repo.create_subscription(
            session,
            user_id=cmd.user_id,
            plan_id=plan.plan_id,
            status="cancelled",
            auto_renew=False,
            start_date=now,
            end_date=now,
        )

        txn_ref = f"TXN{int(now.timestamp())}_{uuid.uuid4().hex[:6]}"
        tx = self.transaction_repo.create_transaction(
            session,
            user_subscription_id=sub.user_subscription_id,
            payment_gateway=gateway_key,
            gateway_transaction_id=txn_ref,
            amount=plan.price,
            currency="VND",
            status="pending",
        )

        payment_url = gateway.generate_payment_url(
            transaction_ref=txn_ref,
            amount=plan.price,
            order_info=f"Interview Coach - {plan.plan_name}",
            ip_address=cmd.ip_address,
            return_url=cmd.return_url,
        )

        if self.audit_service:
            self.audit_service.record(
                session,
                table_name="payment_transactions",
                action="insert",
                user_id=cmd.user_id,
                record_id=tx.transaction_id,
                new_value={
                    "gateway": gateway_key,
                    "txn_ref": txn_ref,
                    "amount": str(plan.price),
                    "status": "pending",
                },
            )

        return PaymentInitResult(
            transaction_ref=txn_ref,
            payment_url=payment_url,
            amount=plan.price,
            currency="VND",
        )

    def process_vnpay_ipn(
        self, session: Any, params: dict[str, Any],
    ) -> dict[str, str]:
        vnpay = self.gateways.get("vnpay")
        if not vnpay:
            return {"RspCode": "99", "Message": "VNPay Gateway Not Configured"}

        is_valid, txn_ref, rsp_code, amount = vnpay.verify_response(params)
        if not is_valid:
            return {"RspCode": "97", "Message": "Invalid Checksum"}

        tx = self.transaction_repo.get_by_gateway_ref(session, "vnpay", txn_ref)
        if tx is None:
            return {"RspCode": "01", "Message": "Order Not Found"}

        if tx.amount != amount:
            return {"RspCode": "04", "Message": "Invalid Amount"}

        # Idempotency: If already success, do not process again
        if tx.status == "success":
            return {"RspCode": "00", "Message": "Confirm Success"}

        now = self.clock.now()

        if rsp_code == "00":
            # Success
            self.transaction_repo.update_status(
                session, tx.transaction_id, status="success", paid_at=now,
            )
            # Find sub and plan to calculate validity
            sub_id = tx.user_subscription_id
            # Duration based on standard 30 days
            end_date = now + timedelta(days=30)
            self.subscription_repo.update_subscription(
                session, sub_id, status="active", start_date=now, end_date=end_date,
            )
            if self.audit_service:
                self.audit_service.record(
                    session,
                    table_name="payment_transactions",
                    action="update",
                    record_id=tx.transaction_id,
                    new_value={"status": "success", "paid_at": now.isoformat()},
                )
                self.audit_service.record(
                    session,
                    table_name="user_subscriptions",
                    action="update",
                    record_id=sub_id,
                    new_value={"status": "active", "end_date": end_date.isoformat()},
                )
            return {"RspCode": "00", "Message": "Confirm Success"}
        else:
            # Failed
            self.transaction_repo.update_status(
                session, tx.transaction_id, status="failed",
            )
            if self.audit_service:
                self.audit_service.record(
                    session,
                    table_name="payment_transactions",
                    action="update",
                    record_id=tx.transaction_id,
                    new_value={"status": "failed", "vnp_code": rsp_code},
                )
            return {"RspCode": "00", "Message": "Confirm Success"}

    def get_payment_history(
        self, session: Any, user_id: int, limit: int = 50,
    ) -> list[StoredPaymentTransaction]:
        return self.transaction_repo.list_by_user(session, user_id, limit=limit)
