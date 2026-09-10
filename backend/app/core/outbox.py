from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

# Both covariant because definitions only expose their type and payload; this
# also lets OutboxMessageDefinition[SpecificType, SpecificPayload] satisfy
# OutboxMessageDefinition[str, BaseModel] and avoids Pylance's invariant
# type-parameter assignment warning.
TType_co = TypeVar("TType_co", bound=str, covariant=True, default=str)
TPayload_co = TypeVar("TPayload_co", bound=BaseModel, covariant=True, default=BaseModel)


@dataclass(frozen=True)
class OutboxMessageDefinition(Generic[TType_co, TPayload_co]):
    type: TType_co
    payload: type[TPayload_co]


type OutboxMessageDefinitionList[TType: str] = Sequence[OutboxMessageDefinition[TType]]


class OutboxHandler[TPayload: BaseModel = BaseModel](Protocol):
    # Read-only so the definition's type parameters stay covariant here: a
    # mutable protocol attribute is invariant, which would reject a handler
    # whose message is narrowed to its feature's own message type.
    @property
    def message(self) -> OutboxMessageDefinition[str, TPayload]: ...

    async def handle(self, payload: TPayload) -> None: ...
    async def on_dead_letter(self, payload: TPayload) -> None: ...


__all__ = ["OutboxMessageDefinition", "OutboxMessageDefinitionList", "OutboxHandler"]
