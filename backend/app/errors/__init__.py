# backend/app/errors/__init__.py

from __future__ import annotations

from .app_error import AppError
from .validation import ValidationError

__all__ = ["AppError", "ValidationError"]
