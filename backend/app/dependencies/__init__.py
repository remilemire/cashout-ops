# backend/app/dependencies/__init__.py

from __future__ import annotations

from .auth import get_current_user, require_admin, require_verified_user
from .csrf import require_csrf
from .db import get_db
from .email import get_email_client
from .processor import get_cashout_document_processor
from .redis import get_redis
from .storage import get_document_storage

__all__ = [
    "get_cashout_document_processor",
    "get_current_user",
    "get_db",
    "get_document_storage",
    "get_email_client",
    "get_redis",
    "require_admin",
    "require_csrf",
    "require_verified_user",
]
