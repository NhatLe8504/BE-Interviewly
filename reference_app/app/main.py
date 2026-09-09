from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder

from .application.container import ServiceContainer
from .bootstrap import build_services
from .config import API_DESCRIPTION, API_TITLE, API_VERSION
from .infrastructure.database import check_database
from .presentation.api.error_handlers import register_error_handlers


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
    export_openapi(app)
    yield


def create_app(services: ServiceContainer | None = None) -> FastAPI:
    app = FastAPI(
        title=API_TITLE,
        version=API_VERSION,
        description=API_DESCRIPTION,
        lifespan=lifespan,
    )
    app.state.services = services or build_services()

    @app.get("/health", tags=["health"])
    async def health(request: Request) -> dict:
        container: ServiceContainer = request.app.state.services
        return {"status": "ok", "database": check_database(container.engine)}

    register_error_handlers(app)
    return app


app = create_app()
