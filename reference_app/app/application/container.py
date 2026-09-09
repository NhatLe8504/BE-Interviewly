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
