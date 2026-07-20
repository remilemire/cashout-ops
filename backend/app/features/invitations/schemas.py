# backend/app/features/invitations/schemas.py

from __future__ import annotations

import uuid

from pydantic import EmailStr

from app.core.schemas import BaseIn, EntityOut, UtcDateTime


class InvitationOut(EntityOut):
    email: EmailStr
    expires_at: UtcDateTime
    accepted_at: UtcDateTime | None = None
    invited_by_user_id: uuid.UUID
    accepted_by_user_id: uuid.UUID | None = None


class InvitationCreate(BaseIn):
    email: EmailStr
