# backend/app/features/auth/external_identities/service.py

"""Mapping OAuth issuer identities to local accounts."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import AppError
from app.features.users import service as users_service
from app.integrations.oauth import OAuthIdentity

from . import repository
from .model import ExternalIdentity

if TYPE_CHECKING:
    from app.features.users.model import User


async def resolve_user(db: AsyncSession, *, identity: OAuthIdentity) -> User:
    """Resolve an issuer identity to a local account, linking on first use.

    An `(issuer, subject)` match wins — the subject claim is durable across
    issuer-side email changes. Otherwise a VERIFIED issuer email may claim
    the local account with that address, creating the link. Never creates an
    account: accounts are admin-provisioned, so an unmatched identity is
    rejected outright.
    """
    linked = await repository.find_by_issuer_subject(
        db, issuer=identity.issuer, subject=identity.subject
    )
    if linked is not None:
        user = await users_service.find_by_id(db, user_id=linked.user_id)
        if user is None:
            # The FK cascade removes links with their user, so this only
            # covers a user deleted after the link was loaded.
            raise AppError("OAUTH_ACCOUNT_NOT_FOUND")
        return user

    if not identity.email_verified or identity.email is None:
        raise AppError("OAUTH_ACCOUNT_NOT_FOUND")

    user = await users_service.find_by_email(db, email=identity.email)
    if user is None:
        raise AppError("OAUTH_ACCOUNT_NOT_FOUND")

    link = ExternalIdentity(
        user_id=user.id, issuer=identity.issuer, subject=identity.subject
    )
    await repository.add(db, link)

    return user


__all__ = ["resolve_user"]
