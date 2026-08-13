# backend/app/features/auth/external_identities/model.py

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.models import Base, enum_column
from app.integrations.oauth.issuers import OAuthIssuer


class ExternalIdentity(Base):
    """A link between a local account and an OAuth issuer identity.

    `(issuer, subject)` is the durable key — the issuer's `sub` claim never
    changes, unlike its email. A user holds at most one identity per issuer.
    """

    __tablename__ = "external_identities"
    # Named unique indexes: a violation reports the index name, which the
    # centralized integrity translator can map to a feature code.
    __table_args__ = (
        Index(
            "ix_external_identities_issuer_subject",
            "issuer",
            "subject",
            unique=True,
        ),
        Index(
            "ix_external_identities_user_issuer",
            "user_id",
            "issuer",
            unique=True,
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    issuer: Mapped[OAuthIssuer] = mapped_column(
        enum_column(OAuthIssuer, "oauth_issuer"), nullable=False
    )

    subject: Mapped[str] = mapped_column(String(255), nullable=False)

    # id/created_at last to match the migration's physical column order.
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
