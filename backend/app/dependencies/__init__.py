# backend/app/dependencies/__init__.py

from __future__ import annotations

from .auth import get_current_user, require_admin
from .background import PostCommitTasks, get_post_commit_tasks
from .clients import get_cashout_document_processor, get_document_storage
from .csrf import require_csrf
from .db import get_db, get_db_sessionmaker

__all__ = [
    "PostCommitTasks",
    "get_cashout_document_processor",
    "get_current_user",
    "get_db",
    "get_db_sessionmaker",
    "get_document_storage",
    "get_post_commit_tasks",
    "require_admin",
    "require_csrf",
]
