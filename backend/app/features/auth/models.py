# backend/app/features/auth/models.py

"""ORM models owned by auth, re-exported for the registry and other features.

The models live in the `sessions` and `email_verification` subfeatures; auth is
the only feature that reaches into them, so anything outside auth imports the
models from here.
"""

from __future__ import annotations

from .email_verification.model import EmailVerification
from .sessions.model import Session

__all__ = ["EmailVerification", "Session"]
