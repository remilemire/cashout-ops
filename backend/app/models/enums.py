# backend/app/models/enums.py

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    CASHIER = "cashier"
    ADMIN = "admin"


class ShiftStatus(StrEnum):
    # TODO
    pass
