from __future__ import annotations

from decimal import Decimal
import urllib.parse
import pytest

from app.infrastructure.payment.vnpay_adapter import VNPayAdapter


@pytest.fixture
def adapter():
    return VNPayAdapter(
        tmn_code="TESTTMN",
        hash_secret="SECRETKEY123",
        payment_url="https://sandbox.vnpayment.vn/paymentv2/vpcpay.html",
        return_url="http://localhost:3000/result",
    )


def test_generate_payment_url(adapter):
    url = adapter.generate_payment_url(
        transaction_ref="TXN123",
        amount=Decimal("99000"),
        order_info="Test Order",
        ip_address="127.0.0.1",
    )
    assert url.startswith("https://sandbox.vnpayment.vn/paymentv2/vpcpay.html?")
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)

    assert params["vnp_TmnCode"][0] == "TESTTMN"
    assert params["vnp_Amount"][0] == "9900000"  # multiplied by 100
    assert params["vnp_TxnRef"][0] == "TXN123"
    assert "vnp_SecureHash" in params


def test_verify_response_valid(adapter):
    url = adapter.generate_payment_url(
        transaction_ref="TXN999",
        amount=Decimal("99000"),
        order_info="Test Order",
        ip_address="127.0.0.1",
    )
    parsed = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(parsed.query)
    raw_params = {k: v[0] for k, v in qs.items()}
    raw_params["vnp_ResponseCode"] = "00"

    # Recalculate hash with ResponseCode
    input_data = {k: v for k, v in raw_params.items() if k.startswith("vnp_") and k != "vnp_SecureHash"}
    sorted_data = sorted(input_data.items(), key=lambda x: x[0])
    query = "&".join(f"{k}={urllib.parse.quote_plus(str(v))}" for k, v in sorted_data)
    import hashlib, hmac
    raw_params["vnp_SecureHash"] = hmac.new(
        "SECRETKEY123".encode("utf-8"), query.encode("utf-8"), hashlib.sha512
    ).hexdigest()

    is_valid, txn_ref, rsp_code, amount = adapter.verify_response(raw_params)
    assert is_valid is True
    assert txn_ref == "TXN999"
    assert rsp_code == "00"
    assert amount == Decimal("99000")


def test_verify_response_tampered(adapter):
    fake_params = {
        "vnp_TxnRef": "TXN_FAKE",
        "vnp_Amount": "100000",
        "vnp_ResponseCode": "00",
        "vnp_SecureHash": "tampered_hash",
    }
    is_valid, txn_ref, rsp_code, amount = adapter.verify_response(fake_params)
    assert is_valid is False
