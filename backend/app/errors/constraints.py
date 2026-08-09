# backend/app/errors/constraints.py

from __future__ import annotations

from app.features.cashout.errors import cashout_constraint_to_code
from app.features.users.errors import user_constraint_to_code

from .codes import ErrorCode
from .contracts import ConstraintToCode

constraint_to_code: ConstraintToCode[ErrorCode] = {
    **user_constraint_to_code,
    **cashout_constraint_to_code,
}

__all__ = ["constraint_to_code"]
