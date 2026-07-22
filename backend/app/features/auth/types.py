# backend/app/features/auth/types.py

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.features.users.model import User

    from .sessions.model import Session


@dataclass(frozen=True)
class UserWithSessionToken:
    user: User
    session_token: str


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: Session
