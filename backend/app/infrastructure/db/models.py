# backend/app/infrastructure/db/models.py

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Self

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


def enum_column(enum_cls: type[enum.Enum], name: str) -> SQLEnum:
    """A native Postgres enum column type that persists member *values*."""
    return SQLEnum(enum_cls, name=name, values_callable=_enum_values)


class Base(DeclarativeBase):
    __abstract__ = True


class Entity(Base):
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    @classmethod
    async def find_by_id(cls, db: AsyncSession, id_: uuid.UUID) -> Self | None:
        """None on miss — the calling service raises its feature's NOT_FOUND code."""
        return await db.get(cls, id_)
