# backend/tests/support/settings.py

"""The suite's hermetic settings baseline.

Every group is constructed with the dotenv source removed (`_env_file=None`),
so a developer's `backend/.env` never shapes test behavior. Kwargs are passed
only where a value is semantically required; everything else exercises the
code defaults. `os.environ` still outranks those defaults by design — it is
how CI and the conftest pins configure the suite.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.config import (
    AISettings,
    AppSettings,
    AuthSettings,
    BootstrapSettings,
    DbSettings,
    EmailSettings,
    OutboxSettings,
    RateLimitSettings,
    RedisSettings,
    Settings,
    StorageSettings,
    TipoutSettings,
)

# `Settings(_env_file=None)` alone would not cut .env: each group is built by
# its own zero-argument default_factory, which re-reads .env itself. Every
# group is therefore constructed here explicitly, with this unpacked in.
_NO_DOTENV: dict[str, Any] = {"_env_file": None}


def make_test_settings() -> Settings:
    """Build a Settings whose every group ignores `backend/.env`."""
    groups: dict[str, Any] = {
        # The default model (claude-sonnet-5) is Anthropic's, so its key is
        # the one _validate_ai_credentials requires.
        "ai": AISettings(**_NO_DOTENV, ANTHROPIC_API_KEY="test-anthropic-key"),
        "app": AppSettings(**_NO_DOTENV, ENV="dev"),
        # Google credentials present, like the AI key above: enablement is
        # derived from them, the fake OAuth client is the seam (no issuer is
        # ever dialed), and integration tests exercise the enabled path by
        # default. Disabled-path tests monkeypatch the pair to None.
        "auth": AuthSettings(
            **_NO_DOTENV,
            GOOGLE_CLIENT_ID="test-google-client-id",
            GOOGLE_CLIENT_SECRET="test-google-client-secret",
            # Every login() is three padded requests, so the default floor
            # would add minutes of pure sleep to the suite. The floor's own
            # tests monkeypatch a real value.
            CHALLENGE_TIME_FLOOR_MS=0,
        ),
        # Matches the OWNER_EMAIL literal in tests/support/api.py.
        "bootstrap": BootstrapSettings(**_NO_DOTENV, OWNER_EMAIL="owner@test.com"),
        # URL is required but never dialed — real connections come from
        # TEST_DATABASE_URL/testcontainers via dependency_overrides. It must be
        # passed under the field's validation_alias: `URL=...` would be
        # silently swallowed by extra="ignore".
        "db": DbSettings(
            **{**_NO_DOTENV, "DATABASE_URL": "postgresql+psycopg://unused/unused"}
        ),
        "email": EmailSettings(**_NO_DOTENV),
        "outbox": OutboxSettings(**_NO_DOTENV),
        "rate_limit": RateLimitSettings(**_NO_DOTENV),
        # Required field; a placeholder for the same reason as db above.
        "redis": RedisSettings(**_NO_DOTENV, URL="redis://unused:6379/0"),
        # The default provider (LOCAL) requires a directory.
        "storage": StorageSettings(**_NO_DOTENV, LOCAL_DIR=Path("storage/documents")),
        "tipout": TipoutSettings(**_NO_DOTENV),
    }
    # A settings group added to Settings but not to `groups` would fall back to
    # its default_factory and silently re-read .env; fail loudly instead.
    missing = set(Settings.model_fields) - set(groups)
    if missing:
        raise RuntimeError(
            "make_test_settings() does not construct these settings groups: "
            f"{', '.join(sorted(missing))}. Add each one above with "
            "_env_file=None so the suite stays hermetic."
        )
    # The group instances pass through by identity: Settings does not
    # revalidate (and so cannot re-read .env for) an already built group.
    return Settings(**_NO_DOTENV, **groups)


__all__ = ["make_test_settings"]
