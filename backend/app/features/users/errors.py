# backend/app/features/users/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ConstraintCodeMap, ErrorKindMap

type ErrorCode = Literal[
    "USER_NOT_FOUND",
    "EMAIL_TAKEN",
    "CANNOT_MODIFY_OWN_ADMIN",
    "CANNOT_MODIFY_OWNER",
    "CANNOT_DELETE_OWNER",
    "TRANSFER_TARGET_NOT_ADMIN",
    "OWNER_ALREADY_EXISTS",
]

error_kind_map: ErrorKindMap[ErrorCode] = {
    "USER_NOT_FOUND": "NOT_FOUND",
    "EMAIL_TAKEN": "CONFLICT",
    "CANNOT_MODIFY_OWN_ADMIN": "FORBIDDEN",
    "CANNOT_MODIFY_OWNER": "FORBIDDEN",
    "CANNOT_DELETE_OWNER": "FORBIDDEN",
    "TRANSFER_TARGET_NOT_ADMIN": "CONFLICT",
    "OWNER_ALREADY_EXISTS": "CONFLICT",
}

# Postgres reports unique-index violations under the index name.
constraint_code_map: ConstraintCodeMap[ErrorCode] = {
    "ix_users_email": "EMAIL_TAKEN",
    "ix_users_single_owner": "OWNER_ALREADY_EXISTS",
}

__all__ = ["ErrorCode", "constraint_code_map", "error_kind_map"]
