from __future__ import annotations

from fastapi import Request

from ...application.container import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.services


def get_product_service(request: Request):
    return request.app.state.services.product_query_service


def get_movement_service(request: Request):
    return request.app.state.services.movement_service
