from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select

from ...application.billing.ports import (
    StoredPaymentTransaction,
    StoredSubscriptionPlan,
    StoredUserSubscription,
)
from .models.billing import (
    PaymentTransaction as OrmPaymentTransaction,
    SubscriptionPlan as OrmSubscriptionPlan,
    UserSubscription as OrmUserSubscription,
    UserUsageBalance as OrmUserUsageBalance,
)
from .models.enums import BillingCycle, PaymentStatus, SubStatus


def _enum_value(val: Any) -> str:
    return val.value if hasattr(val, "value") else str(val)


def _to_stored_plan(row: OrmSubscriptionPlan) -> StoredSubscriptionPlan:
    return StoredSubscriptionPlan(
        plan_id=row.plan_id,
        plan_name=row.plan_name,
        price=Decimal(str(row.price)),
        billing_cycle=_enum_value(row.billing_cycle),
        feature_limits=dict(row.feature_limits or {}),
        is_active=bool(row.is_active),
        created_at=row.created_at,
    )


def _to_stored_subscription(row: OrmUserSubscription) -> StoredUserSubscription:
    plan = _to_stored_plan(row.plan) if row.plan else None
    return StoredUserSubscription(
        user_subscription_id=row.user_subscription_id,
        user_id=row.user_id,
        plan_id=row.plan_id,
        status=_enum_value(row.status),
        auto_renew=bool(row.auto_renew),
        start_date=row.start_date,
        end_date=row.end_date,
        created_at=row.created_at,
        plan=plan,
    )


def _to_stored_tx(row: OrmPaymentTransaction) -> StoredPaymentTransaction:
    return StoredPaymentTransaction(
        transaction_id=row.transaction_id,
        user_subscription_id=row.user_subscription_id,
        payment_gateway=row.payment_gateway,
        gateway_transaction_id=row.gateway_transaction_id,
        amount=Decimal(str(row.amount)),
        currency=row.currency,
        status=_enum_value(row.status),
        paid_at=row.paid_at,
        created_at=row.created_at,
    )


