from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CreateCheckoutCommand:
    user_id: int
    plan_id: int
    payment_gateway: str = "vnpay"
    ip_address: str = "127.0.0.1"
    return_url: str | None = None


@dataclass(frozen=True)
class HandleWebhookCommand:
    gateway: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class CheckQuotaCommand:
    user_id: int
    feature_name: str = "interview_turns"
