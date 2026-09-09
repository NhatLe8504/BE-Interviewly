from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...domain.errors import DomainValidationError, NotFoundError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(DomainValidationError)
    async def domain_invalid(request: Request, exc: DomainValidationError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})
