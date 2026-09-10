from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from .issuers import OAuthIssuer

# The issuer's token response (access_token, id_token, ...). Opaque to
# callers: the flow service only shuttles it from `exchange_token` to
# `get_identity`, which needs the whole mapping (ID-token validation reads
# more than one field), so no narrower type would be honest.
OAuthToken: TypeAlias = Mapping[str, Any]


@dataclass(frozen=True)
class OAuthAuthorization:
    """Authorization URL and values retained for the callback.

    The URL includes state and nonce. The raw code_verifier is retained for
    the server-to-server token exchange; its challenge appears in the URL.
    """

    url: str
    state: str
    nonce: str
    code_verifier: str


@dataclass(frozen=True)
class OAuthIdentity:
    issuer: OAuthIssuer
    subject: str
    email: str | None
    email_verified: bool
    name: str | None


__all__ = ["OAuthAuthorization", "OAuthIdentity", "OAuthToken"]