class SqlAlchemyBillingRepository:
    def list_active_plans(self, session: Any) -> list[StoredSubscriptionPlan]:
        rows = session.execute(
            select(OrmSubscriptionPlan)
            .where(OrmSubscriptionPlan.is_active.is_(True))
            .order_by(OrmSubscriptionPlan.price.asc())
        ).scalars().all()
        return [_to_stored_plan(r) for r in rows]

    def get_plan_by_id(self, session: Any, plan_id: int) -> StoredSubscriptionPlan | None:
        row = session.get(OrmSubscriptionPlan, plan_id)
        return _to_stored_plan(row) if row else None

    def get_subscription_by_id(
        self, session: Any, user_subscription_id: int,
    ) -> StoredUserSubscription | None:
        row = session.get(OrmUserSubscription, user_subscription_id)
        return _to_stored_subscription(row) if row else None

    def get_active_subscription(
        self, session: Any, user_id: int,
    ) -> StoredUserSubscription | None:
        rows = session.execute(
            select(OrmUserSubscription)
            .where(
                OrmUserSubscription.user_id == user_id,
                OrmUserSubscription.status == SubStatus.active,
            )
            .order_by(desc(OrmUserSubscription.user_subscription_id))
        ).scalars().all()
        now = datetime.now(timezone.utc)
        for r in rows:
            # If end_date is present, verify not expired
            if r.end_date is not None:
                end_dt = r.end_date if r.end_date.tzinfo else r.end_date.replace(tzinfo=timezone.utc)
                if end_dt < now:
                    continue
            return _to_stored_subscription(r)
        return None

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
        sub_status = SubStatus(status) if status in SubStatus._value2member_map_ else SubStatus.active
        now = datetime.now(timezone.utc)
        row = OrmUserSubscription(
            user_id=user_id,
            plan_id=plan_id,
            status=sub_status,
            auto_renew=auto_renew,
            start_date=start_date or now,
            end_date=end_date,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_stored_subscription(row)

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
        row = session.get(OrmUserSubscription, user_subscription_id)
        if row is not None:
            if status is not None:
                row.status = SubStatus(status) if status in SubStatus._value2member_map_ else SubStatus.active
            if start_date is not None:
                row.start_date = start_date
            if end_date is not None:
                row.end_date = end_date
            if plan_id is not None:
                row.plan_id = plan_id
            session.commit()
            session.refresh(row)
            return _to_stored_subscription(row)
        raise ValueError(f"UserSubscription {user_subscription_id} not found")
    def get_or_create_usage_balance(
        self, session: Any, user_id: int, default_voice_minutes: int = 15, default_cv_generations: int = 1
    ) -> OrmUserUsageBalance:
        row = session.get(OrmUserUsageBalance, user_id)
        if not row:
            row = OrmUserUsageBalance(
                user_id=user_id,
                voice_minutes_quota=default_voice_minutes,
                voice_minutes_addon=0,
                voice_minutes_used=0,
                cv_generations_quota=default_cv_generations,
                cv_generations_addon=0,
                cv_generations_used=0,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
        return row

    def update_plan_balance(
        self, session: Any, user_id: int, voice_minutes: int, cv_generations: int
    ) -> OrmUserUsageBalance:
        balance = self.get_or_create_usage_balance(session, user_id)
        balance.voice_minutes_quota = voice_minutes
        balance.voice_minutes_used = 0
        balance.cv_generations_quota = cv_generations
        balance.cv_generations_used = 0
        balance.last_reset_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(balance)
        return balance

    def add_addon_balance(
        self, session: Any, user_id: int, addon_type: str, amount: int
    ) -> OrmUserUsageBalance:
        balance = self.get_or_create_usage_balance(session, user_id)
        if addon_type == "voice":
            balance.voice_minutes_addon += amount
        elif addon_type == "cv":
            balance.cv_generations_addon += amount
        session.commit()
        session.refresh(balance)
        return balance

    def deduct_voice_minutes(
        self, session: Any, user_id: int, minutes: int
    ) -> bool:
        balance = self.get_or_create_usage_balance(session, user_id)
        total = balance.voice_minutes_quota + balance.voice_minutes_addon
        remaining = max(0, total - balance.voice_minutes_used)
        if remaining < minutes:
            return False
        balance.voice_minutes_used += minutes
        session.commit()
        return True

    def deduct_cv_generation(
        self, session: Any, user_id: int
    ) -> bool:
        balance = self.get_or_create_usage_balance(session, user_id)
        total = balance.cv_generations_quota + balance.cv_generations_addon
        remaining = max(0, total - balance.cv_generations_used)
        if remaining < 1:
            return False
        balance.cv_generations_used += 1
        session.commit()
        return True

    def refund_cv_generation(
        self, session: Any, user_id: int
    ) -> None:
        balance = self.get_or_create_usage_balance(session, user_id)
        balance.cv_generations_used = max(0, balance.cv_generations_used - 1)
        session.commit()


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
        tx_status = PaymentStatus(status) if status in PaymentStatus._value2member_map_ else PaymentStatus.pending
        row = OrmPaymentTransaction(
            user_subscription_id=user_subscription_id,
            payment_gateway=payment_gateway,
            gateway_transaction_id=gateway_transaction_id,
            amount=amount,
            currency=currency,
            status=tx_status,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_stored_tx(row)

    def get_by_gateway_ref(
        self,
        session: Any,
        payment_gateway: str,
        gateway_transaction_id: str,
    ) -> StoredPaymentTransaction | None:
        row = session.execute(
            select(OrmPaymentTransaction).where(
                OrmPaymentTransaction.payment_gateway == payment_gateway,
                OrmPaymentTransaction.gateway_transaction_id == gateway_transaction_id,
            )
        ).scalar_one_or_none()
        return _to_stored_tx(row) if row else None

    def get_by_id(
        self, session: Any, transaction_id: int,
    ) -> StoredPaymentTransaction | None:
        row = session.get(OrmPaymentTransaction, transaction_id)
        return _to_stored_tx(row) if row else None

    def update_status(
        self,
        session: Any,
        transaction_id: int,
        *,
        status: str,
        paid_at: datetime | None = None,
    ) -> StoredPaymentTransaction:
        row = session.get(OrmPaymentTransaction, transaction_id)
        if row is not None:
            row.status = PaymentStatus(status) if status in PaymentStatus._value2member_map_ else PaymentStatus.pending
            if paid_at is not None:
                row.paid_at = paid_at
            session.commit()
            session.refresh(row)
            return _to_stored_tx(row)
        raise ValueError(f"PaymentTransaction {transaction_id} not found")

    def list_by_user(
        self, session: Any, user_id: int, limit: int = 50,
    ) -> list[StoredPaymentTransaction]:
        rows = session.execute(
            select(OrmPaymentTransaction)
            .join(OrmUserSubscription, OrmPaymentTransaction.user_subscription_id == OrmUserSubscription.user_subscription_id)
            .where(OrmUserSubscription.user_id == user_id)
            .order_by(desc(OrmPaymentTransaction.transaction_id))
            .limit(limit)
        ).scalars().all()
        return [_to_stored_tx(r) for r in rows]
