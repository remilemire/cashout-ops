# backend/tests/test_dependencies.py

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.dependencies.auth import require_verified_user
from app.errors import AppError
from app.features.users.model import User


def _user(*, verified: bool) -> User:
    return User(
        email="user@test.com",
        full_name="Test User",
        password_hash="!",
        email_verified_at=datetime.now(UTC) if verified else None,
    )


def test_require_verified_user_allows_verified() -> None:
    user = _user(verified=True)
    assert require_verified_user(user) is user


def test_require_verified_user_blocks_unverified() -> None:
    with pytest.raises(AppError) as exc:
        require_verified_user(_user(verified=False))
    assert exc.value.code == "EMAIL_NOT_VERIFIED"
