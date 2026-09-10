from __future__ import annotations

from enum import StrEnum


class OAuthIssuer(StrEnum):
    """An identity issuer users can sign in with (Google, ...).

    Deliberately NOT one of core/providers.py's provider enums: those select
    exactly one implementation of a service, while issuers stack — every
    configured issuer is live at once. (If this app ever chooses between
    OAuth *client* implementations, that choice would be an OAuthProvider.)
    """

    GOOGLE = "google"


def enabled_issuers() -> frozenset[OAuthIssuer]:
    """The issuers whose credentials are configured.

    Enablement is derived, not configured: there is no issuer-selection
    setting, an issuer is on exactly when its credentials are set. Settings
    rejects a half-configured pair, so a plain truthiness check per issuer is
    the whole policy. The lifespan registers the same set.
    """
    # Imported here, not at module level: ORM models import OAuthIssuer, and
    # a top-level settings import would make loading the model registry (e.g.
    # from alembic's env) construct Settings as a side effect.
    from app.core.config import settings

    issuers: set[OAuthIssuer] = set()
    if settings.auth.GOOGLE_CLIENT_ID and settings.auth.GOOGLE_CLIENT_SECRET:
        issuers.add(OAuthIssuer.GOOGLE)
    return frozenset(issuers)


__all__ = ["OAuthIssuer", "enabled_issuers"]
