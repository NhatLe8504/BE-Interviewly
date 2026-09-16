from __future__ import annotations

from decimal import Decimal
import pytest

from app.infrastructure.payment.xgate_adapter import XGateAdapter


class FakeHttpClient:
    def __init__(self, response_data: dict, status_code: int = 200) -> None:
        self.response_data = response_data
        self.status_code = status_code

    def get(self, url: str, headers: dict, params: dict, timeout: float = 10.0):
        class FakeResponse:
            def __init__(self, data: dict, code: int):
                self._data = data
                self.status_code = code

            def json(self):
                return self._data

        return FakeResponse(self.response_data, self.status_code)


def test_generate_payment_info():
    adapter = XGateAdapter(
        api_key="xgate_test_key",
        receiver_bank="bidv",
        receiver_account="9876543210",
        receiver_name="INTERVIEW COACH",
    )
    info = adapter.generate_payment_info(
        transaction_ref="IC123456",
        amount=Decimal("99000"),
        order_info="Test Order",
    )
    assert info["transaction_ref"] == "IC123456"
    assert info["transfer_content"] == "IC123456"
    assert info["amount"] == Decimal("99000")
    assert info["bank_name"] == "bidv"
    assert info["account_number"] == "9876543210"
    assert "https://img.vietqr.io/image/bidv-9876543210-compact2.png" in info["qr_code_url"]
    assert "amount=99000" in info["qr_code_url"]


def test_verify_transaction_success():
    fake_payload = {
        "success": True,
        "data": {
            "transactions": [
                {
                    "id": "64b51702-6457-43f9-9323-70ebe80a1176",
                    "amount": 99000,
                    "currency": "VND",
                    "type": "in",
                    "content": "NGUYEN VAN A chuyen tien IC123456 thanh toan goi Pro",
                    "sender_account": "0123456789",
                    "receiver_account": "9876543210",
                    "receiver_bank_name": "bidv",
                    "transaction_date": "2026-05-13T13:36:00+07:00",
                }
            ]
        }
    }
    client = FakeHttpClient(fake_payload)
    adapter = XGateAdapter(api_key="xgate_test", http_client=client)

    is_paid, tx_id, amount = adapter.verify_transaction(
        transaction_ref="IC123456",
        expected_amount=Decimal("99000"),
    )
    assert is_paid is True
    assert tx_id == "64b51702-6457-43f9-9323-70ebe80a1176"
    assert amount == Decimal("99000")


def test_verify_transaction_not_found():
    fake_payload = {
        "success": True,
        "data": {
            "transactions": [
                {
                    "id": "other_id",
                    "amount": 99000,
                    "type": "in",
                    "content": "Chuyen tien mua hang khac",
                }
            ]
        }
    }
    client = FakeHttpClient(fake_payload)
    adapter = XGateAdapter(api_key="xgate_test", http_client=client)

    is_paid, tx_id, amount = adapter.verify_transaction(
        transaction_ref="IC999999",
        expected_amount=Decimal("99000"),
    )
    assert is_paid is False
    assert tx_id is None


def test_verify_transaction_insufficient_amount():
    fake_payload = {
        "success": True,
        "data": {
            "transactions": [
                {
                    "id": "low_amount_id",
                    "amount": 50000,
                    "type": "in",
                    "content": "Chuyen tien IC123456",
                }
            ]
        }
    }
    client = FakeHttpClient(fake_payload)
    adapter = XGateAdapter(api_key="xgate_test", http_client=client)

    is_paid, tx_id, amount = adapter.verify_transaction(
        transaction_ref="IC123456",
        expected_amount=Decimal("99000"),
    )
    assert is_paid is False
