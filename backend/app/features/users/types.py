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
# through the API, so an ownerless deployment implies an out-of-band database
# edit. The sign-in flow reclaims ownership on its own only while the
# bootstrap address has no row (see features/auth/email_challenges/service.py)
# — nothing promotes an existing account to OWNER, and recovering from the
# remaining case is deliberately a manual job.
class UserRole(StrEnum):
    STAFF = "staff"
    ADMIN = "admin"
    OWNER = "owner"
