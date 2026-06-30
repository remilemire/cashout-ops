# backend/app/api/users.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user, require_csrf
from app.models import User
from app.schemas.users import UserOut

router = APIRouter(
    prefix="/users",
    tags=["user"],
    dependencies=[Depends(get_current_user), Depends(require_csrf)],
)


@router.get("/me", response_model=UserOut)
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    return UserOut.model_validate(current_user)
