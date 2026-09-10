# backend/app/features/cashout/dependencies.py

"""Per-user quotas on the costly cashout endpoints.

Uploads land a file in storage and normally trigger an AI extraction
(the manual-entry upload skips the AI but shares the same intake quota), and
every on-demand re-extraction triggers one. These guards bound the spend a
runaway script or a compromised account can incur — a cost ceiling, not a
credential-guessing defense (those live on the pre-session auth routes).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import Depends

from app.core.config import settings
from app.features.auth.dependencies import get_current_user
from app.features.users.model import User
from app.infrastructure.redis import Redis
from app.infrastructure.redis.dependencies import get_redis
from app.security.rate_limit import enforce

_HOUR = timedelta(hours=1)


async def rate_limit_upload(
    current_user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Cap uploads (AI-extracting and manual alike) per user."""
    # Settings are read at call time so tests can monkeypatch the limit.
    await enforce(
        redis,
        scope="cashout_upload_user",
        identifier=str(current_user.id),
        limit=settings.rate_limit.UPLOADS_PER_USER_PER_HOUR,
        window=_HOUR,
    )


async def rate_limit_extract(
    current_user: Annotated[User, Depends(get_current_user)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> None:
    """Cap on-demand re-extractions per user."""
    # Settings are read at call time so tests can monkeypatch the limit.
    await enforce(
        redis,
        scope="cashout_extract_user",
        identifier=str(current_user.id),
        limit=settings.rate_limit.EXTRACTS_PER_USER_PER_HOUR,
        window=_HOUR,
    )


__all__ = ["rate_limit_extract", "rate_limit_upload"]
