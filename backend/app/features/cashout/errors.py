# backend/app/features/cashout/errors.py

from __future__ import annotations

from app.core.errors import ConstraintCodeMap, ErrorDefinitionList

from .analyses.errors import ErrorCode as AnalysisErrorCode
from .analyses.errors import (
    error_definition_list as analysis_error_definition_list,
)
from .data.errors import ErrorCode as DataErrorCode
from .data.errors import error_definition_list as data_error_definition_list
from .documents.errors import ErrorCode as DocumentErrorCode
from .documents.errors import (
    error_definition_list as document_error_definition_list,
)
from .submissions.errors import ErrorCode as SubmissionErrorCode
from .submissions.errors import (
    error_definition_list as submission_error_definition_list,
)

# Cashout owns no codes directly at the root: every code lives in its
# subfeature and is folded in below, so cashout exposes a single error
# surface for the whole feature.
type ErrorCode = (
    SubmissionErrorCode | DocumentErrorCode | AnalysisErrorCode | DataErrorCode
)

error_definition_list: ErrorDefinitionList[ErrorCode] = [
    *submission_error_definition_list,
    *document_error_definition_list,
    *analysis_error_definition_list,
    *data_error_definition_list,
]

# cashout_data.submission_id is ON DELETE RESTRICT: reconciled data blocks
# deleting its submission. The (submission, checksum) unique index rejects
# uploading the same file twice into one cashout.
constraint_code_map: ConstraintCodeMap[ErrorCode] = {
    "cashout_data_submission_id_fkey": "SUBMISSION_HAS_DATA",
    "ix_cashout_documents_submission_checksum": "DOCUMENT_DUPLICATE",
}

__all__ = ["ErrorCode", "constraint_code_map", "error_definition_list"]
