from __future__ import annotations

from fastapi import FastAPI

from .application.container import ServiceContainer
from .bootstrap import build_services
from .presentation.api.error_handlers import register_error_handlers
from .presentation.api.routers import movements, products


def create_app(services: ServiceContainer | None = None) -> FastAPI:
    app = FastAPI(title="WMS Lite")
    app.state.services = services or build_services()

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    app.include_router(products.router)
    app.include_router(movements.router)
    register_error_handlers(app)
    return app


app = create_app()
