# backend/app/features/auth/models.py

"""The auth feature's persisted models, as one surface.

Auth keeps its ORM models inside the sub-feature that owns them, and most of
its state is not persisted at all (sessions, email challenges, and OAuth
flows live in Redis). This module is what the database registry imports, so
adding or moving a sub-feature's table never reaches past this boundary.
"""

from __future__ import annotations

from .oauth.external_identities.model import ExternalIdentity

__all__ = ["ExternalIdentity"]
