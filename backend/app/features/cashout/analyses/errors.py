# backend/app/features/cashout/analyses/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ErrorDefinition, ErrorDefinitionList

type ErrorCode = Literal[
    "ANALYSIS_NOT_FOUND",
    "ANALYSIS_VERIFIED",
    "ANALYSIS_NOT_VERIFIED",
    "EXTRACTION_IN_PROGRESS",
    "EXTRACTION_FAILED",
]

error_definition_list: ErrorDefinitionList[ErrorCode] = [
    ErrorDefinition(
        code="ANALYSIS_NOT_FOUND",
        kind="NOT_FOUND",
        message="Document analysis not found.",
    ),
    ErrorDefinition(
        code="ANALYSIS_VERIFIED",
        kind="CONFLICT",
        message="This analysis has already been verified.",
    ),
    ErrorDefinition(
        code="ANALYSIS_NOT_VERIFIED",
        kind="CONFLICT",
        message="Only a verified analysis can be edited.",
    ),
    ErrorDefinition(
        code="EXTRACTION_IN_PROGRESS",
        kind="CONFLICT",
        message="An extraction is already in progress.",
    ),
    ErrorDefinition(
        code="EXTRACTION_FAILED",
        kind="CONFLICT",
        message="The extraction failed; retry it before verifying.",
    ),
]

__all__ = ["ErrorCode", "error_definition_list"]
