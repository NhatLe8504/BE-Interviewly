from __future__ import annotations

from decimal import Decimal
import uuid


def unique_email(prefix: str = "billing") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


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
        json={"plan_id": free_plan["plan_id"], "payment_gateway": "xgate"},
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


def test_pro_checkout_and_xgate_verify_payment_flow(client) -> None:
    headers = auth_headers(client)
    plans = client.get("/api/v1/billing/plans").json()
    pro_plan = next(p for p in plans if p["plan_name"] == "Pro Monthly")

    # 1. Checkout via xGate
    checkout_resp = client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan_id": pro_plan["plan_id"], "payment_gateway": "xgate"},
    )
    assert checkout_resp.status_code == 200, checkout_resp.text
    checkout_data = checkout_resp.json()
    txn_ref = checkout_data["transaction_ref"]
    assert txn_ref.startswith("IC")
    assert checkout_data["bank_name"] != ""
    assert checkout_data["account_number"] != ""
    assert "vietqr.io" in checkout_data["qr_code_url"]

    # 2. Before verification, subscription is not active yet
    sub_resp = client.get("/api/v1/billing/subscriptions/me", headers=headers)
    assert sub_resp.status_code == 200
    assert sub_resp.json() is None  # not active yet

    # 3. Simulate xGate REST API finding transaction
    payment_svc = client.app.state.services.payment_service
    payment_svc.xgate_gateway.verify_transaction = (
        lambda transaction_ref, expected_amount: (True, "mock_xgate_tx_999", expected_amount)
    )

    # 4. Verify payment
    verify_resp = client.post(
        "/api/v1/billing/verify-payment",
        headers=headers,
        json={"transaction_ref": txn_ref},
    )
    assert verify_resp.status_code == 200, verify_resp.text
    verify_data = verify_resp.json()
    assert verify_data["status"] == "success"
    assert "thành công" in verify_data["message"]
    assert verify_data["subscription"] is not None
    assert verify_data["subscription"]["status"] == "active"

    # 5. IDEMPOTENCY: calling verify-payment second time succeeds cleanly
    dup_resp = client.post(
        "/api/v1/billing/verify-payment",
        headers=headers,
        json={"transaction_ref": txn_ref},
    )
    assert dup_resp.status_code == 200
    assert dup_resp.json()["status"] == "success"

    # 6. Check subscription state
    sub_active = client.get("/api/v1/billing/subscriptions/me", headers=headers)
    assert sub_active.status_code == 200
    active_data = sub_active.json()
    assert active_data is not None
    assert active_data["status"] == "active"
    assert active_data["plan"]["plan_name"] == "Pro Monthly"

    # 7. Payment history shows success transaction
    history = client.get("/api/v1/billing/payments/history", headers=headers)
    assert history.status_code == 200
    history_data = history.json()
    assert len(history_data) >= 1
    assert history_data[0]["status"] == "success"
    assert history_data[0]["gateway_transaction_id"] == txn_ref

    # 8. Quota check
    quota = client.get("/api/v1/billing/quota", headers=headers)
    assert quota.status_code == 200
    quota_data = quota.json()
    assert quota_data["has_active_subscription"] is True
    assert quota_data["plan_name"] == "Pro Monthly"


def test_xgate_webhook_flow(client) -> None:
    headers = auth_headers(client)
    plans = client.get("/api/v1/billing/plans").json()
    pro_plan = next(p for p in plans if p["plan_name"] == "Pro Monthly")

    checkout_resp = client.post(
        "/api/v1/billing/checkout",
        headers=headers,
        json={"plan_id": pro_plan["plan_id"], "payment_gateway": "xgate"},
    )
    txn_ref = checkout_resp.json()["transaction_ref"]

    webhook_resp = client.post(
        "/api/v1/billing/webhook",
        json={
            "id": "event_123",
            "amount": 99000,
            "content": f"Chuyen khoan tien {txn_ref}",
        },
    )
    assert webhook_resp.status_code == 200
    assert webhook_resp.json()["success"] is True

    # Subscription is active after webhook
    sub_resp = client.get("/api/v1/billing/subscriptions/me", headers=headers)
    assert sub_resp.status_code == 200
    assert sub_resp.json()["status"] == "active"
