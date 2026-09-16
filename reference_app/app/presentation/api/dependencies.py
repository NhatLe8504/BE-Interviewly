from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ...application.container import ServiceContainer
from ...domain.errors import AuthError

bearer_scheme = HTTPBearer(auto_error=False)


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.services


def get_session(request: Request) -> Iterator[Any]:
    session_factory = request.app.state.services.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    container: ServiceContainer = Depends(get_container),
) -> int:
    if credentials is None or not credentials.credentials:
        raise AuthError("missing bearer token")
    return container.auth_service.tokens.parse(credentials.credentials)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> Any:
    if credentials is None or not credentials.credentials:
        raise AuthError("missing bearer token")
    user_id = container.auth_service.tokens.parse(credentials.credentials)
    return container.auth_service.get_user(session, user_id)
