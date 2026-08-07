# backend/app/features/auth/models.py

"""ORM models owned by auth, re-exported for the registry and other features.

The model lives in the `email_verification` subfeature; auth is the only
feature that reaches into it, so anything outside auth imports the model from
here. Sessions are tracked in Redis and have no ORM model.
"""

from __future__ import annotations

from .email_verification.model import EmailVerification

__all__ = ["EmailVerification"]
