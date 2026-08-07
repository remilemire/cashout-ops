# backend/app/infrastructure/db/models.py

from __future__ import annotations

import enum

from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [str(member.value) for member in enum_cls]


def enum_column(enum_cls: type[enum.Enum], name: str) -> SQLEnum:
    """A native Postgres enum column type that persists member *values*."""
    return SQLEnum(enum_cls, name=name, values_callable=_enum_values)


class Base(DeclarativeBase):
    __abstract__ = True
