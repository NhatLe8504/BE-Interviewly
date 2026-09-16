from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response

from ....application.container import ServiceContainer
from ..dependencies import get_container, get_current_user, get_session
from ..schemas.report import PdfReportMetaOut

router = APIRouter(prefix="/api/v1/sessions", tags=["report"])


@router.get("/{id}/pdf/download")
def download_pdf(
    id: int,
    current_user: Any = Depends(get_current_user),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> Response:
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
    current_user: Any = Depends(get_current_user),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> Response:
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
    current_user: Any = Depends(get_current_user),
    session: Any = Depends(get_session),
    container: ServiceContainer = Depends(get_container),
) -> PdfReportMetaOut:
    file_url = container.pdf_report_service.repo.get_pdf_report_meta(session, id)
    if not file_url:
        _, filename = container.pdf_report_service.generate_and_store(session, id)
        file_url = f"/reports/{filename}"
    return PdfReportMetaOut(session_id=id, file_url=file_url)
