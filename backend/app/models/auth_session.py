# backend/app/models/auth_session.py

from __future__ import annotations

from .base import Entity


class AuthSession(Entity):
    __tablename__ = "auth_sessions"
    """
    # TODO:

    token_hash
    expires_at

    # relationships:

    user

    """
