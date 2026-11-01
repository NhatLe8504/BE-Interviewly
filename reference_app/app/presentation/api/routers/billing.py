from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect

from ....application.billing.commands import (
    CheckQuotaCommand,
    CreateCheckoutCommand,
    VerifyPaymentCommand,
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
    DeductCvQuotaIn,
    DeductResultOut,
    DeductVoiceMinutesIn,
    PaymentTransactionOut,
    PlanOut,
    QuotaOut,
    SubscriptionOut,
    VerifyPaymentIn,
    VerifyPaymentOut,
    WebhookResponseOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])
compat_router = APIRouter(prefix="/api/v1", tags=["billing"])


class PaymentWsManager:
    """Thread-safe WebSocket connection manager for instant payment confirmation events."""

    def __init__(self) -> None:
        # Map uppercase transaction_ref -> set of WebSockets
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, txn_ref: str, ws: WebSocket) -> None:
        await ws.accept()
        key = txn_ref.strip().upper()
        async with self._lock:
            if key not in self._connections:
                self._connections[key] = set()
            self._connections[key].add(ws)
        logger.info(f"[PaymentWS] Client connected for {key} (active sockets: {len(self._connections[key])})")

    async def disconnect(self, txn_ref: str, ws: WebSocket) -> None:
        key = txn_ref.strip().upper()
        async with self._lock:
            if key in self._connections:
                self._connections[key].discard(ws)
                if not self._connections[key]:
                    del self._connections[key]
        logger.info(f"[PaymentWS] Client disconnected for {key}")

    async def broadcast_success(self, txn_ref: str, payload: dict[str, Any]) -> int:
        key = txn_ref.strip().upper()
        targets: list[WebSocket] = []
        async with self._lock:
            if key in self._connections:
                targets = list(self._connections[key])

        if not targets:
            logger.info(f"[PaymentWS] No active WebSocket listeners for {key}")
            return 0

        logger.info(f"[PaymentWS] Broadcasting payment success to {len(targets)} client(s) for {key}")
        dead_sockets: list[WebSocket] = []
        sent_count = 0
        for ws in targets:
            try:
                await ws.send_json(payload)
                sent_count += 1
            except Exception as e:
                logger.warning(f"[PaymentWS] Failed sending to socket: {e}")
                dead_sockets.append(ws)

        for ws in dead_sockets:
            await self.disconnect(key, ws)

        return sent_count


payment_ws_manager = PaymentWsManager()


def _to_plan_out(plan: StoredSubscriptionPlan) -> PlanOut:
    return PlanOut(
        plan_id=plan.plan_id,
        plan_name=plan.plan_name,
        price=float(plan.price),
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
        amount=res.amount,
        currency=res.currency,
        transfer_content=res.transfer_content,
        bank_name=res.bank_name,
        account_number=res.account_number,
        account_name=res.account_name,
        qr_code_url=res.qr_code_url,
        payment_url=res.payment_url,
    )


@router.post("/verify-payment", response_model=VerifyPaymentOut)
@compat_router.post("/verify-payment", response_model=VerifyPaymentOut)
async def verify_payment(
    data: VerifyPaymentIn,
    current_user: Any = Depends(get_current_user),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> VerifyPaymentOut:
    res = container.payment_service.verify_payment(
        session,
        VerifyPaymentCommand(
            user_id=current_user.user_id,
            transaction_ref=data.transaction_ref,
        ),
    )
    if res.get("status") == "success":
        await payment_ws_manager.broadcast_success(
            data.transaction_ref,
            {
                "type": "payment_success",
                "status": "success",
                "transaction_ref": data.transaction_ref,
                "message": res.get("message", "Thanh toán thành công!"),
            },
        )
    sub_out = _to_sub_out(res.get("subscription"))
    return VerifyPaymentOut(
        status=res["status"],
        message=res["message"],
        transaction_ref=res["transaction_ref"],
        subscription=sub_out,
    )


@router.post("/webhook", response_model=WebhookResponseOut)
@router.post("/xgate-webhook", response_model=WebhookResponseOut)
@compat_router.post("/webhook", response_model=WebhookResponseOut)
@compat_router.post("/xgate-webhook", response_model=WebhookResponseOut)
async def xgate_webhook(
    request: Request,
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> WebhookResponseOut:
    try:
        body = await request.json()
    except Exception:
        body = {}
    result = container.payment_service.process_xgate_webhook(session, body)
    if result.get("success") and result.get("transaction_ref"):
        txn_ref = result["transaction_ref"]
        await payment_ws_manager.broadcast_success(
            txn_ref,
            {
                "type": "payment_success",
                "status": "success",
                "transaction_ref": txn_ref,
                "message": "Thanh toán thành công! Gói cước đã được kích hoạt.",
            },
        )
    return WebhookResponseOut(
        success=result.get("success", False),
        message=result.get("message", ""),
    )


@router.websocket("/ws/{transaction_ref}")
@compat_router.websocket("/billing/ws/{transaction_ref}")
async def payment_websocket_endpoint(
    websocket: WebSocket,
    transaction_ref: str,
):
    clean_ref = transaction_ref.strip().upper()
    await payment_ws_manager.connect(clean_ref, websocket)

    # Immediately check DB: if transaction is already marked 'success', inform client right away
    container: ServiceContainer = getattr(websocket.app.state, "services", None)
    if container and getattr(container, "session_factory", None):
        try:
            with container.session_factory() as db_session:
                tx = container.payment_service.transaction_repo.get_by_gateway_ref(
                    db_session, "xgate", clean_ref
                )
                if tx and tx.status == "success":
                    await websocket.send_json({
                        "type": "payment_success",
                        "status": "success",
                        "transaction_ref": clean_ref,
                        "message": "Thanh toán thành công! Gói cước đã được kích hoạt.",
                    })
        except Exception as e:
            logger.warning(f"[PaymentWS] Error checking initial transaction state: {e}")

    try:
        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug(f"[PaymentWS] Socket loop exception: {e}")
    finally:
        await payment_ws_manager.disconnect(clean_ref, websocket)


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


@router.post("/deduct-voice-minutes", response_model=DeductResultOut)
@compat_router.post("/deduct-voice-minutes", response_model=DeductResultOut)
def deduct_voice_minutes(
    payload: DeductVoiceMinutesIn,
    current_user: Any = Depends(get_current_user),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> DeductResultOut:
    res = container.subscription_service.deduct_voice_minutes(
        session, current_user.user_id, payload.duration_seconds, payload.session_id
    )
    return DeductResultOut(**res)


@router.post("/deduct-cv-quota", response_model=DeductResultOut)
@compat_router.post("/deduct-cv-quota", response_model=DeductResultOut)
def deduct_cv_quota(
    payload: DeductCvQuotaIn,
    current_user: Any = Depends(get_current_user),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> DeductResultOut:
    res = container.subscription_service.deduct_cv_generation(
        session, current_user.user_id, payload.job_id
    )
    return DeductResultOut(**res)


@router.post("/refund-cv-quota", response_model=DeductResultOut)
@compat_router.post("/refund-cv-quota", response_model=DeductResultOut)
def refund_cv_quota(
    payload: DeductCvQuotaIn,
    current_user: Any = Depends(get_current_user),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> DeductResultOut:
    res = container.subscription_service.refund_cv_generation(
        session, current_user.user_id, payload.job_id
    )
    return DeductResultOut(**res)
