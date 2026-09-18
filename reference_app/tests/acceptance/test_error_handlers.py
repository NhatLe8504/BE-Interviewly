from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient

from app.domain.errors import (
    AuthError,
    ConflictError,
    DomainError,
    DomainValidationError,
    ForbiddenError,
    NotFoundError,
)
from app.main import create_app

dummy_router = APIRouter(prefix="/api/v1/test-errors")


@dummy_router.get("/not-found")
def raise_not_found():
    raise NotFoundError("Resource missing")


@dummy_router.get("/domain-validation")
def raise_domain_validation():
    raise DomainValidationError("Invalid value provided")


@dummy_router.get("/auth")
def raise_auth():
    raise AuthError("Invalid token")


@dummy_router.get("/forbidden")
def raise_forbidden():
    raise ForbiddenError("Permission denied")


@dummy_router.get("/conflict")
def raise_conflict():
    raise ConflictError("Entity duplicate")


@dummy_router.get("/generic-domain")
def raise_generic_domain():
    raise DomainError("Business rule violation")


@dummy_router.get("/http-exception")
def raise_http():
    raise HTTPException(status_code=400, detail="Bad client request")


@dummy_router.get("/server-crash")
def raise_crash():
    raise RuntimeError("Unexpected internal crash")


def test_global_exception_handlers():
    app = create_app()
    app.include_router(dummy_router)
    client = TestClient(app, raise_server_exceptions=False)

    # 1. NotFoundError -> 404
    r1 = client.get("/api/v1/test-errors/not-found")
    assert r1.status_code == 404
    assert r1.json() == {"detail": "Resource missing"}

    # 2. DomainValidationError -> 422
    r2 = client.get("/api/v1/test-errors/domain-validation")
    assert r2.status_code == 422
    assert r2.json() == {"detail": "Invalid value provided"}

    # 3. AuthError -> 401
    r3 = client.get("/api/v1/test-errors/auth")
    assert r3.status_code == 401
    assert r3.json() == {"detail": "Invalid token"}

    # 4. ForbiddenError -> 403
    r4 = client.get("/api/v1/test-errors/forbidden")
    assert r4.status_code == 403
    assert r4.json() == {"detail": "Permission denied"}

    # 5. ConflictError -> 409
    r5 = client.get("/api/v1/test-errors/conflict")
    assert r5.status_code == 409
    assert r5.json() == {"detail": "Entity duplicate"}

    # 6. Generic DomainError -> 400
    r6 = client.get("/api/v1/test-errors/generic-domain")
    assert r6.status_code == 400
    assert r6.json() == {"detail": "Business rule violation"}

    # 7. Starlette/FastAPI HTTPException -> keeps status code
    r7 = client.get("/api/v1/test-errors/http-exception")
    assert r7.status_code == 400
    assert r7.json() == {"detail": "Bad client request"}

    # 8. Unhandled Exception -> 500 without leaking stack trace
    r8 = client.get("/api/v1/test-errors/server-crash")
    assert r8.status_code == 500
    assert r8.json() == {"detail": "Internal server error"}

    # 9. RequestValidationError -> 422
    r9 = client.post("/api/v1/auth/register", json={"invalid": "payload"})
    assert r9.status_code == 422
    assert "detail" in r9.json()
