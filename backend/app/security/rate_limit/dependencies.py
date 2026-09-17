from __future__ import annotations

from datetime import timedelta
from ipaddress import IPv6Address, ip_address

from fastapi import Request

from app.core.config import settings
from app.errors import RateLimitedError
from app.infrastructure.redis import Redis

from . import store


async def enforce(
    redis: Redis, *, scope: str, identifier: str, limit: int, window: timedelta
) -> None:
    """Count one hit against ``{scope}:{identifier}``; raise once over limit."""
    hit = await store.count_hit(
        redis, scope=scope, identifier=identifier, window=window
    )

    if hit.count > limit:
        raise RateLimitedError(hit.retry_after_seconds)


def client_ip(request: Request) -> str:
    """The client IP to key per-IP rate limits on."""
    if settings.rate_limit.CLIENT_IP_SOURCE == "cloudflare":
        # Only enable behind an edge that overwrites this header, with no
        # untrusted private-network bypass. Reject ambiguity and never fall
        # back to request.client: wildcard proxy trust may have rewritten it
        # from an attacker-controlled X-Forwarded-For prefix.
        values = request.headers.getlist("cf-connecting-ip")
        if len(values) != 1:
            return "unknown"
        value = values[0].strip()
        # Scoped IPv6 addresses are not public client identities. Their zone
        # suffix could otherwise create arbitrary buckets for the same IP.
        if "%" in value:
            return "unknown"
        try:
            address = ip_address(value)
        except ValueError:
            return "unknown"
        if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        return str(address)

    return "unknown" if request.client is None else request.client.host


__all__ = ["client_ip", "enforce"]
