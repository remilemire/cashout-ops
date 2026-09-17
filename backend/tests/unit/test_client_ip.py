"""Client identity at the rate limiter's deployment-specific trust boundary."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core.config import settings
from app.security.rate_limit import client_ip


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ([], "unknown"),
        ([""], "unknown"),
        (["not-an-ip"], "unknown"),
        (["198.51.100.1, 198.51.100.2"], "unknown"),
        (["198.51.100.1", "198.51.100.1"], "unknown"),
        (["198.51.100.1", "198.51.100.2"], "unknown"),
        (["198.51.100.1:1234"], "unknown"),
        (["[2001:db8::1]"], "unknown"),
        (["fe80::1%arbitrary-zone"], "unknown"),
        (["198.51.100.1"], "198.51.100.1"),
        ([" 198.51.100.1 "], "198.51.100.1"),
        (["2001:0db8:0000:0000:0000:0000:0000:0001"], "2001:db8::1"),
        (["::ffff:198.51.100.1"], "198.51.100.1"),
    ],
)
def test_cloudflare_identity_ignores_spoofable_fallbacks(
    monkeypatch: pytest.MonkeyPatch, headers: list[str], expected: str
) -> None:
    monkeypatch.setattr(settings.rate_limit, "CLIENT_IP_SOURCE", "cloudflare")
    for spoofed in ["203.0.113.1", "203.0.113.2"]:
        # Uvicorn may already have copied the spoofed XFF into scope.client.
        request = Request(
            {
                "type": "http",
                "client": (spoofed, 0),
                "headers": [(b"cf-connecting-ip", value.encode()) for value in headers]
                + [(b"x-forwarded-for", spoofed.encode())],
            }
        )
        assert client_ip(request) == expected


@pytest.mark.parametrize("peer", [None, ("127.0.0.1", 1234)])
def test_request_client_mode_ignores_cloudflare_header(
    monkeypatch: pytest.MonkeyPatch, peer: tuple[str, int] | None
) -> None:
    monkeypatch.setattr(settings.rate_limit, "CLIENT_IP_SOURCE", "request_client")
    request = Request(
        {
            "type": "http",
            "client": peer,
            "headers": [(b"cf-connecting-ip", b"198.51.100.1")],
        }
    )
    assert client_ip(request) == ("unknown" if peer is None else peer[0])
