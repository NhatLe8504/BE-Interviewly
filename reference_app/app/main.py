from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware

from .application.container import ServiceContainer
from .bootstrap import build_services
from .config import API_DESCRIPTION, API_TITLE, API_VERSION
from .infrastructure.database import check_database
from .infrastructure.persistence.seed import seed_default_data
from .presentation.api.error_handlers import register_error_handlers
from .presentation.api.routers import admin as admin_router
from .presentation.api.routers import auth as auth_router
from .presentation.api.routers import catalog as catalog_router
from .presentation.api.routers import profile as profile_router


def export_openapi(app: FastAPI) -> Path:
    out = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(jsonable_encoder(app.openapi()), indent=2, ensure_ascii=False) + chr(10),
        encoding="utf-8",
    )
    return out


@asynccontextmanager
async def lifespan(app: FastAPI):
    container: ServiceContainer = app.state.services
    if container.auth_service and hasattr(container.auth_service, "hasher"):
        try:
            seed_default_data(container.session_factory, container.auth_service.hasher)
        except Exception:
            pass
    export_openapi(app)
    yield


def create_app(services: ServiceContainer | None = None) -> FastAPI:
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.services = services or build_services()

    @app.get("/health", tags=["health"])
    async def health(request: Request) -> dict:
        container: ServiceContainer = request.app.state.services
        return {"status": "ok", "database": check_database(container.engine)}

    app.include_router(auth_router.router)
    app.include_router(profile_router.router)
    app.include_router(catalog_router.router)
    app.include_router(admin_router.router)
    register_error_handlers(app)
    return app


app = create_app()
