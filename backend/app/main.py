# backend/app/main.py

from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api import api_router
from app.core.config import settings
from app.errors import ERROR_RESPONSES, init_error_handlers
from app.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cashout Operations | Whiskey District",
        lifespan=lifespan,
        debug=settings.DEBUG,
        responses=cast(Any, ERROR_RESPONSES),
    )

    app.add_middleware(SessionMiddleware, settings.SECRET_KEY)

    init_error_handlers(app)

    app.include_router(api_router)

    app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):  # type: ignore[reportUnusedFunction]
        return FileResponse("static/index.html")

    return app


app = create_app()
