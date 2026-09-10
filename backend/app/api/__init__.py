from __future__ import annotations

from fastapi import APIRouter

from app.features.auth.router import router as auth_router
from app.features.cashout.router import router as cashout_router
from app.features.users.router import router as users_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(cashout_router)

__all__ = ["api_router"]
