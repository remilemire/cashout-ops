# backend/app/features/auth/sessions/types.py

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .model import Session


@dataclass(frozen=True)
class SessionWithToken:
    session: Session
    session_token: str
