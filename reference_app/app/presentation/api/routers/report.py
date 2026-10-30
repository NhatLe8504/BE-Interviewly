from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.security import HTTPAuthorizationCredentials

from ....application.container import ServiceContainer
from ....domain.errors import AuthError
from ..dependencies import (
    bearer_scheme,
    ensure_session_owner,
    get_container,
    get_current_user_id,
    get_session,
)
from ..schemas.report import PdfReportMetaOut

router = APIRouter(prefix="/api/v1/sessions", tags=["report"])


def _extract_user_id(
    token_query: str | None,
    credentials: HTTPAuthorizationCredentials | None,
    container: ServiceContainer,
) -> int:
    auth_token = credentials.credentials if (credentials and credentials.credentials) else token_query
    if not auth_token:
        raise AuthError("missing authentication token")
    return container.auth_service.tokens.parse(auth_token)


@router.get("/{id}/pdf/download")
def download_pdf(
    id: int,
    token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> Response:
    user_id = _extract_user_id(token, credentials, container)
    ensure_session_owner(id, user_id, session, container)

    pdf_bytes, filename = container.pdf_report_service.get_pdf(session, id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/{id}/pdf/preview")
def preview_pdf(
    id: int,
    token: str | None = Query(default=None),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> Response:
    user_id = _extract_user_id(token, credentials, container)
    ensure_session_owner(id, user_id, session, container)

    pdf_bytes, filename = container.pdf_report_service.get_pdf(session, id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
        },
    )


@router.get("/{id}/pdf/meta", response_model=PdfReportMetaOut)
def get_pdf_meta(
    id: int,
    user_id: int = Depends(get_current_user_id),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> PdfReportMetaOut:
    ensure_session_owner(id, user_id, session, container)
    file_url = f"/api/v1/sessions/{id}/pdf/download"
    return PdfReportMetaOut(session_id=id, file_url=file_url)
