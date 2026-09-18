from __future__ import annotations

from datetime import datetime, timezone, timedelta

from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload

from ...application.admin.ports import AdminRepositoryPort
from ...domain.admin import (
    AuditLogEntry,
    ModerationItem,
    SystemStats,
    UserAdminSummary,
    PaymentAdminItem,
)
from .models.billing import PaymentTransaction, UserSubscription, SubscriptionPlan
from .models.catalog import QuestionBank
from .models.enums import AuditAction, Language, PaymentStatus, SessionStatus, UserRole, UserStatus, SubStatus
from ...domain.errors import ConflictError
from .models.session import InterviewSession
from .models.system import AuditLog, ModerationLog
from .models.user import User


def _enum_val(val: Any) -> str | None:
    if val is None:
        return None
    return val.value if hasattr(val, "value") else str(val)


def _to_user_summary(row: User) -> UserAdminSummary:
    return UserAdminSummary(
        user_id=row.user_id,
        full_name=row.full_name,
        email=row.email,
        phone=row.phone,
        role=_enum_val(row.role) or "candidate",
        status=_enum_val(row.status) or "active",
        preferred_language=_enum_val(row.preferred_language) or "vi",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_audit_entry(row: AuditLog) -> AuditLogEntry:
    return AuditLogEntry(
        audit_id=row.audit_id,
        user_id=row.user_id,
        table_name=row.table_name,
        record_id=row.record_id,
        action=_enum_val(row.action) or "update",
        old_value=row.old_value,
        new_value=row.new_value,
        created_at=row.created_at,
    )



def _to_payment_item(row: PaymentTransaction) -> PaymentAdminItem:
    user = row.subscription.user if row.subscription else None
    plan = row.subscription.plan if row.subscription else None
    return PaymentAdminItem(
        transaction_id=row.transaction_id,
        user_subscription_id=row.user_subscription_id,
        payment_gateway=row.payment_gateway,
        gateway_transaction_id=row.gateway_transaction_id,
        amount=float(row.amount),
        currency=row.currency,
        status=_enum_val(row.status) or "pending",
        paid_at=row.paid_at,
        created_at=row.created_at,
        user_id=user.user_id if user else None,
        user_email=user.email if user else None,
        user_name=user.full_name if user else None,
        plan_name=plan.plan_name if plan else None,
    )

def _to_moderation_item(row: ModerationLog) -> ModerationItem:
    return ModerationItem(
        log_id=row.log_id,
        admin_id=row.admin_id,
        target_type=row.target_type,
        target_id=row.target_id,
        action=row.action,
        reason=row.reason,
        created_at=row.created_at,
    )


class SqlAlchemyAdminRepository:
    def list_users(
        self,
        session: Any,
        *,
        search: str | None = None,
        role: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[UserAdminSummary]:
        stmt = select(User)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
        if role:
            stmt = stmt.where(User.role == UserRole(role))
        if status:
            stmt = stmt.where(User.status == UserStatus(status))
        stmt = stmt.order_by(User.user_id.desc()).offset(offset).limit(limit)
        rows = session.execute(stmt).scalars().all()
        return [_to_user_summary(r) for r in rows]

    def count_users(
        self,
        session: Any,
        *,
        search: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ) -> int:
        stmt = select(func.count(User.user_id))
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
        if role:
            stmt = stmt.where(User.role == UserRole(role))
        if status:
            stmt = stmt.where(User.status == UserStatus(status))
        return session.execute(stmt).scalar() or 0

    def get_user_by_id(self, session: Any, user_id: int) -> UserAdminSummary | None:
        row = session.get(User, user_id)
        return _to_user_summary(row) if row else None

    def create_user(
        self,
        session: Any,
        *,
        full_name: str,
        email: str,
        password_hash: str,
        phone: str | None = None,
        role: str = "candidate",
        status: str = "active",
        preferred_language: str = "vi",
    ) -> UserAdminSummary:
        existing = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Email {email} is already registered")

        user = User(
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            phone=phone,
            role=UserRole(role),
            status=UserStatus(status),
            preferred_language=Language(preferred_language) if preferred_language in [l.value for l in Language] else Language.vi,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return _to_user_summary(user)

    def update_user_status(self, session: Any, user_id: int, status: str) -> UserAdminSummary:
        row = session.get(User, user_id)
        if not row:
            raise ValueError(f"user {user_id} not found")
        row.status = UserStatus(status)
        session.commit()
        session.refresh(row)
        return _to_user_summary(row)

    def update_user_role(self, session: Any, user_id: int, role: str) -> UserAdminSummary:
        row = session.get(User, user_id)
        if not row:
            raise ValueError(f"user {user_id} not found")
        row.role = UserRole(role)
        session.commit()
        session.refresh(row)
        return _to_user_summary(row)

    def get_system_stats(self, session: Any) -> SystemStats:
        total_users = session.execute(select(func.count(User.user_id))).scalar() or 0
        active_users = session.execute(
            select(func.count(User.user_id)).where(User.status == UserStatus.active)
        ).scalar() or 0

        total_sessions = session.execute(
            select(func.count(InterviewSession.session_id))
        ).scalar() or 0
        completed_sessions = session.execute(
            select(func.count(InterviewSession.session_id)).where(InterviewSession.status == SessionStatus.completed)
        ).scalar() or 0

        total_questions = session.execute(
            select(func.count(QuestionBank.question_id))
        ).scalar() or 0

        revenue = session.execute(
            select(func.coalesce(func.sum(PaymentTransaction.amount), 0)).where(PaymentTransaction.status == PaymentStatus.success)
        ).scalar() or 0.0

        return SystemStats(
            total_users=total_users,
            active_users=active_users,
            total_sessions=total_sessions,
            completed_sessions=completed_sessions,
            total_questions=total_questions,
            total_revenue=float(revenue),
        )

    def list_audit_logs(
        self,
        session: Any,
        *,
        table_name: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        stmt = select(AuditLog)
        if table_name:
            stmt = stmt.where(AuditLog.table_name == table_name)
        stmt = stmt.order_by(AuditLog.audit_id.desc()).offset(offset).limit(limit)
        rows = session.execute(stmt).scalars().all()
        return [_to_audit_entry(r) for r in rows]

    def count_audit_logs(
        self,
        session: Any,
        *,
        table_name: str | None = None,
    ) -> int:
        stmt = select(func.count(AuditLog.audit_id))
        if table_name:
            stmt = stmt.where(AuditLog.table_name == table_name)
        return session.execute(stmt).scalar() or 0

    def record_audit(
        self,
        session: Any,
        *,
        user_id: int | None,
        table_name: str,
        record_id: int | None,
        action: str,
        old_value: dict | None = None,
        new_value: dict | None = None,
    ) -> None:
        log = AuditLog(
            user_id=user_id,
            table_name=table_name,
            record_id=record_id,
            action=AuditAction(action),
            old_value=old_value,
            new_value=new_value,
        )
        session.add(log)
        session.commit()

    def list_moderation_logs(
        self,
        session: Any,
        *,
        target_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ModerationItem]:
        stmt = select(ModerationLog)
        if target_type:
            stmt = stmt.where(ModerationLog.target_type == target_type)
        stmt = stmt.order_by(ModerationLog.log_id.desc()).offset(offset).limit(limit)
        rows = session.execute(stmt).scalars().all()
        return [_to_moderation_item(r) for r in rows]

    def count_moderation_logs(
        self,
        session: Any,
        *,
        target_type: str | None = None,
    ) -> int:
        stmt = select(func.count(ModerationLog.log_id))
        if target_type:
            stmt = stmt.where(ModerationLog.target_type == target_type)
        return session.execute(stmt).scalar() or 0

    def add_moderation_log(
        self,
        session: Any,
        *,
        admin_id: int,
        target_type: str,
        action: str,
        target_id: int | None = None,
        reason: str | None = None,
    ) -> ModerationItem:
        row = ModerationLog(
            admin_id=admin_id,
            target_type=target_type,
            target_id=target_id,
            action=action,
            reason=reason,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return _to_moderation_item(row)


    def list_payments(
        self,
        session: Any,
        *,
        status: str | None = None,
        gateway: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PaymentAdminItem]:
        stmt = (
            select(PaymentTransaction)
            .options(
                joinedload(PaymentTransaction.subscription)
                .joinedload(UserSubscription.user),
                joinedload(PaymentTransaction.subscription)
                .joinedload(UserSubscription.plan),
            )
            .order_by(PaymentTransaction.created_at.desc())
        )
        if status:
            stmt = stmt.where(PaymentTransaction.status == PaymentStatus(status))
        if gateway:
            stmt = stmt.where(PaymentTransaction.payment_gateway == gateway)

        rows = session.execute(stmt.offset(offset).limit(limit)).scalars().all()
        return [_to_payment_item(r) for r in rows]

    def count_payments(
        self,
        session: Any,
        *,
        status: str | None = None,
        gateway: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(PaymentTransaction)
        if status:
            stmt = stmt.where(PaymentTransaction.status == PaymentStatus(status))
        if gateway:
            stmt = stmt.where(PaymentTransaction.payment_gateway == gateway)
        return session.execute(stmt).scalar() or 0

    def get_payment_by_id(self, session: Any, transaction_id: int) -> PaymentAdminItem | None:
        stmt = (
            select(PaymentTransaction)
            .options(
                joinedload(PaymentTransaction.subscription)
                .joinedload(UserSubscription.user),
                joinedload(PaymentTransaction.subscription)
                .joinedload(UserSubscription.plan),
            )
            .where(PaymentTransaction.transaction_id == transaction_id)
        )
        row = session.execute(stmt).scalar_one_or_none()
        return _to_payment_item(row) if row else None


    def update_payment_status(
        self,
        session: Any,
        transaction_id: int,
        status: str,
    ) -> PaymentAdminItem:
        stmt = (
            select(PaymentTransaction)
            .options(
                joinedload(PaymentTransaction.subscription)
                .joinedload(UserSubscription.user),
                joinedload(PaymentTransaction.subscription)
                .joinedload(UserSubscription.plan),
            )
            .where(PaymentTransaction.transaction_id == transaction_id)
        )
        row = session.execute(stmt).scalars().first()
        if not row:
            raise ValueError(f"payment transaction {transaction_id} not found")

        row.status = PaymentStatus(status)
        now = datetime.now(timezone.utc)
        if status == "success":
            if not row.paid_at:
                row.paid_at = now
            if row.subscription:
                row.subscription.status = SubStatus.active
                row.subscription.start_date = now
                cycle = _enum_val(row.subscription.plan.billing_cycle) if row.subscription.plan else "monthly"
                days = 7 if cycle == "weekly" else 365 if cycle == "yearly" else 30
                row.subscription.end_date = now + timedelta(days=days)

        session.commit()
        session.refresh(row)
        return _to_payment_item(row)
