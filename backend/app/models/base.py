# backend/app/models/base.py

from __future__ import annotations

import enum
from datetime import datetime
from typing import Self

from sqlalchemy import DateTime, Integer, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.errors import NotFoundError
from app.lib.casing import pascal_to_snake


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


def enum_column(enum_cls: type[enum.Enum], name: str) -> SQLEnum:
    """A native Postgres enum column type that persists member *values*."""
    return SQLEnum(enum_cls, name=name, values_callable=_enum_values)


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
            raise NotFoundError(
                f"{pascal_to_snake(cls.__name__).replace('_', ' ').capitalize()} not found."
            )
        return entity
