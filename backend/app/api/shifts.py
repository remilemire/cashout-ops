# backend/app/api/shifts.py

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.shifts import ShiftOut
from app.services import shifts

from .dependencies import get_current_user, get_db, require_csrf

router = APIRouter(
    prefix="/shifts",
    tags=["shift"],
    dependencies=[Depends(require_csrf), Depends(get_current_user)],
)


@router.post("/start", response_model=ShiftOut)
async def start_shift(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ShiftOut:
    shift = await shifts.start_new(db, user_id=current_user.id)
    return ShiftOut.model_validate(shift)


@router.post("/end", response_model=ShiftOut)
async def end_shift(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ShiftOut:
    shift = await shifts.end_current(db, user_id=current_user.id)
    return ShiftOut.model_validate(shift)
