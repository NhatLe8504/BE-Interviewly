from __future__ import annotations

from decimal import Decimal
from typing import Any
import urllib.parse
import httpx


class XGateAdapter:
    def __init__(
        self,
        api_key: str = "xgate_86c34581a1efc75cf97ab04f51eae3845030",
        api_url: str = "https://api.xgate.vn/api/v1/transactions",
        receiver_bank: str = "bidv",
        receiver_account: str = "9876543210",
        receiver_name: str = "INTERVIEW COACH",
        http_client: Any = None,
    ) -> None:
        self.api_key = api_key
        self.api_url = api_url
        self.receiver_bank = receiver_bank
        self.receiver_account = receiver_account
        self.receiver_name = receiver_name
        self._http_client = http_client

    def generate_payment_info(
        self,
        *,
        transaction_ref: str,
        amount: Decimal,
        order_info: str = "",
    ) -> dict[str, Any]:
        transfer_content = transaction_ref.strip()
        int_amount = int(amount)
        encoded_account_name = urllib.parse.quote_plus(self.receiver_name)
        encoded_content = urllib.parse.quote_plus(transfer_content)

        # Standard VietQR link
        qr_code_url = (
            f"https://img.vietqr.io/image/{self.receiver_bank}-{self.receiver_account}-compact2.png"
            f"?amount={int_amount}&addInfo={encoded_content}&accountName={encoded_account_name}"
        )

        return {
            "transaction_ref": transaction_ref,
            "transfer_content": transfer_content,
            "amount": amount,
            "currency": "VND",
            "bank_name": self.receiver_bank,
            "account_number": self.receiver_account,
            "account_name": self.receiver_name,
            "qr_code_url": qr_code_url,
            "payment_url": qr_code_url,
        }

    def fetch_transactions(
        self,
        *,
        content: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        headers = {"X-API-Key": self.api_key}
        params: dict[str, Any] = {"limit": limit, "type": "in"}
        if content:
            params["content"] = content

        try:
            if self._http_client is not None:
                resp = self._http_client.get(self.api_url, headers=headers, params=params, timeout=10.0)
            else:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(self.api_url, headers=headers, params=params)

            if resp.status_code == 200:
                payload = resp.json()
                if payload.get("success") and "data" in payload:
                    return payload["data"].get("transactions", [])
        except Exception:
            return []
        return []

    def verify_transaction(
        self,
        *,
        transaction_ref: str,
        expected_amount: Decimal,
    ) -> tuple[bool, str | None, Decimal | None]:
        transactions = self.fetch_transactions(content=transaction_ref, limit=50)
        target_ref = transaction_ref.strip().lower()

        for tx in transactions:
            tx_type = str(tx.get("type", "")).lower()
            if tx_type != "in":
                continue
            content = str(tx.get("content", "")).lower()
            if target_ref in content:
                try:
                    amount = Decimal(str(tx.get("amount", "0")))
                except Exception:
                    amount = Decimal("0")
                if amount >= expected_amount:
                    tx_id = str(tx.get("id", ""))
                    return True, tx_id, amount

        return False, None, None
