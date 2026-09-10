from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.errors import AppError, error_responses, init_error_handlers
from app.lifespan import lifespan

DESCRIPTION = """\
Internal API for the Whiskey District end-of-shift cashout flow: cashiers open a
submission and upload TouchBistro reports and terminal server summaries.
An AI pipeline classifies and extracts each document after upload; the cashier
polls the analysis, verifies each extraction (correcting it if needed), and
then completes the cashout.

## Conventions

- JSON is **camelCase** in and out; timestamps are ISO-8601 UTC with a trailing `Z`.
- Authentication is a `session_token` HttpOnly cookie, set when a passwordless
  email challenge is completed (`/auth/email-challenges/verify-code`) or an
  OAuth sign-in succeeds.
- Authenticated mutations require the double-submit CSRF check: send the JS-readable
  `csrf_token` cookie's value in the `x-csrf-token` header.
- Error responses contain `kind`, `code`, and a public JSON `ctx` object.
  Validation failures may also contain `issues`, each with a Pydantic `code`,
  camelCase `path`, and safe constraint `ctx`. The frontend supplies messages.
"""

OPENAPI_TAGS = [
    {
        "name": "auth",
        "description": (
            "Passwordless login. Accepted email submissions return a "
            "challenge ID for both known and unknown addresses. Eligible "
            "accounts receive a one-time code; verifying it with the "
            "challenge ID starts a cookie session. OAuth sign-in (Google) "
            "is a browser navigation: /oauth/{issuer}/start redirects to "
            "the provider and its callback starts the same cookie session "
            "for an existing account. Accounts are created by admins."
        ),
    },
    {"name": "users", "description": "The authenticated user."},
    {
        "name": "cashout",
        "description": (
            "Cashout submissions, their documents, AI extraction, and "
            "verification. Per document: upload (starts a background "
            "extraction, returns an `EXTRACTING` analysis) → poll the "
            "analysis until `NEEDS_VERIFICATION` or `FAILED` → verify. Then "
            "complete the submission (`PROCESSING` → `COMPLETED`)."
        ),
    },
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cashout Operations | Whiskey District",
        description=DESCRIPTION,
        version="1.0.0",
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
        debug=settings.app.DEBUG,
        responses=error_responses("INTERNAL"),
    )

    init_error_handlers(app)

    app.include_router(api_router)

    # check_dir=False so importing the app doesn't require a built frontend:
    # static/assets is gitignored build output, absent until `frontend-build`,
    # so the backend test suite can import app.main without a prior SPA build.
    app.mount(
        "/assets",
        StaticFiles(directory="static/assets", check_dir=False),
        name="assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):  # type: ignore[reportUnusedFunction]
        # Unknown /api paths must surface as JSON 404s, not the SPA shell.
        if full_path == "api" or full_path.startswith("api/"):
            raise AppError("ROUTE_NOT_FOUND")
        return FileResponse("static/index.html")

    return app


configure_logging()

app = create_app()
