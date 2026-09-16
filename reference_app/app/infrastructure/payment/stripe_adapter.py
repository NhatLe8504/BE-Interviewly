from __future__ import annotations

from decimal import Decimal
from typing import Any


class StripeAdapter:
    def __init__(
        self,
        api_key: str = "",
        webhook_secret: str = "",
    ) -> None:
        self.api_key = api_key
        self.webhook_secret = webhook_secret

    def generate_payment_url(
        self,
        *,
        transaction_ref: str,
        amount: Decimal,
        order_info: str,
        ip_address: str,
        return_url: str | None = None,
    ) -> str:
        # Fallback / mock stripe checkout session url if stripe sdk not configured
        success_url = return_url or "http://localhost:3000/subscription/result/success"
        return f"https://checkout.stripe.com/pay/{transaction_ref}?amount={int(amount)}&desc={order_info}&redirect={success_url}"

    def verify_response(
        self, params: dict[str, Any],
    ) -> tuple[bool, str, str, Decimal]:
        txn_ref = str(params.get("session_id", params.get("txn_ref", "")))
        amount = Decimal(str(params.get("amount", "0")))
        status = str(params.get("status", "00"))
        return True, txn_ref, status, amount
