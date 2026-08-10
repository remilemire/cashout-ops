# backend/app/features/users/errors.py

from __future__ import annotations

from typing import Literal

from app.errors.contracts import ConstraintToCode, ErrorCatalog

type UserErrorCode = Literal[
    "USER_NOT_FOUND",
    "EMAIL_TAKEN",
    "CANNOT_MODIFY_OWN_ADMIN",
    "CANNOT_MODIFY_OWNER",
    "CANNOT_DELETE_OWNER",
    "TRANSFER_TARGET_NOT_ADMIN",
    "OWNER_ALREADY_EXISTS",
]

user_error_catalog: ErrorCatalog[UserErrorCode] = {
    "USER_NOT_FOUND": {"kind": "NOT_FOUND", "message": "User not found."},
    "EMAIL_TAKEN": {"kind": "CONFLICT", "message": "This email is already in use."},
    "CANNOT_MODIFY_OWN_ADMIN": {
        "kind": "FORBIDDEN",
        "message": "You cannot change your own admin access.",
    },
    "CANNOT_MODIFY_OWNER": {
        "kind": "FORBIDDEN",
        "message": "The owner's role cannot be changed.",
    },
    "CANNOT_DELETE_OWNER": {
        "kind": "FORBIDDEN",
        "message": "The owner account cannot be deleted.",
    },
    "TRANSFER_TARGET_NOT_ADMIN": {
        "kind": "CONFLICT",
        "message": "Ownership can only be transferred to an admin.",
    },
    "OWNER_ALREADY_EXISTS": {
        "kind": "CONFLICT",
        "message": "There is already an owner.",
    },
}

# Postgres reports unique-index violations under the index name.
user_constraint_to_code: ConstraintToCode[UserErrorCode] = {
    "ix_users_email": "EMAIL_TAKEN",
    "ix_users_single_owner": "OWNER_ALREADY_EXISTS",
}

__all__ = ["UserErrorCode", "user_constraint_to_code", "user_error_catalog"]
