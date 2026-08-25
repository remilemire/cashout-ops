# backend/app/features/cashout/submissions/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorDefinition, ErrorDefinitionList

type ErrorCode = Literal[
    "SUBMISSION_NOT_FOUND",
    "SUBMISSION_COMPLETED",
    "SUBMISSION_NOT_COMPLETED",
    "SUBMISSION_EMPTY",
    "SUBMISSION_UNVERIFIED",
    "SUBMISSION_HAS_DATA",
]

error_definition_list: ErrorDefinitionList[ErrorCode] = [
    ErrorDefinition(
        code="SUBMISSION_NOT_FOUND",
        kind="NOT_FOUND",
        message="Cashout submission not found.",
    ),
    ErrorDefinition(
        code="SUBMISSION_COMPLETED",
        kind="CONFLICT",
        message="This cashout has already been completed.",
    ),
    ErrorDefinition(
        code="SUBMISSION_NOT_COMPLETED",
        kind="CONFLICT",
        message="Only a completed cashout can be unsubmitted.",
    ),
    ErrorDefinition(
        code="SUBMISSION_EMPTY",
        kind="CONFLICT",
        message="Upload at least one document before completing.",
    ),
    ErrorDefinition(
        code="SUBMISSION_UNVERIFIED",
        kind="CONFLICT",
        message="Every document must be verified before completing.",
    ),
    ErrorDefinition(
        code="SUBMISSION_HAS_DATA",
        kind="CONFLICT",
        message="This cashout has reconciled data and cannot be deleted.",
    ),
]

__all__ = ["ErrorCode", "error_definition_list"]
