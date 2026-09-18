from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
import time
from fastapi.middleware.cors import CORSMiddleware
from .infrastructure.logging.server_log_store import global_server_log_store

from .application.container import ServiceContainer
from .bootstrap import build_services
from .config import API_DESCRIPTION, API_TITLE, API_VERSION
from .infrastructure.database import check_database
from .infrastructure.persistence.seed import seed_default_data
from .infrastructure.redis_client import check_redis
from .presentation.api.error_handlers import register_error_handlers
from .presentation.api.routers import admin as admin_router
from .presentation.api.routers import analytics as analytics_router
from .presentation.api.routers import auth as auth_router
from .presentation.api.routers import billing as billing_router
from .presentation.api.routers import catalog as catalog_router
from .presentation.api.routers import evaluation as evaluation_router
from .presentation.api.routers import interview as interview_router
from .presentation.api.routers import profile as profile_router
from .presentation.api.routers import report as report_router
from .presentation.api.routers import upload as upload_router
from .presentation.api.routers import voice_ws as voice_router
from .presentation.api.routers import onboarding as onboarding_router


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

    @app.middleware("http")
    async def route_logger_middleware(request: Request, call_next):
        start_time = time.perf_counter()
        client_ip = request.client.host if request.client else "127.0.0.1"
        user_agent = request.headers.get("user-agent", "-")
        user_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                token = auth_header[7:]
                container = getattr(request.app.state, "services", None)
                if container and container.auth_service and hasattr(container.auth_service, "tokens"):
                    user_id = container.auth_service.tokens.parse(token)
            except Exception:
                pass

        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        if not request.url.path.startswith("/ws"):
            global_server_log_store.record_route_log(
                method=request.method,
                path=request.url.path,
                query=str(request.query_params) if request.query_params else "",
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                user_agent=user_agent,
                user_id=user_id,
            )
        return response

    @app.get("/health", tags=["health"])
    async def health(request: Request) -> dict:
        container: ServiceContainer = request.app.state.services
        data: dict[str, str] = {
            "status": "ok",
            "database": check_database(container.engine),
        }
        if container.redis_client is not None:
            data["redis"] = check_redis(container.redis_client)
        return data

    app.include_router(auth_router.router)
    app.include_router(profile_router.router)
    app.include_router(catalog_router.router)
    app.include_router(admin_router.router)
    app.include_router(analytics_router.router)
    app.include_router(interview_router.router)
    app.include_router(evaluation_router.router)
    app.include_router(billing_router.router)
    app.include_router(billing_router.compat_router)
    app.include_router(report_router.router)
    app.include_router(upload_router.router)
    app.include_router(voice_router.router)
    app.include_router(onboarding_router.router)
    app.include_router(onboarding_router.admin_router)
    register_error_handlers(app)
    return app


app = create_app()
