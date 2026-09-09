from __future__ import annotations

from .application.common import ClockPort
from .application.container import ServiceContainer
from .infrastructure.clock import SystemClock


def build_services(clock: ClockPort | None = None) -> ServiceContainer:
    return ServiceContainer(clock=clock or SystemClock())
