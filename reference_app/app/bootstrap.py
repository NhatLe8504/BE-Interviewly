from __future__ import annotations

from .application.common import ClockPort
from .application.container import ServiceContainer
from .config import Settings
from .infrastructure.clock import SystemClock
from .infrastructure.database import create_engine_from_url


def build_services(
    clock: ClockPort | None = None,
    settings: Settings | None = None,
) -> ServiceContainer:
    settings = settings or Settings.from_env()
    return ServiceContainer(
        clock=clock or SystemClock(),
        settings=settings,
        engine=create_engine_from_url(settings.database_url),
    )
