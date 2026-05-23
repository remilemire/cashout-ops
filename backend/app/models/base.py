# backend/app/models/base.py

from __future__ import annotations

from datetime import datetime
from typing import Self

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.errors import NotFoundError


class Base(DeclarativeBase):
    __abstract__ = True


class Entity(Base):
    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @classmethod
    async def get_active(cls, db: AsyncSession, id_: int) -> Self:
        entity = await db.get(cls, id_)
        if entity is None:
            raise NotFoundError(f"{cls.__name__} not found")
        return entity
