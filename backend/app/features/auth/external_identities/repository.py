# backend/app/features/auth/external_identities/repository.py

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.oauth.issuers import OAuthIssuer

from .model import ExternalIdentity


async def find_by_issuer_subject(
    db: AsyncSession, *, issuer: OAuthIssuer, subject: str
) -> ExternalIdentity | None:
    stmt = select(ExternalIdentity).where(
        ExternalIdentity.issuer == issuer,
        ExternalIdentity.subject == subject,
    )

    return (await db.execute(stmt)).scalar_one_or_none()


async def add(db: AsyncSession, identity: ExternalIdentity) -> None:
    """Stage the link and flush so unique/FK violations surface here, inside
    the caller's translation boundary, rather than at commit."""
    db.add(identity)
    await db.flush()


__all__ = ["find_by_issuer_subject", "add"]
