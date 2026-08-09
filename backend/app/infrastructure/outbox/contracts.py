# backend/app/infrastructure/outbox/contracts.py

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

# Covariant because definitions only expose their payload type; this also lets
# OutboxMessageDefinition[SpecificPayload] satisfy OutboxMessageDefinition[BaseModel]
# and avoids Pylance's invariant type-parameter assignment warning.
TPayload_co = TypeVar("TPayload_co", bound=BaseModel, covariant=True, default=BaseModel)


@dataclass(frozen=True)
class OutboxMessageDefinition(Generic[TPayload_co]):
    type: str
    payload: type[TPayload_co]


class OutboxHandler[TPayload: BaseModel = BaseModel](Protocol):
    message: OutboxMessageDefinition[TPayload]

    async def handle(self, payload: TPayload) -> None: ...
    async def on_dead_letter(self, payload: TPayload) -> None: ...


# Registry values are handlers for heterogeneous payload types; `Any` is what
# makes a concrete OutboxHandler[SpecificPayload] assignable here (TPayload is
# invariant because it appears in `handle`'s parameter position).
type OutboxHandlerRegistry = Mapping[str, OutboxHandler[Any]]

__all__ = ["OutboxMessageDefinition", "OutboxHandler", "OutboxHandlerRegistry"]
