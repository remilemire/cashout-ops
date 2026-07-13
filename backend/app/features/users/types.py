# backend/app/features/users/types.py

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    CASHIER = "CASHIER"
    ADMIN = "ADMIN"
