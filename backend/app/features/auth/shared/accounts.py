"""Resolving a mailbox-proven address to a local account.

Both sign-in flows land here once they hold proof that the person controls
the address: the email challenge when its emailed code comes back, OAuth
when the issuer asserts a verified address. That proof is the whole
precondition for the owner bootstrap, so the rule lives beside the flows
rather than inside either one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.users import service as users_service
from app.features.users.schemas import UserCreate

if TYPE_CHECKING:
    from app.features.users.model import User


async def may_bootstrap_owner(db: AsyncSession, *, email: str) -> bool:
    """Whether this address may become the owner on a proven sign-in.

    Only the configured bootstrap address, and only while the deployment has
    no owner at all — the one state the single-owner invariant leaves open.
    A database that lost its owner therefore heals on the next sign-in
    there, while an address whose ownership has moved on is just another
    unknown one. Saying that outright beats attempting the insert and
    letting ix_users_single_owner reject it.

    It is a check, not a guarantee: two concurrent sign-ins can both pass
    here, so the index (and the SAVEPOINT in users' `add_if_unique`) stays
    the thing that actually holds the invariant.

    The address is compared first, so the ownership query runs only for it —
    never on an ordinary unknown-address probe.
    """
    if email != settings.bootstrap.OWNER_EMAIL:
        return False

    return not await users_service.owner_exists(db)


async def resolve(db: AsyncSession, *, email: str) -> User | None:
    """The account behind a proven address, bootstrapping the owner.

    Callers must reach this only with mailbox proof in hand — a consumed
    challenge code, or an issuer's verified-email claim. Creating the owner
    any earlier would let an unauthenticated request mint it, which is why
    the account appears here rather than where a flow starts.

    Bootstrapping is gated on the deployment having no owner rather than on
    the deployment being new (`may_bootstrap_owner`), so ownership is
    reclaimable after an out-of-band loss, and an address whose ownership
    has moved on is turned away here instead of at the unique index. It
    does not promote an existing non-owner account: the lookup below returns
    that account unchanged. Promoting an existing account to owner requires
    an explicit ownership transfer by the current owner.

    None means the sign-in cannot proceed: the address has no account and
    may not claim ownership, or the bootstrap lost a race to a concurrent
    sign-in at the same address. Each flow reports its own unified error, so
    neither case is distinguishable from the outside.
    """
    user = await users_service.find_by_email(db, email=email)

    if user is None and await may_bootstrap_owner(db, email=email):
        # No flow registers the owner, so its first proven sign-in creates
        # the account — through whichever flow that sign-in happens to be.
        user = await users_service.bootstrap_owner(
            db,
            payload=UserCreate(
                email=settings.bootstrap.OWNER_EMAIL,
                full_name=settings.bootstrap.OWNER_FULL_NAME,
            ),
        )

    return user


__all__ = ["may_bootstrap_owner", "resolve"]
