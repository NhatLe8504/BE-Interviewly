from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import Request

from ...application.container import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.services


def get_session(request: Request) -> Iterator[Any]:
    session_factory = request.app.state.services.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
