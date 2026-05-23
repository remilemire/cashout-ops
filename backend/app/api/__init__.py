# backend/app/api/__init__.py

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.utils.csrf import verify_csrf

from .auth import router as auth_router

api_router = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(verify_csrf)])

api_router.include_router(auth_router)

__all__ = ["api_router"]
