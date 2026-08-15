# backend/app/features/users/types.py

from __future__ import annotations

from enum import StrEnum


# STAFF submits cashouts; ADMIN additionally manages users and reviews every
# submission; OWNER has admin access but cannot be promoted, demoted, or
# deleted. At most one owner exists (enforced by ix_users_single_owner) —
# ownership only moves via an explicit owner-to-admin transfer.
#
# That index is partial, so zero owners is a legal state: the window before
# BOOTSTRAP_OWNER_EMAIL first signs in. Past it the owner is unremovable
# through the API, so going ownerless again takes an out-of-band database
# edit — after which a sign-in at the bootstrap address reclaims ownership
# (see features/auth/email_challenges/service.py).
#
# That recovery holds only while the bootstrap address has no row of its own.
# Re-creating an account there is an ordinary admin action once ownership has
# moved on, and it disarms the recovery permanently: nothing promotes an
# existing account to OWNER, so an ownerless deployment in that state is a
# manual fix.
class UserRole(StrEnum):
    STAFF = "staff"
    ADMIN = "admin"
    OWNER = "owner"
