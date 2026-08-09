# backend/app/infrastructure/db/dependencies.py

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """One transaction per request: commit on success, roll back on error.

    Services never commit; they may flush when they need a generated PK.
    """
    async with request.app.state.db_sessionmaker() as db:
        try:
            yield db
            await db.commit()
        except BaseException:
            await db.rollback()
            raise


__all__ = ["get_db"]
