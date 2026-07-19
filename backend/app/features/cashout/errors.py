# backend/app/features/cashout/errors.py

from __future__ import annotations

from typing import Literal

from app.errors.contracts import ConstraintToCode, ErrorCatalog

type CashoutErrorCode = Literal[
    "SUBMISSION_NOT_FOUND",
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

cashout_error_catalog: ErrorCatalog[CashoutErrorCode] = {
    "SUBMISSION_NOT_FOUND": {
        "kind": "NOT_FOUND",
        "message": "Cashout submission not found.",
    },
    "SUBMISSION_COMPLETED": {
        "kind": "CONFLICT",
        "message": "This cashout has already been completed.",
    },
    "SUBMISSION_EMPTY": {
        "kind": "CONFLICT",
        "message": "Upload at least one document before completing.",
    },
    "SUBMISSION_UNVERIFIED": {
        "kind": "CONFLICT",
        "message": "Every document must be verified before completing.",
    },
    "SUBMISSION_HAS_DATA": {
        "kind": "CONFLICT",
        "message": "This cashout has reconciled data and cannot be deleted.",
    },
    "ANALYSIS_VERIFIED": {
        "kind": "CONFLICT",
        "message": "This analysis has already been verified.",
    },
    "EXTRACTION_IN_PROGRESS": {
        "kind": "CONFLICT",
        "message": "An extraction is already in progress.",
    },
    "EXTRACTION_FAILED": {
        "kind": "CONFLICT",
        "message": "The extraction failed; retry it before verifying.",
    },
    "DOCUMENT_TOO_LARGE": {
        "kind": "BAD_REQUEST",
        "message": "Document exceeds the 20 MB size limit.",
    },
    "DOCUMENT_DUPLICATE": {
        "kind": "CONFLICT",
        "message": "This document has already been uploaded to this cashout.",
    },
    "UNSUPPORTED_DOCUMENT_TYPE": {
        "kind": "BAD_REQUEST",
        "message": "Unsupported document content type.",
    },
}

# cashout_data.submission_id is ON DELETE RESTRICT: reconciled data blocks
# deleting its submission. The (submission, checksum) unique index rejects
# uploading the same file twice into one cashout.
cashout_constraint_to_code: ConstraintToCode[CashoutErrorCode] = {
    "cashout_data_submission_id_fkey": "SUBMISSION_HAS_DATA",
    "ix_cashout_documents_submission_checksum": "DOCUMENT_DUPLICATE",
}

__all__ = ["CashoutErrorCode", "cashout_constraint_to_code", "cashout_error_catalog"]
