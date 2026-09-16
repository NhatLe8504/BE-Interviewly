from __future__ import annotations

from decimal import Decimal
import hashlib
import hmac
import urllib.parse
import uuid


def unique_email(prefix: str = "billing") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def sign_vnpay(params: dict[str, str], secret: str = "SANDBOXSECRETKEY1234567890ABCDEF") -> dict[str, str]:
    sorted_items = sorted(params.items(), key=lambda x: x[0])
    qs = "&".join(f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in sorted_items)
    h = hmac.new(secret.encode("utf-8"), qs.encode("utf-8"), hashlib.sha512).hexdigest()
    result = dict(params)
    result["vnp_SecureHash"] = h
    return result


def auth_headers(client, email: str | None = None) -> dict[str, str]:
    email = email or unique_email()
    client.post(
        "/api/v1/auth/register",
        json={"full_name": "Billing Tester", "email": email, "password": "password123"},
    )
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "password123"},
    )
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_plans(client) -> None:
    resp = client.get("/api/v1/billing/plans")
    assert resp.status_code == 200, resp.text
    plans = resp.json()
    assert len(plans) >= 3
    plan_names = [p["plan_name"] for p in plans]
    assert "Free" in plan_names
    assert "Pro Monthly" in plan_names
    assert "Pro Yearly" in plan_names

    # Compat route
    resp_compat = client.get("/api/v1/plans")
    assert resp_compat.status_code == 200
    assert len(resp_compat.json()) == len(plans)


def test_free_checkout_instant_activation(client) -> None:
    headers = auth_headers(client)
    plans = client.get("/api/v1/billing/plans").json()
    free_plan = next(p for p in plans if p["plan_name"] == "Free")

    resp = client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan_id": free_plan["plan_id"], "payment_gateway": "vnpay"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(str(body["amount"])) == Decimal("0")

    sub_resp = client.get("/api/v1/billing/subscriptions/me", headers=headers)
    assert sub_resp.status_code == 200
    sub_data = sub_resp.json()
    assert sub_data is not None
    assert sub_data["status"] == "active"
    assert sub_data["plan"]["plan_name"] == "Free"


def test_pro_checkout_and_vnpay_ipn_flow(client) -> None:
    headers = auth_headers(client)
    plans = client.get("/api/v1/billing/plans").json()
    pro_plan = next(p for p in plans if p["plan_name"] == "Pro Monthly")

    # 1. Checkout
    checkout_resp = client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan_id": pro_plan["plan_id"], "payment_gateway": "vnpay"},
    )
    assert checkout_resp.status_code == 200, checkout_resp.text
    checkout_data = checkout_resp.json()
    txn_ref = checkout_data["transaction_ref"]
    assert "vnp_SecureHash" in checkout_data["payment_url"]

    # 2. Before IPN, subscription is not active yet
    sub_resp = client.get("/api/v1/billing/subscriptions/me", headers=headers)
    assert sub_resp.status_code == 200
    assert sub_resp.json() is None  # no active sub yet

    # 3. Simulate VNPay IPN webhook
    raw_ipn = {
        "vnp_Amount": "9900000",
        "vnp_BankCode": "NCB",
        "vnp_BankTranNo": "VNP14073848",
        "vnp_CardType": "ATM",
        "vnp_Command": "pay",
        "vnp_CurrCode": "VND",
        "vnp_OrderInfo": "Payment Pro Monthly",
        "vnp_PayDate": "20260916120000",
        "vnp_ResponseCode": "00",
        "vnp_TmnCode": "INTERVIE",
        "vnp_TransactionNo": "14073848",
        "vnp_TransactionStatus": "00",
        "vnp_TxnRef": txn_ref,
    }
    signed_ipn = sign_vnpay(raw_ipn)

    ipn_resp = client.get("/api/v1/billing/vnpay-ipn", params=signed_ipn)
    assert ipn_resp.status_code == 200, ipn_resp.text
    assert ipn_resp.json() == {"RspCode": "00", "Message": "Confirm Success"}

    # 4. IDEMPOTENCY: calling IPN second time returns success without duplicate processing
    dup_ipn = client.get("/api/v1/billing/vnpay-ipn", params=signed_ipn)
    assert dup_ipn.status_code == 200
    assert dup_ipn.json() == {"RspCode": "00", "Message": "Confirm Success"}

    # 5. After IPN, subscription is active
    sub_active = client.get("/api/v1/billing/subscriptions/me", headers=headers)
    assert sub_active.status_code == 200
    active_data = sub_active.json()
    assert active_data is not None
    assert active_data["status"] == "active"
    assert active_data["plan"]["plan_name"] == "Pro Monthly"

    # 6. Payment history shows transaction
    history = client.get("/api/v1/billing/payments/history", headers=headers)
    assert history.status_code == 200
    history_data = history.json()
    assert len(history_data) >= 1
    assert history_data[0]["status"] == "success"
    assert history_data[0]["gateway_transaction_id"] == txn_ref

    # 7. Quota check
    quota = client.get("/api/v1/billing/quota", headers=headers)
    assert quota.status_code == 200
    quota_data = quota.json()
    assert quota_data["has_active_subscription"] is True
    assert quota_data["plan_name"] == "Pro Monthly"
