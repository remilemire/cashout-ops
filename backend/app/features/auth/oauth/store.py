# backend/app/features/auth/oauth/store.py

"""Redis storage for pending OAuth flows.

- ``oauth_flow:{flow_id}`` holds a JSON-encoded :class:`StoredOAuthFlow` and
  expires after ``AUTH_OAUTH_FLOW_TTL_MINUTES`` — Redis TTLs enforce expiry,
  so a missing key covers both "never started" and "expired".
- No hashing here: the stored state/nonce/code_verifier are single-use CSPRNG
  values that never leave the server, not user-presented credentials — the
  browser only ever carries the flow id.
"""

from __future__ import annotations

from datetime import timedelta

from pydantic import ValidationError

from app.core.config import settings
from app.infrastructure.redis import Redis

from .model import StoredOAuthFlow


def _flow_key(flow_id: str) -> str:
    return f"oauth_flow:{flow_id}"


async def save(redis: Redis, *, flow_id: str, flow: StoredOAuthFlow) -> None:
    ttl = timedelta(minutes=settings.auth.OAUTH_FLOW_TTL_MINUTES)
    await redis.set(_flow_key(flow_id), flow.model_dump_json(), ex=ttl)


async def find(redis: Redis, *, flow_id: str) -> StoredOAuthFlow | None:
    """The stored flow, or None if absent/expired."""
    value = await redis.get(_flow_key(flow_id))

    if value is None:
        return None

    try:
        return StoredOAuthFlow.model_validate_json(str(value))
    except ValidationError:
        # A malformed stored value is treated as missing, mirroring expiry.
        return None


async def delete(redis: Redis, *, flow_id: str) -> bool:
    """Delete the flow; False if it was already gone.

    The checked delete is what makes consumption single-use under
    concurrency: of two racing callbacks, only one observes the removal.
    """
    return await redis.delete(_flow_key(flow_id)) > 0


__all__ = ["save", "find", "delete"]
