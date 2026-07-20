# backend/app/dependencies/__init__.py

from __future__ import annotations

from .auth import get_current_user, require_admin, require_verified_user
from .background import PostCommitTasks, get_post_commit_tasks
from .csrf import require_csrf
from .db import get_db, get_db_sessionmaker
from .email import get_email_client
from .processor import get_cashout_document_processor
from .storage import get_document_storage

__all__ = [
    "PostCommitTasks",
    "get_cashout_document_processor",
    "get_current_user",
    "get_db",
    "get_db_sessionmaker",
    "get_document_storage",
    "get_email_client",
    "get_post_commit_tasks",
    "require_admin",
    "require_csrf",
    "require_verified_user",
]
