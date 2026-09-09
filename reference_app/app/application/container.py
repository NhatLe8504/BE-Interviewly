from __future__ import annotations

from dataclasses import dataclass

from .common import ClockPort


@dataclass
class ServiceContainer:
    clock: ClockPort
