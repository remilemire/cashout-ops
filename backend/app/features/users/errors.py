# backend/app/features/users/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ConstraintCodeMap, ErrorDefinition, ErrorDefinitionList

type ErrorCode = Literal[
    "USER_NOT_FOUND",
    "EMAIL_TAKEN",
    "CANNOT_MODIFY_OWN_ADMIN",
    "CANNOT_MODIFY_OWNER",
    "CANNOT_DELETE_OWNER",
    "TRANSFER_TARGET_NOT_ADMIN",
    "OWNER_ALREADY_EXISTS",
]

error_definition_list: ErrorDefinitionList[ErrorCode] = [
    ErrorDefinition(code="USER_NOT_FOUND", kind="NOT_FOUND", message="User not found."),
    ErrorDefinition(
        code="EMAIL_TAKEN", kind="CONFLICT", message="This email is already in use."
    ),
    ErrorDefinition(
        code="CANNOT_MODIFY_OWN_ADMIN",
        kind="FORBIDDEN",
        message="You cannot change your own admin access.",
    ),
    ErrorDefinition(
        code="CANNOT_MODIFY_OWNER",
        kind="FORBIDDEN",
        message="The owner's role cannot be changed.",
    ),
    ErrorDefinition(
        code="CANNOT_DELETE_OWNER",
        kind="FORBIDDEN",
        message="The owner account cannot be deleted.",
    ),
    ErrorDefinition(
        code="TRANSFER_TARGET_NOT_ADMIN",
        kind="CONFLICT",
        message="Ownership can only be transferred to an admin.",
    ),
    ErrorDefinition(
        code="OWNER_ALREADY_EXISTS",
        kind="CONFLICT",
        message="There is already an owner.",
    ),
]

# Postgres reports unique-index violations under the index name.
constraint_code_map: ConstraintCodeMap[ErrorCode] = {
    "ix_users_email": "EMAIL_TAKEN",
    "ix_users_single_owner": "OWNER_ALREADY_EXISTS",
}

__all__ = ["ErrorCode", "constraint_code_map", "error_definition_list"]
