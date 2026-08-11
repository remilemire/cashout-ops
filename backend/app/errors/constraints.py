# backend/app/errors/constraints.py

from __future__ import annotations

from app.core.errors import ConstraintCodeMap
from app.features.cashout.errors import (
    constraint_code_map as cashout_constraint_code_map,
)
from app.features.users.errors import constraint_code_map as user_constraint_code_map

from .codes import ErrorCode

constraint_code_map: ConstraintCodeMap[ErrorCode] = {
    **user_constraint_code_map,
    **cashout_constraint_code_map,
}

__all__ = ["constraint_code_map"]
