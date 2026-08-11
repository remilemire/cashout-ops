# backend/app/features/auth/email_challenges/schemas.py

from __future__ import annotations

from pydantic import EmailStr, Field

from app.core.schemas import BaseIn, BaseOut


class EmailChallengeStart(BaseIn):
    email: EmailStr


class EmailChallengeStartOut(BaseOut):
    challenge_id: str


# challenge_id stays a plain constrained str rather than a UUID: a garbled id
# resolves to the unified 401 (missing Redis key) instead of a 422.
class EmailChallengeVerifyLink(BaseIn):
    challenge_id: str = Field(min_length=1, max_length=64)
    token: str = Field(min_length=1, max_length=128)


class EmailChallengeVerifyLinkOut(BaseOut):
    code: str


class EmailChallengeVerifyCode(BaseIn):
    challenge_id: str = Field(min_length=1, max_length=64)
    # Length is validated in the service against the issued code, so keep this
    # permissive: any wrong value resolves to EMAIL_CHALLENGE_INVALID rather
    # than a shape error.
    code: str = Field(min_length=1, max_length=12)
