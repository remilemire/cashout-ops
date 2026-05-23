# backend/app/__init__.py

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api import api_router
from app.core.config import settings
from app.core.lifespan import lifespan
from app.errors import init_error_handlers


def create_app() -> FastAPI:
    app = FastAPI(title="roller_bay_ops", lifespan=lifespan, debug=settings.DEBUG)

    app.add_middleware(SessionMiddleware, settings.SECRET_KEY)

    init_error_handlers(app)

    app.include_router(api_router)

    app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):  # type: ignore[reportUnusedFunction]
        return FileResponse("static/index.html")

    return app


app = create_app()

__all__ = ["app"]
