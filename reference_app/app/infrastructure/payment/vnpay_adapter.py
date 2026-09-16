from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
from typing import Any
import urllib.parse


class VNPayAdapter:
    def __init__(
        self,
        tmn_code: str = "INTERVIE",
        hash_secret: str = "SANDBOXSECRETKEY1234567890ABCDEF",
        payment_url: str = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html",
        return_url: str = "http://localhost:3000/subscription/result/success",
    ) -> None:
        self.tmn_code = tmn_code
        self.hash_secret = hash_secret
        self.payment_url = payment_url
        self.return_url = return_url

    def generate_payment_url(
        self,
        *,
        transaction_ref: str,
        amount: Decimal,
        order_info: str,
        ip_address: str,
        return_url: str | None = None,
    ) -> str:
        # VNPay requires amount * 100
        int_amount = int(amount * Decimal("100"))
        create_date = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")

        params: dict[str, str] = {
            "vnp_Version": "2.1.0",
            "vnp_Command": "pay",
            "vnp_TmnCode": self.tmn_code,
            "vnp_Amount": str(int_amount),
            "vnp_CurrCode": "VND",
            "vnp_TxnRef": transaction_ref,
            "vnp_OrderInfo": order_info,
            "vnp_OrderType": "other",
            "vnp_Locale": "vn",
            "vnp_ReturnUrl": return_url or self.return_url,
            "vnp_IpAddr": ip_address or "127.0.0.1",
            "vnp_CreateDate": create_date,
        }

        sorted_params = sorted(params.items(), key=lambda x: x[0])
        query_string = "&".join(
            f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in sorted_params
        )

        secure_hash = hmac.new(
            self.hash_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()

        return f"{self.payment_url}?{query_string}&vnp_SecureHash={secure_hash}"

    def verify_response(
        self, params: dict[str, Any],
    ) -> tuple[bool, str, str, Decimal]:
        secure_hash = str(params.get("vnp_SecureHash", "")).strip()
        txn_ref = str(params.get("vnp_TxnRef", "")).strip()
        response_code = str(params.get("vnp_ResponseCode", "")).strip()

        raw_amount = params.get("vnp_Amount", "0")
        try:
            amount = Decimal(str(raw_amount)) / Decimal("100")
        except Exception:
            amount = Decimal("0")

        # Filter and sort params
        input_data = {}
        for key, value in params.items():
            if key.startswith("vnp_") and key not in ("vnp_SecureHash", "vnp_SecureHashType"):
                input_data[key] = value

        sorted_data = sorted(input_data.items(), key=lambda x: x[0])
        query_string = "&".join(
            f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in sorted_data
        )

        expected_hash = hmac.new(
            self.hash_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()

        is_valid = hmac.compare_digest(
            expected_hash.lower(), secure_hash.lower()
        )
        return is_valid, txn_ref, response_code, amount
