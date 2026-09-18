from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from typing import Any

from ...domain.errors import DomainValidationError, NotFoundError
from ..common import ClockPort
from .commands import CheckQuotaCommand, CreateCheckoutCommand, VerifyPaymentCommand
from .ports import (
    PaymentInitResult,
    PaymentTransactionRepoPort,
    StoredPaymentTransaction,
    StoredSubscriptionPlan,
    StoredUserSubscription,
    SubscriptionRepoPort,
    XGateGatewayPort,
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
        xgate_gateway: XGateGatewayPort,
        clock: ClockPort,
        audit_service: Any = None,
        gateways: dict[str, Any] | None = None,
    ) -> None:
        self.subscription_repo = subscription_repo
        self.transaction_repo = transaction_repo
        self.xgate_gateway = xgate_gateway
        self.clock = clock
        self.audit_service = audit_service
        self.gateways = gateways or {}

    def create_checkout(
        self, session: Any, cmd: CreateCheckoutCommand,
    ) -> PaymentInitResult:
        plan = self.subscription_repo.get_plan_by_id(session, cmd.plan_id)
        if plan is None:
            raise NotFoundError(f"Subscription plan {cmd.plan_id} not found")
        if not plan.is_active:
            raise DomainValidationError("Subscription plan is inactive")

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
                amount=Decimal("0"),
                currency="VND",
                transfer_content="",
                bank_name="",
                account_number="",
                account_name="",
                qr_code_url="",
                payment_url="",
            )

        # Create pending subscription record
        sub = self.subscription_repo.create_subscription(
            session,
            user_id=cmd.user_id,
            plan_id=plan.plan_id,
            status="cancelled",
            auto_renew=False,
            start_date=now,
            end_date=now,
        )

        # Generate a clean transfer reference for xGate banking: e.g. IC847061
        random_suffix = int(uuid.uuid4().hex[:6], 16) % 900000 + 100000
        txn_ref = f"IC{random_suffix}"

        tx = self.transaction_repo.create_transaction(
            session,
            user_subscription_id=sub.user_subscription_id,
            payment_gateway="xgate",
            gateway_transaction_id=txn_ref,
            amount=plan.price,
            currency="VND",
            status="pending",
        )

        info = self.xgate_gateway.generate_payment_info(
            transaction_ref=txn_ref,
            amount=plan.price,
            order_info=f"Interview Coach - {plan.plan_name}",
        )

        if self.audit_service:
            self.audit_service.record(
                session,
                table_name="payment_transactions",
                action="insert",
                user_id=cmd.user_id,
                record_id=tx.transaction_id,
                new_value={
                    "gateway": "xgate",
                    "txn_ref": txn_ref,
                    "amount": str(plan.price),
                    "status": "pending",
                },
            )

        return PaymentInitResult(
            transaction_ref=txn_ref,
            amount=plan.price,
            currency="VND",
            transfer_content=info["transfer_content"],
            bank_name=info["bank_name"],
            account_number=info["account_number"],
            account_name=info["account_name"],
            qr_code_url=info["qr_code_url"],
            payment_url=info["payment_url"],
        )

    def verify_payment(
        self, session: Any, cmd: VerifyPaymentCommand,
    ) -> dict[str, Any]:
        tx = self.transaction_repo.get_by_gateway_ref(session, "xgate", cmd.transaction_ref)
        if tx is None:
            raise NotFoundError(f"Không tìm thấy giao dịch: {cmd.transaction_ref}")

        # Idempotency check: already verified
        if tx.status == "success":
            sub = self.subscription_repo.get_active_subscription(session, cmd.user_id)
            return {
                "status": "success",
                "message": "Giao dịch đã được xác nhận thành công trước đó.",
                "transaction_ref": cmd.transaction_ref,
                "subscription": sub,
            }

        # Query xGate REST API for confirmation
        is_paid, xgate_tx_id, amount = self.xgate_gateway.verify_transaction(
            transaction_ref=cmd.transaction_ref,
            expected_amount=tx.amount,
        )

        if not is_paid:
            return {
                "status": "pending",
                "message": "Chưa nhận được giao dịch chuyển khoản trên xGate. Vui lòng kiểm tra lại sau giây lát.",
                "transaction_ref": cmd.transaction_ref,
                "subscription": None,
            }

        now = self.clock.now()

        # Mark transaction success
        self.transaction_repo.update_status(
            session, tx.transaction_id, status="success", paid_at=now,
        )

        # Determine subscription duration based on plan
        sub_id = tx.user_subscription_id
        plan = self.subscription_repo.get_plan_by_id(session, sub_id)
        days = 365 if (plan and plan.billing_cycle == "yearly") else 30
        end_date = now + timedelta(days=days)

        active_sub = self.subscription_repo.update_subscription(
            session, sub_id, status="active", start_date=now, end_date=end_date,
        )

        if self.audit_service:
            self.audit_service.record(
                session,
                table_name="payment_transactions",
                action="update",
                record_id=tx.transaction_id,
                new_value={"status": "success", "paid_at": now.isoformat(), "xgate_id": xgate_tx_id},
            )
            self.audit_service.record(
                session,
                table_name="user_subscriptions",
                action="update",
                record_id=sub_id,
                new_value={"status": "active", "end_date": end_date.isoformat()},
            )

        return {
            "status": "success",
            "message": "Thanh toán thành công! Gói cước Pro đã được kích hoạt.",
            "transaction_ref": cmd.transaction_ref,
            "subscription": active_sub,
        }

    def process_xgate_webhook(
        self, session: Any, payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Support for future production webhooks."""
        content = str(payload.get("content", "")).strip()
        raw_amount = payload.get("amount", "0")
        try:
            amount = Decimal(str(raw_amount))
        except Exception:
            amount = Decimal("0")

        # Find matching transaction by transaction_ref inside content
        import re
        match = re.search(r"(IC\d+)", content, re.IGNORECASE)
        if not match:
            return {"success": False, "message": "No matching IC transfer content found"}

        txn_ref = match.group(1).upper()
        tx = self.transaction_repo.get_by_gateway_ref(session, "xgate", txn_ref)
        if tx is None:
            return {"success": False, "message": f"Transaction {txn_ref} not found"}

        if tx.status == "success":
            return {"success": True, "message": "Already processed"}

        if amount < tx.amount:
            return {"success": False, "message": "Amount smaller than order amount"}

        now = self.clock.now()
        self.transaction_repo.update_status(
            session, tx.transaction_id, status="success", paid_at=now,
        )

        sub_id = tx.user_subscription_id
        plan = self.subscription_repo.get_plan_by_id(session, sub_id)
        days = 365 if (plan and plan.billing_cycle == "yearly") else 30
        end_date = now + timedelta(days=days)

        self.subscription_repo.update_subscription(
            session, sub_id, status="active", start_date=now, end_date=end_date,
        )

        if self.audit_service:
            self.audit_service.record(
                session,
                table_name="payment_transactions",
                action="update",
                record_id=tx.transaction_id,
                new_value={"status": "success", "paid_at": now.isoformat(), "source": "webhook"},
            )

        return {"success": True, "message": "Payment confirmed via webhook"}


    def sync_xgate_transactions(
        self, session: Any, limit: int = 50,
    ) -> dict[str, Any]:
        """Fetch real transactions from xGate API and reconcile with local transactions."""
        import re
        txns = self.xgate_gateway.fetch_transactions(limit=limit)
        matched_count = 0
        new_confirmed_count = 0

        for tx in txns:
            tx_type = str(tx.get("type", "")).lower()
            if tx_type != "in":
                continue

            content = str(tx.get("content", "")).strip()
            raw_amount = tx.get("amount", 0)
            try:
                amount = Decimal(str(raw_amount))
            except Exception:
                amount = Decimal("0")

            xgate_id = str(tx.get("id", ""))
            match = re.search(r"(IC\d+)", content, re.IGNORECASE)
            if not match:
                continue

            txn_ref = match.group(1).upper()
            pending_tx = self.transaction_repo.get_by_gateway_ref(session, "xgate", txn_ref)
            if pending_tx is not None:
                matched_count += 1
                if pending_tx.status == "pending" and amount >= pending_tx.amount:
                    now = self.clock.now()
                    self.transaction_repo.update_status(
                        session, pending_tx.transaction_id, status="success", paid_at=now,
                    )
                    sub_id = pending_tx.user_subscription_id
                    plan = self.subscription_repo.get_plan_by_id(session, sub_id)
                    days = 7 if (plan and plan.billing_cycle == "weekly") else 365 if (plan and plan.billing_cycle == "yearly") else 30
                    end_date = now + timedelta(days=days)

                    self.subscription_repo.update_subscription(
                        session, sub_id, status="active", start_date=now, end_date=end_date,
                    )
                    if self.audit_service:
                        self.audit_service.record(
                            session,
                            table_name="payment_transactions",
                            action="update",
                            record_id=pending_tx.transaction_id,
                            new_value={
                                "status": "success",
                                "paid_at": now.isoformat(),
                                "xgate_id": xgate_id,
                                "sync": "manual",
                            },
                        )
                    new_confirmed_count += 1

        return {
            "success": True,
            "scanned_xgate_count": len(txns),
            "matched_count": matched_count,
            "new_confirmed_count": new_confirmed_count,
            "message": f"Đã quét {len(txns)} giao dịch xGate, đối soát khớp {matched_count} giao dịch, kích hoạt thành công {new_confirmed_count} đơn mới.",
        }

    def get_payment_history(
        self, session: Any, user_id: int, limit: int = 50,
    ) -> list[StoredPaymentTransaction]:
        return self.transaction_repo.list_by_user(session, user_id, limit=limit)
