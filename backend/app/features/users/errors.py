# backend/app/features/users/errors.py

from __future__ import annotations

from typing import Literal

from app.errors.contracts import ConstraintToCode, ErrorCatalog

type UserErrorCode = Literal["USER_NOT_FOUND", "EMAIL_TAKEN"]

user_error_catalog: ErrorCatalog[UserErrorCode] = {
    "USER_NOT_FOUND": {"kind": "NOT_FOUND", "message": "User not found."},
    "EMAIL_TAKEN": {"kind": "CONFLICT", "message": "This email is already in use."},
}

# Postgres reports unique-index violations under the index name.
user_constraint_to_code: ConstraintToCode[UserErrorCode] = {
    "ix_users_email": "EMAIL_TAKEN"
}

__all__ = ["UserErrorCode", "user_constraint_to_code", "user_error_catalog"]
