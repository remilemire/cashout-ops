# backend/app/main.py

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.core.config import settings
from app.errors import AppError
from app.errors.handlers import init_error_handlers
from app.errors.openapi import error_responses
from app.lifespan import lifespan

DESCRIPTION = """\
Internal API for the Whiskey District end-of-shift cashout flow: cashiers open a
submission and upload the shift documents (TouchBistro reports, terminal
reports, receipts, tip-out sheets, cash summaries). An AI pipeline classifies
and extracts each document in the background after upload; the cashier polls
the analysis, verifies each extraction (correcting it if needed), and then
completes the cashout.

## Conventions

- JSON is **camelCase** in and out; timestamps are ISO-8601 UTC with a trailing `Z`.
- Authentication is a `session_token` HttpOnly cookie (set by register/login).
- Unsafe methods require the double-submit CSRF check: send the JS-readable
  `csrf_token` cookie's value in the `x-csrf-token` header.
- Errors always use one body shape: `{ "kind", "code", "message", "issues" }`,
  where `issues` (per-field details) is present only for validation failures
  (`kind: "VALIDATION"`).
"""

OPENAPI_TAGS = [
    {"name": "auth", "description": "Register, login, and logout (cookie sessions)."},
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
        debug=settings.DEBUG,
        responses=error_responses("INTERNAL"),
    )

    init_error_handlers(app)

    app.include_router(api_router)

    app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):  # type: ignore[reportUnusedFunction]
        # Unknown /api paths must surface as JSON 404s, not the SPA shell.
        if full_path == "api" or full_path.startswith("api/"):
            raise AppError("NOT_FOUND")
        return FileResponse("static/index.html")

    return app


app = create_app()
