from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from typing import Any

from ...domain.errors import DomainValidationError, ForbiddenError, NotFoundError
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
        is_active = sub is not None and (sub.end_date is None or now <= sub.end_date)
        plan = sub.plan if is_active else None
        plan_name = plan.plan_name if plan else "Free"

        balance = self.subscription_repo.get_or_create_usage_balance(session, cmd.user_id)
        voice_total = balance.voice_minutes_quota + balance.voice_minutes_addon
        voice_remaining = max(0, voice_total - balance.voice_minutes_used)
        cv_total = balance.cv_generations_quota + balance.cv_generations_addon
        cv_remaining = max(0, cv_total - balance.cv_generations_used)

        is_voice = cmd.feature_name in ("voice", "interview", "turns", "interview_turns", "speech")
        quota_allowed = voice_remaining > 0 if is_voice else cv_remaining > 0
        remaining_quota = voice_remaining if is_voice else cv_remaining

        return {
            "has_active_subscription": is_active,
            "plan_name": plan_name,
            "quota_allowed": quota_allowed,
            "remaining_quota": remaining_quota,
            "feature": cmd.feature_name,
            "voice_minutes": {
                "total": voice_total,
                "used": balance.voice_minutes_used,
                "remaining": voice_remaining,
                "allowed": voice_remaining > 0,
            },
            "cv_generations": {
                "total": cv_total,
                "used": balance.cv_generations_used,
                "remaining": cv_remaining,
                "allowed": cv_remaining > 0,
            },
        }

    def deduct_voice_minutes(
        self, session: Any, user_id: int, duration_seconds: int, session_id: Any = None
    ) -> dict[str, Any]:
        import math
        minutes = max(1, math.ceil(duration_seconds / 60))
        success = self.subscription_repo.deduct_voice_minutes(session, user_id, minutes)
        balance = self.subscription_repo.get_or_create_usage_balance(session, user_id)
        total = balance.voice_minutes_quota + balance.voice_minutes_addon
        remaining = max(0, total - balance.voice_minutes_used)
        return {
            "success": success,
            "message": f"Đã trừ {minutes} phút phỏng vấn" if success else "Hạn mức phút phỏng vấn không đủ",
            "remaining": remaining,
        }

    def deduct_cv_generation(
        self, session: Any, user_id: int, job_id: Any = None
    ) -> dict[str, Any]:
        success = self.subscription_repo.deduct_cv_generation(session, user_id)
        balance = self.subscription_repo.get_or_create_usage_balance(session, user_id)
        total = balance.cv_generations_quota + balance.cv_generations_addon
        remaining = max(0, total - balance.cv_generations_used)
        return {
            "success": success,
            "message": "Đã trừ 1 lượt tạo CV AI" if success else "Hạn mức lượt tạo CV không đủ",
            "remaining": remaining,
        }

    def refund_cv_generation(
        self, session: Any, user_id: int, job_id: Any = None
    ) -> dict[str, Any]:
        self.subscription_repo.refund_cv_generation(session, user_id)
        balance = self.subscription_repo.get_or_create_usage_balance(session, user_id)
        total = balance.cv_generations_quota + balance.cv_generations_addon
        remaining = max(0, total - balance.cv_generations_used)
        return {
            "success": True,
            "message": "Đã hoàn lại 1 lượt tạo CV AI do tác vụ không thành công",
            "remaining": remaining,
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
            limits = plan.feature_limits or {}
            self.subscription_repo.update_plan_balance(
                session,
                user_id=cmd.user_id,
                voice_minutes=limits.get("voice_minutes", 15),
                cv_generations=limits.get("cv_generations", 1),
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

        sub_row = self.subscription_repo.get_subscription_by_id(session, tx.user_subscription_id) if tx.user_subscription_id else None
        if sub_row is not None and sub_row.user_id != cmd.user_id:
            raise ForbiddenError("Forbidden")

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

        sub_row = self.subscription_repo.get_subscription_by_id(session, tx.user_subscription_id) if tx.user_subscription_id else None
        plan_id = sub_row.plan_id if sub_row else None
        plan = self.subscription_repo.get_plan_by_id(session, plan_id) if plan_id else None

        is_addon = (plan.feature_limits.get("type") == "addon") if (plan and plan.feature_limits) else False

        if is_addon:
            addon_type = plan.feature_limits.get("addon_type", "voice")
            addon_amount = (
                plan.feature_limits.get("voice_minutes", 0)
                if addon_type == "voice"
                else plan.feature_limits.get("cv_generations", 0)
            )
            self.subscription_repo.add_addon_balance(session, cmd.user_id, addon_type, addon_amount)
            active_sub = self.subscription_repo.get_active_subscription(session, cmd.user_id)
            message = (
                f"Thanh toán thành công! Đã nạp thêm {addon_amount} "
                f"{'phút phỏng vấn' if addon_type == 'voice' else 'lượt tạo CV AI'}."
            )
        else:
            cycle = plan.billing_cycle if plan else ""
            if cycle == "yearly":
                days = 365
            elif cycle == "weekly":
                days = 7
            else:
                days = 30
            end_date = now + timedelta(days=days)

            active_sub = self.subscription_repo.update_subscription(
                session, tx.user_subscription_id, status="active", start_date=now, end_date=end_date,
            )
            limits = plan.feature_limits if plan else {}
            v_mins = limits.get("voice_minutes", 300 if cycle == "monthly" else 60 if cycle == "weekly" else 4000)
            c_gens = limits.get("cv_generations", 15 if cycle == "monthly" else 3 if cycle == "weekly" else 200)
            self.subscription_repo.update_plan_balance(session, cmd.user_id, v_mins, c_gens)
            message = f"Thanh toán thành công! Gói cước {plan.plan_name if plan else 'Pro'} đã được kích hoạt."

        if self.audit_service:
            self.audit_service.record(
                session,
                table_name="payment_transactions",
                action="update",
                record_id=tx.transaction_id,
                new_value={"status": "success", "paid_at": now.isoformat(), "xgate_id": xgate_tx_id},
            )

        return {
            "status": "success",
            "message": message,
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
            return {"success": True, "message": "Already processed", "transaction_ref": txn_ref}

        if amount < tx.amount:
            return {"success": False, "message": "Amount smaller than order amount"}

        now = self.clock.now()
        self.transaction_repo.update_status(
            session, tx.transaction_id, status="success", paid_at=now,
        )

        sub_row = self.subscription_repo.get_subscription_by_id(session, tx.user_subscription_id) if tx.user_subscription_id else None
        plan_id = sub_row.plan_id if sub_row else None
        plan = self.subscription_repo.get_plan_by_id(session, plan_id) if plan_id else None
        user_id = sub_row.user_id if sub_row else None

        is_addon = (plan.feature_limits.get("type") == "addon") if (plan and plan.feature_limits) else False

        if is_addon and user_id:
            addon_type = plan.feature_limits.get("addon_type", "voice")
            addon_amount = (
                plan.feature_limits.get("voice_minutes", 0)
                if addon_type == "voice"
                else plan.feature_limits.get("cv_generations", 0)
            )
            self.subscription_repo.add_addon_balance(session, user_id, addon_type, addon_amount)
        else:
            cycle = plan.billing_cycle if plan else ""
            if cycle == "yearly":
                days = 365
            elif cycle == "weekly":
                days = 7
            else:
                days = 30
            end_date = now + timedelta(days=days)

            self.subscription_repo.update_subscription(
                session, tx.user_subscription_id, status="active", start_date=now, end_date=end_date,
            )
            if user_id:
                limits = plan.feature_limits if plan else {}
                v_mins = limits.get("voice_minutes", 300 if cycle == "monthly" else 60 if cycle == "weekly" else 4000)
                c_gens = limits.get("cv_generations", 15 if cycle == "monthly" else 3 if cycle == "weekly" else 200)
                self.subscription_repo.update_plan_balance(session, user_id, v_mins, c_gens)

        if self.audit_service:
            self.audit_service.record(
                session,
                table_name="payment_transactions",
                action="update",
                record_id=tx.transaction_id,
                new_value={"status": "success", "paid_at": now.isoformat(), "source": "webhook"},
            )

        return {"success": True, "message": "Payment confirmed via webhook", "transaction_ref": txn_ref}


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
