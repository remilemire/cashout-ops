# backend/app/features/cashout/router.py

"""The flow, per document: the cashier uploads it and immediately gets back an
EXTRACTING analysis; the AI extraction runs in a background task and the
client polls the analysis until it reaches NEEDS_VERIFICATION (or FAILED,
retryable via the extract endpoint). The cashier verifies each analysis —
optionally submitting corrections. Once every document is verified,
completing the submission reconciles the analyses into a CashoutData row and
closes the cashout (COMPLETED).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.errors import error_responses
from app.features.auth.dependencies import get_current_user
from app.security.dependencies import require_csrf

from .analyses.router import router as analyses_router
from .data.router import router as data_router
from .documents.router import router as documents_router
from .submissions.router import router as submissions_router

# Every cashout route requires a session and (on unsafe methods) CSRF; the
# sub-routers inherit these along with the shared error responses.
router = APIRouter(
    prefix="/cashout",
    tags=["cashout"],
    dependencies=[
        Depends(require_csrf),
        Depends(get_current_user),
    ],
    responses=error_responses(
        "UNAUTHENTICATED",
        "INVALID_SESSION",
        "INVALID_CSRF_TOKEN",
        "FORBIDDEN",
    ),
)

# The submission lifecycle (create, list, complete, unsubmit, delete).
router.include_router(submissions_router)
# Document upload, removal, and inline viewing.
router.include_router(documents_router)
# Extraction restarts, polling, and verification.
router.include_router(analyses_router)
# The reconciled cashout data (admin table).
router.include_router(data_router)

__all__ = ["router"]
