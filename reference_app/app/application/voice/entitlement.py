from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def check_user_voice_entitlement(session_db: Any, user_id: int) -> bool:
    """
    Checks whether a user has an active non-free subscription.
    Returns True if user is on a paid plan (Sprint, Pro Monthly, Pro Yearly), False otherwise.
    """
    if not session_db or not user_id or user_id <= 0:
        return False

    try:
        from ...infrastructure.persistence.models.billing import (
            UserSubscription as OrmUserSubscription,
            SubscriptionPlan as OrmSubscriptionPlan,
            SubStatus,
        )
        from sqlalchemy import select, desc

        rows = session_db.execute(
            select(OrmUserSubscription)
            .where(
                OrmUserSubscription.user_id == user_id,
                OrmUserSubscription.status == SubStatus.active,
            )
            .order_by(desc(OrmUserSubscription.user_subscription_id))
        ).scalars().all()

        now = datetime.now(timezone.utc)
        for r in rows:
            if r.end_date is not None:
                end_dt = r.end_date if r.end_date.tzinfo else r.end_date.replace(tzinfo=timezone.utc)
                if end_dt < now:
                    continue

            plan = r.plan
            if plan and plan.is_active:
                price = getattr(plan, "price", Decimal("0"))
                plan_name = getattr(plan, "plan_name", "").lower()
                if Decimal(str(price)) > Decimal("0") or "free" not in plan_name:
                    return True

        return False
    except Exception:
        return False
