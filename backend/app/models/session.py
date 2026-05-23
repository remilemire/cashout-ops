# backend/app/models/session.py

from __future__ import annotations

from .base import Entity


class Session(Entity):
    __tablename__ = "sessions"
    """
    # TODO:

    token_hash
    expires_at

    # relationships:

    user

    """
