# backend/app/errors/__init__.py

from __future__ import annotations

# Deliberately minimal: feature error modules import `app.errors.contracts`,
# which initializes this package, so pulling the aggregators (codes, catalog,
# handlers, ...) in here would be a circular import. Import `error_responses`
# from `app.errors.openapi` and `init_error_handlers` from `app.errors.handlers`.
from .app_error import AppError
from .validation import ValidationError

__all__ = ["AppError", "ValidationError"]
