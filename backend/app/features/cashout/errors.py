# backend/app/features/cashout/errors.py

from __future__ import annotations

from typing import Literal

from app.core.errors import ConstraintCodeMap, ErrorDefinition, ErrorDefinitionList

type ErrorCode = Literal[
    "SUBMISSION_NOT_FOUND",
    "DOCUMENT_NOT_FOUND",
    "ANALYSIS_NOT_FOUND",
    "SUBMISSION_COMPLETED",
    "SUBMISSION_EMPTY",
    "SUBMISSION_UNVERIFIED",
    "SUBMISSION_HAS_DATA",
    "ANALYSIS_VERIFIED",
    "EXTRACTION_IN_PROGRESS",
    "EXTRACTION_FAILED",
    "DOCUMENT_TOO_LARGE",
    "DOCUMENT_DUPLICATE",
    "UNSUPPORTED_DOCUMENT_TYPE",
]

error_definition_list: ErrorDefinitionList[ErrorCode] = [
    ErrorDefinition(
        code="SUBMISSION_NOT_FOUND",
        kind="NOT_FOUND",
        message="Cashout submission not found.",
    ),
    ErrorDefinition(
        code="DOCUMENT_NOT_FOUND",
        kind="NOT_FOUND",
        message="Cashout document not found.",
    ),
    ErrorDefinition(
        code="ANALYSIS_NOT_FOUND",
        kind="NOT_FOUND",
        message="Document analysis not found.",
    ),
    ErrorDefinition(
        code="SUBMISSION_COMPLETED",
        kind="CONFLICT",
        message="This cashout has already been completed.",
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
    ErrorDefinition(
        code="ANALYSIS_VERIFIED",
        kind="CONFLICT",
        message="This analysis has already been verified.",
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
    ErrorDefinition(
        code="DOCUMENT_TOO_LARGE",
        kind="BAD_REQUEST",
        message="Document exceeds the 20 MB size limit.",
    ),
    ErrorDefinition(
        code="DOCUMENT_DUPLICATE",
        kind="CONFLICT",
        message="This document has already been uploaded to this cashout.",
    ),
    ErrorDefinition(
        code="UNSUPPORTED_DOCUMENT_TYPE",
        kind="BAD_REQUEST",
        message="Unsupported document content type.",
    ),
]

# cashout_data.submission_id is ON DELETE RESTRICT: reconciled data blocks
# deleting its submission. The (submission, checksum) unique index rejects
# uploading the same file twice into one cashout.
constraint_code_map: ConstraintCodeMap[ErrorCode] = {
    "cashout_data_submission_id_fkey": "SUBMISSION_HAS_DATA",
    "ix_cashout_documents_submission_checksum": "DOCUMENT_DUPLICATE",
}

__all__ = ["ErrorCode", "constraint_code_map", "error_definition_list"]
