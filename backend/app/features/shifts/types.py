# backend/app/features/shifts/types.py

from __future__ import annotations

from enum import StrEnum


class ShiftStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
