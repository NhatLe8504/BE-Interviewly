from __future__ import annotations

from fastapi import Request

from ...application.container import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.services
