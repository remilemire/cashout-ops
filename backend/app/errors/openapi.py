# backend/app/errors/openapi.py

from __future__ import annotations

from .schemas import ErrorBody
from .types import ErrorStatus

ERROR_RESPONSES: dict[int, dict[str, type[ErrorBody]]] = {
    status.value: {"model": ErrorBody} for status in ErrorStatus
}
