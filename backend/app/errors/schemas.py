# backend/app/errors/schemas.py

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, computed_field, field_serializer

from app.schemas.base import BaseOut
from app.utils.casing import snake_to_camel

from .messages import (
    CONFLICT_MESSAGES,
    CONTEXTUAL_UNPROCESSABLE_MESSAGES,
    ERROR_MESSAGES,
    UNPROCESSABLE_MESSAGES,
)
from .types import ConflictCode, UnprocessableCode, UnprocessableContext

# ================================
# ---------- Responses -----------
# ================================


class ServerErrorResponse(BaseOut):
    type: Literal["server_error"] = "server_error"
    message: str = ERROR_MESSAGES["server_error"]


class UnprocessableResponse(BaseOut):
    type: Literal["unprocessable"] = "unprocessable"
    message: str = ERROR_MESSAGES["unprocessable"]
    details: list[UnprocessableDetail] = Field(default_factory=lambda: [])


class ConflictResponse(BaseOut):
    type: Literal["conflict"] = "conflict"
    message: str = ERROR_MESSAGES["conflict"]
    details: list[ConflictDetail] = Field(default_factory=lambda: [])


class NotFoundResponse(BaseOut):
    type: Literal["not_found"] = "not_found"
    message: str = ERROR_MESSAGES["not_found"]


class ForbiddenResponse(BaseOut):
    type: Literal["forbidden"] = "forbidden"
    message: str = ERROR_MESSAGES["forbidden"]


class UnauthenticatedResponse(BaseOut):
    type: Literal["unauthenticated"] = "unauthenticated"
    message: str = ERROR_MESSAGES["unauthenticated"]


class BadRequestResponse(BaseOut):
    type: Literal["bad_request"] = "bad_request"
    message: str = ERROR_MESSAGES["server_error"]


type ErrorResponse = Annotated[
    ServerErrorResponse
    | BadRequestResponse
    | NotFoundResponse
    | UnauthenticatedResponse
    | ForbiddenResponse
    | ConflictResponse
    | UnprocessableResponse,
    Field(discriminator="type"),
]


# ================================
# ----------- Details ------------
# ================================


class BaseDetail(BaseOut):
    field: str

    @field_serializer("field")
    def serialize_field(self, value: str) -> str:
        return snake_to_camel(value)


class UnprocessableDetail(BaseDetail):
    code: UnprocessableCode = "invalid_value"
    ctx: UnprocessableContext = Field(
        default_factory=UnprocessableContext, exclude=True
    )

    @computed_field
    @property
    def message(self) -> str:
        return (
            CONTEXTUAL_UNPROCESSABLE_MESSAGES[self.code](self.ctx)
            if self.code in CONTEXTUAL_UNPROCESSABLE_MESSAGES
            else UNPROCESSABLE_MESSAGES[self.code]
        )


class ConflictDetail(BaseDetail):
    code: ConflictCode = "integrity"

    @computed_field
    @property
    def message(self) -> str:
        return CONFLICT_MESSAGES[self.code]
