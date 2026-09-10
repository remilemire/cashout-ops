# backend/app/features/cashout/shared/access.py

"""The single authorization rule for cashout submissions.

A submission belongs to its employee; admins (and the owner) have full
control over every cashout, so acting and viewing share the same rule. One
act is theirs alone: adjusting a cashout's reconciliation.
Pure policy — no database access, no service imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.errors import AppError
from app.features.users.model import User
from app.features.users.types import UserRole

if TYPE_CHECKING:
    from app.features.cashout.submissions.model import CashoutSubmission


def is_admin(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.OWNER)


def ensure_can_view(submission: CashoutSubmission, user: User) -> None:
    if not is_admin(user) and submission.employee_user_id != user.id:
        raise AppError(
            "FORBIDDEN", "You do not have access to this cashout submission."
        )


def ensure_can_adjust(user: User) -> None:
    """Only an admin may correct the cross-check a cashout closes against."""
    if not is_admin(user):
        raise AppError(
            "FORBIDDEN", "Only an admin can adjust a cashout's reconciliation."
        )


__all__ = ["ensure_can_adjust", "ensure_can_view", "is_admin"]
