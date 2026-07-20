# backend/app/features/email_verification/schemas.py

from __future__ import annotations

from pydantic import Field

from app.core.schemas import BaseIn


class EmailVerificationVerify(BaseIn):
    # Length is validated in the service against the issued code, so keep this
    # permissive: any wrong value resolves to VERIFICATION_CODE_INVALID rather
    # than a shape error.
    code: str = Field(min_length=1, max_length=12)
