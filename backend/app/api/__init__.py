# backend/app/api/__init__.py

from __future__ import annotations

from fastapi import APIRouter

api_router = APIRouter(prefix="/api", tags=["api"])


__all__ = ["api_router"]
