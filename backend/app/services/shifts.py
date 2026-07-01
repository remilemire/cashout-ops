# backend/app/services/shifts.py

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AlreadyExistsError
from app.models import Shift


async def find_active(db: AsyncSession, *, user_id: int) -> Shift | None:
    # TODO
    ...


async def start_new(db: AsyncSession, *, user_id: int) -> Shift:
    if await find_active(db, user_id=user_id) is not None:
        raise AlreadyExistsError("A shift is already in progress.")
    # TODO
    return Shift()


async def end_current(db: AsyncSession, *, user_id: int) -> Shift:
    # TODO
    return Shift()


__all__ = ["find_active", "start_new", "end_current"]
