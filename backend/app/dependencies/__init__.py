# backend/app/dependencies/__init__.py

from __future__ import annotations

from .auth import get_current_user, require_admin
from .clients import get_cashout_document_processor, get_document_storage
from .csrf import require_csrf
from .db import get_db

__all__ = [
    "get_cashout_document_processor",
    "get_current_user",
    "get_db",
    "get_document_storage",
    "require_admin",
    "require_csrf",
]
