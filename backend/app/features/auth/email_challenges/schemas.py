from __future__ import annotations

from pydantic import Field

from app.core.schemas import BaseIn, BaseOut, NormalizedEmail


class EmailChallengeStart(BaseIn):
    # Normalized here, so the address reaches the rate limiter, the user
    # lookup, and the stored challenge in one agreed form.
    email: NormalizedEmail


class EmailChallengeStartOut(BaseOut):
    challenge_id: str


# challenge_id stays a plain constrained str rather than a UUID: a garbled id
# resolves to the unified 401 (missing Redis key) instead of a 422.
class EmailChallengeVerifyCode(BaseIn):
    challenge_id: str = Field(min_length=1, max_length=64)
    # Length is validated in the service against the issued code, so keep this
    # permissive: any wrong value resolves to EMAIL_CHALLENGE_INVALID rather
    # than a shape error.
    code: str = Field(min_length=1, max_length=12)
