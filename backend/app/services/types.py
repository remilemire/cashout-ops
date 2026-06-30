# backend/app/services/types.py

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Session, User


@dataclass(frozen=True)
class SessionWithToken:
    session: Session
    session_token: str


@dataclass(frozen=True)
class UserWithSessionToken:
    user: User
    session_token: str


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: Session
