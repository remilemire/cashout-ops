# backend/app/features/cashout/models.py

"""The cashout feature's persisted models, as one surface.

Cashout keeps its ORM models inside the sub-feature that owns them. This
module is what the database registry imports, so adding or moving a
sub-feature's table never reaches past this boundary.
"""

from __future__ import annotations

from .analyses.model import CashoutDocumentAnalysis
from .data.model import CashoutData
from .submissions.model import CashoutSubmission
from .uploads.model import CashoutUpload

__all__ = [
    "CashoutData",
    "CashoutDocumentAnalysis",
    "CashoutSubmission",
    "CashoutUpload",
]
