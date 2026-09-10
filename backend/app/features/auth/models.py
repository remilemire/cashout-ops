"""Auth ORM models registered with the database metadata.

Sessions, email challenges, and pending OAuth flows are stored in Redis;
external identity links are stored in PostgreSQL.
"""

from __future__ import annotations

from .oauth.external_identities.model import ExternalIdentity

__all__ = ["ExternalIdentity"]
