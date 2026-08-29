# backend/app/features/cashout/data/types.py

from __future__ import annotations

from enum import StrEnum


class TipoutDepartment(StrEnum):
    BAR = "bar"
    KITCHEN = "kitchen"
    EXPO = "expo"
    HOST = "host"


__all__ = ["TipoutDepartment"]
