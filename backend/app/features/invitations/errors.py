# backend/app/features/invitations/errors.py

from __future__ import annotations

from typing import Literal

from app.errors.contracts import ConstraintToCode, ErrorCatalog

type InvitationErrorCode = Literal[
    "INVITATION_NOT_FOUND",
    "INVITATION_EXISTS",
    "INVITATION_REQUIRED",
]

invitation_error_catalog: ErrorCatalog[InvitationErrorCode] = {
    "INVITATION_NOT_FOUND": {"kind": "NOT_FOUND", "message": "Invitation not found."},
    "INVITATION_EXISTS": {
        "kind": "CONFLICT",
        "message": "An invitation for this email already exists.",
    },
    "INVITATION_REQUIRED": {
        "kind": "FORBIDDEN",
        "message": "An invitation is required to register.",
    },
}

# Postgres reports unique-index violations under the index name.
invitation_constraint_to_code: ConstraintToCode[InvitationErrorCode] = {
    "ix_invitations_email": "INVITATION_EXISTS"
}

__all__ = [
    "InvitationErrorCode",
    "invitation_constraint_to_code",
    "invitation_error_catalog",
]
