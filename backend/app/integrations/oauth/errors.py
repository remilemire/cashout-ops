# backend/app/integrations/oauth/errors.py

from __future__ import annotations


class OAuthExchangeError(Exception):
    """The issuer interaction failed.

    Covers the authorization-URL build, the code-for-token exchange, and
    ID-token validation. Clients raise this instead of Authlib/httpx/JOSE
    exceptions so callers see an application error naming the cause, never a
    provider library's internal exception type.
    """


__all__ = ["OAuthExchangeError"]
