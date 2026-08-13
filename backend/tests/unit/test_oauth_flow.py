# backend/tests/unit/test_oauth_flow.py

"""Pure logic of the OAuth flow service."""

from __future__ import annotations

import pytest

from app.features.auth.oauth.service import sanitize_redirect_to


@pytest.mark.parametrize(
    ("redirect_to", "expected"),
    [
        ("/cashouts", "/cashouts"),
        ("/admin/users?tab=all", "/admin/users?tab=all"),
        (None, "/"),
        ("", "/"),
        # Off-origin escapes: protocol-relative, backslash trick, absolute URL.
        ("//evil.example", "/"),
        ("/\\evil.example", "/"),
        ("https://evil.example", "/"),
        # Not a path at all.
        ("cashouts", "/"),
    ],
)
def test_only_relative_paths_survive_sanitization(
    redirect_to: str | None, expected: str
) -> None:
    assert sanitize_redirect_to(redirect_to) == expected
