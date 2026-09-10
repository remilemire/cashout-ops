# backend/tests/integration/test_errors.py

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from psycopg.errors import UniqueViolation
from pydantic import Field, JsonValue
from sqlalchemy.exc import IntegrityError

from app.core.schemas import BaseIn
from app.errors import AppError, RateLimitedError, error_responses, init_error_handlers


@pytest.mark.parametrize(
    ("error", "status", "body"),
    [
        (
            AppError("UPLOAD_TOO_LARGE", "private diagnostic", ctx={"maxSizeMb": 7}),
            400,
            {
                "kind": "BAD_REQUEST",
                "code": "UPLOAD_TOO_LARGE",
                "ctx": {"maxSizeMb": 7},
            },
        ),
        (
            AppError("FORBIDDEN", "private diagnostic"),
            403,
            {"kind": "FORBIDDEN", "code": "FORBIDDEN", "ctx": {}},
        ),
        (
            RateLimitedError(120, "private diagnostic"),
            429,
            {
                "kind": "TOO_MANY_REQUESTS",
                "code": "RATE_LIMITED",
                "ctx": {"retryAfterSeconds": 120},
            },
        ),
        (
            IntegrityError("private SQL", {}, UniqueViolation("private diagnostic")),
            409,
            {"kind": "CONFLICT", "code": "CONFLICT", "ctx": {}},
        ),
        (
            HTTPException(404, "private diagnostic"),
            404,
            {"kind": "NOT_FOUND", "code": "ROUTE_NOT_FOUND", "ctx": {}},
        ),
        (
            RuntimeError("private diagnostic"),
            500,
            {"kind": "INTERNAL", "code": "INTERNAL", "ctx": {}},
        ),
    ],
)
async def test_error_responses_expose_only_the_public_contract(
    error: Exception,
    status: int,
    body: dict[str, JsonValue],
) -> None:
    app = FastAPI()
    init_error_handlers(app)

    def fail() -> None:
        raise error

    app.add_api_route("/failure", fail)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/failure")

    assert response.status_code == status
    assert response.json() == body
    assert response.headers.get("Retry-After") == ("120" if status == 429 else None)


class Payload(BaseIn):
    full_name: str = Field(min_length=3)
    count: int = Field(ge=0)


async def test_request_validation_and_openapi_share_the_code_context_contract() -> None:
    app = FastAPI()
    init_error_handlers(app)

    def accept(payload: Payload) -> None:
        pass

    app.add_api_route(
        "/payload",
        accept,
        methods=["POST"],
        responses=error_responses(
            "VALIDATION_FAILED", "RATE_LIMITED", "EMAIL_TAKEN", "CONFLICT"
        ),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/payload", json={"fullName": "x", "count": -1})

    assert response.status_code == 422
    assert response.json() == {
        "kind": "VALIDATION",
        "code": "VALIDATION_FAILED",
        "ctx": {},
        "issues": [
            {"code": "string_too_short", "path": ["fullName"], "ctx": {"minLength": 3}},
            {"code": "greater_than_equal", "path": ["count"], "ctx": {"ge": 0}},
        ],
    }
    openapi = app.openapi()
    schemas = openapi["components"]["schemas"]
    assert set(schemas["ErrorResponseSchema"]["properties"]) == {
        "kind",
        "code",
        "ctx",
        "issues",
    }
    assert set(schemas["ValidationIssue"]["properties"]) == {"code", "path", "ctx"}
    responses = openapi["paths"]["/payload"]["post"]["responses"]
    examples = responses["422"]["content"]["application/json"]["examples"]
    assert examples["VALIDATION_FAILED"]["value"]["issues"] == [
        {"code": "missing", "path": ["field"], "ctx": {}},
    ]
    assert set(responses["409"]["content"]["application/json"]["examples"]) == {
        "EMAIL_TAKEN",
        "CONFLICT",
    }
    retry = responses["429"]["content"]["application/json"]["examples"]["RATE_LIMITED"][
        "value"
    ]
    assert retry["ctx"] == {"retryAfterSeconds": 60}
