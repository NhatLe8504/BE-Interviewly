from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from ....application.billing.commands import (
    CheckQuotaCommand,
    CreateCheckoutCommand,
)
from ....application.billing.ports import (
    StoredPaymentTransaction,
    StoredSubscriptionPlan,
    StoredUserSubscription,
)
from ....application.container import ServiceContainer
from ..dependencies import get_container, get_current_user, get_session
from ..helpers.cache import cache_response
from ..schemas.billing import (
    CheckoutIn,
    CheckoutUrlOut,
    PaymentTransactionOut,
    PlanOut,
    QuotaOut,
    SubscriptionOut,
    VnpayIpnOut,
)

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])
compat_router = APIRouter(prefix="/api/v1", tags=["billing"])


def _to_plan_out(plan: StoredSubscriptionPlan) -> PlanOut:
    return PlanOut(
        plan_id=plan.plan_id,
        plan_name=plan.plan_name,
        price=plan.price,
        billing_cycle=plan.billing_cycle,
        feature_limits=plan.feature_limits,
        is_active=plan.is_active,
    )


def _to_sub_out(sub: StoredUserSubscription | None) -> SubscriptionOut | None:
    if sub is None:
        return None
    plan_out = _to_plan_out(sub.plan) if sub.plan else None
    return SubscriptionOut(
        user_subscription_id=sub.user_subscription_id,
        user_id=sub.user_id,
        plan_id=sub.plan_id,
        status=sub.status,
        auto_renew=sub.auto_renew,
        start_date=sub.start_date,
        end_date=sub.end_date,
        plan=plan_out,
    )


def _to_tx_out(tx: StoredPaymentTransaction) -> PaymentTransactionOut:
    return PaymentTransactionOut(
        transaction_id=tx.transaction_id,
        user_subscription_id=tx.user_subscription_id,
        payment_gateway=tx.payment_gateway,
        gateway_transaction_id=tx.gateway_transaction_id,
        amount=tx.amount,
        currency=tx.currency,
        status=tx.status,
        paid_at=tx.paid_at,
        created_at=tx.created_at,
    )


@router.get("/plans", response_model=list[PlanOut])
@compat_router.get("/plans", response_model=list[PlanOut])
@cache_response(ttl_seconds=900, prefix="billing:plans")
def get_plans(
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[PlanOut]:
    plans = container.subscription_service.list_plans(session)
    return [_to_plan_out(p) for p in plans]


@router.post("/checkout", response_model=CheckoutUrlOut)
@compat_router.post("/checkout", response_model=CheckoutUrlOut)
def checkout(
    data: CheckoutIn,
    request: Request,
    current_user: Any = Depends(get_current_user),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> CheckoutUrlOut:
    client_ip = request.client.host if request.client else "127.0.0.1"
    res = container.payment_service.create_checkout(
        session,
        CreateCheckoutCommand(
            user_id=current_user.user_id,
            plan_id=data.plan_id,
            payment_gateway=data.payment_gateway,
            ip_address=client_ip,
            return_url=data.return_url,
        ),
    )
    return CheckoutUrlOut(
        transaction_ref=res.transaction_ref,
        payment_url=res.payment_url,
        amount=res.amount,
        currency=res.currency,
    )


async def _handle_vnpay_ipn(
    request: Request,
    session: Any,
    container: ServiceContainer,
) -> VnpayIpnOut:
    params = dict(request.query_params)
    if not params:
        try:
            body = await request.json()
            if isinstance(body, dict):
                params = body
        except Exception:
            params = {}
    result = container.payment_service.process_vnpay_ipn(session, params)
    return VnpayIpnOut(RspCode=result["RspCode"], Message=result["Message"])


@router.get("/vnpay-ipn", response_model=VnpayIpnOut)
@router.post("/vnpay-ipn", response_model=VnpayIpnOut)
@compat_router.get("/vnpay-ipn", response_model=VnpayIpnOut)
@compat_router.post("/vnpay-ipn", response_model=VnpayIpnOut)
async def vnpay_ipn(
    request: Request,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> VnpayIpnOut:
    return await _handle_vnpay_ipn(request, session, container)


@router.get("/subscriptions/me", response_model=SubscriptionOut | None)
@compat_router.get("/subscriptions/me", response_model=SubscriptionOut | None)
def get_my_subscription(
    current_user: Any = Depends(get_current_user),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> SubscriptionOut | None:
    sub = container.subscription_service.get_user_subscription(session, current_user.user_id)
    return _to_sub_out(sub)


@router.get("/payments/history", response_model=list[PaymentTransactionOut])
@compat_router.get("/payments/history", response_model=list[PaymentTransactionOut])
def get_payment_history(
    limit: int = Query(50, ge=1, le=100),
    current_user: Any = Depends(get_current_user),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> list[PaymentTransactionOut]:
    txs = container.payment_service.get_payment_history(
        session, current_user.user_id, limit=limit,
    )
    return [_to_tx_out(t) for t in txs]


@router.get("/quota", response_model=QuotaOut)
@compat_router.get("/quota", response_model=QuotaOut)
def get_quota(
    feature: str = "interview_turns",
    current_user: Any = Depends(get_current_user),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> QuotaOut:
    info = container.subscription_service.check_quota(
        session, CheckQuotaCommand(user_id=current_user.user_id, feature_name=feature),
    )
    return QuotaOut(**info)
