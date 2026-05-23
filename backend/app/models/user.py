# backend/app/models/user.py

from __future__ import annotations

from .base import Entity


class User(Entity):
    __tablename__ = "users"
    """
    # TODO:

    first_name
    last_name

    email
    password_hash

    role (.enums.UserRole)

    # relationships:

    auth_session
    shifts
    cashout_submissions (association proxy from shifts)

    """
