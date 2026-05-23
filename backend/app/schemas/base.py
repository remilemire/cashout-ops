# backend/app/schemas/base.py

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, field_serializer

from app.utils.casing import snake_to_camel


class BaseOut(BaseModel):
    model_config = ConfigDict(alias_generator=snake_to_camel, from_attributes=True)

    def to_response(self):
        return self.model_dump(by_alias=True, exclude_none=True, mode="json")


class BaseIn(BaseModel):
    model_config = ConfigDict(
        alias_generator=snake_to_camel, validate_by_name=True, extra="forbid"
    )

    def to_update(self):
        return self.model_dump(exclude_unset=True)


class EntityOut(BaseOut):
    id: int
    created_at: datetime

    # Database timezone is UTC
    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
