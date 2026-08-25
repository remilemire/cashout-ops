# backend/app/features/cashout/documents/errors.py

from __future__ import annotations

from typing import Literal

from app.core.config import settings
from app.core.errors import ErrorDefinition, ErrorDefinitionList

type ErrorCode = Literal[
    "DOCUMENT_NOT_FOUND",
    "DOCUMENT_TOO_LARGE",
    "DOCUMENT_DUPLICATE",
    "UNSUPPORTED_DOCUMENT_TYPE",
]

error_definition_list: ErrorDefinitionList[ErrorCode] = [
    ErrorDefinition(
        code="DOCUMENT_NOT_FOUND",
        kind="NOT_FOUND",
        message="Cashout document not found.",
    ),
    ErrorDefinition(
        code="DOCUMENT_TOO_LARGE",
        kind="BAD_REQUEST",
        message=f"Document exceeds the {settings.storage.MAX_DOCUMENT_SIZE_MB} MB size limit.",
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

__all__ = ["ErrorCode", "error_definition_list"]
