# backend/app/api/__init__.py

from __future__ import annotations

from fastapi import APIRouter

from .auth import router as auth_router
from .users import router as users_router

api_router = APIRouter(prefix="/api", tags=["api"])

api_router.include_router(auth_router)
api_router.include_router(users_router)

__all__ = ["api_router"]
