# backend/app/__init__.py

from __future__ import annotations

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.api import api_router
from app.core.config import settings
from app.core.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(title="roller_bay_ops", lifespan=lifespan, debug=settings.DEBUG)

    app.add_middleware(SessionMiddleware, settings.SECRET_KEY)

    app.include_router(api_router)

    return app


app = create_app()

__all__ = ["app"]
