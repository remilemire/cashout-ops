# backend/app/features/users/router.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, require_csrf
from app.errors.openapi import error_responses

from .model import User
from .schemas import UserOut

router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[Depends(require_csrf), Depends(get_current_user)],
    responses=error_responses("UNAUTHENTICATED", "INVALID_SESSION"),
)


@router.get("/me", response_model=UserOut)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    """Return the authenticated user."""
    return UserOut.model_validate(current_user)
