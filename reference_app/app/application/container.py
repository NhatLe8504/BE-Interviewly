from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import Settings
from .common import ClockPort


@dataclass
class ServiceContainer:
    clock: ClockPort
    settings: Settings
    engine: Any
    session_factory: Any
    auth_service: Any = None
    interview_service: Any = None
    evaluation_service: Any = None
    speech_service: Any = None
    subscription_service: Any = None
    payment_service: Any = None
    audit_service: Any = None
    pdf_report_service: Any = None
    analytics_service: Any = None
