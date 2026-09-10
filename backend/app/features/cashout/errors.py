# backend/app/features/cashout/errors.py

from __future__ import annotations

from app.core.errors import ConstraintCodeMap, ErrorKindMap

from .analyses.errors import ErrorCode as AnalysisErrorCode
from .analyses.errors import (
    error_kind_map as analysis_error_kind_map,
)
from .data.errors import ErrorCode as DataErrorCode
from .data.errors import error_kind_map as data_error_kind_map
from .submissions.errors import ErrorCode as SubmissionErrorCode
from .submissions.errors import (
    error_kind_map as submission_error_kind_map,
)
from .uploads.errors import ErrorCode as UploadErrorCode
from .uploads.errors import (
    error_kind_map as upload_error_kind_map,
)

# Cashout owns no codes directly at the root: every code lives in its
# subfeature and is folded in below, so cashout exposes a single error
# surface for the whole feature.
type ErrorCode = (
    SubmissionErrorCode | UploadErrorCode | AnalysisErrorCode | DataErrorCode
)

error_kind_map: ErrorKindMap[ErrorCode] = {
    **submission_error_kind_map,
    **upload_error_kind_map,
    **analysis_error_kind_map,
    **data_error_kind_map,
}

# cashout_data.submission_id is ON DELETE RESTRICT: reconciled data blocks
# deleting its submission. The (submission, checksum) unique index rejects
# uploading the same file twice into one cashout. The partial (employee, day)
# unique index rejects opening a second live cashout for the same day.
constraint_code_map: ConstraintCodeMap[ErrorCode] = {
    "cashout_data_submission_id_fkey": "SUBMISSION_HAS_DATA",
    "ix_cashout_uploads_submission_checksum": "UPLOAD_DUPLICATE",
    "ix_cashout_submissions_employee_business_date": "SUBMISSION_DUPLICATE_DAY",
}

__all__ = ["ErrorCode", "constraint_code_map", "error_kind_map"]
