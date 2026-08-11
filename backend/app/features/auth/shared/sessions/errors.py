# backend/app/features/auth/shared/sessions/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorDefinition, ErrorDefinitionList

type ErrorCode = Literal["INVALID_SESSION"]

error_definition_list: ErrorDefinitionList[ErrorCode] = [
    ErrorDefinition(
        code="INVALID_SESSION",
        kind="UNAUTHORIZED",
        message="Invalid or expired session.",
    )
]

__all__ = ["ErrorCode", "error_definition_list"]
