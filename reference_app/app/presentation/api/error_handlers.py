from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ...domain.errors import (
    AuthError,
    ConflictError,
    DomainValidationError,
    ForbiddenError,
    NotFoundError,
)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(DomainValidationError)
    async def domain_invalid(request: Request, exc: DomainValidationError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(AuthError)
    async def auth_failed(request: Request, exc: AuthError):
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    @app.exception_handler(ForbiddenError)
    async def forbidden(request: Request, exc: ForbiddenError):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict(request: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})
