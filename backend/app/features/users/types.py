# backend/app/features/users/types.py

from __future__ import annotations

from enum import StrEnum


# STAFF submits cashouts; ADMIN additionally manages users and reviews every
# submission; OWNER has admin access but cannot be promoted, demoted, or
# deleted. At most one owner exists (enforced by ix_users_single_owner) —
# ownership only moves via an explicit owner-to-admin transfer.
class UserRole(StrEnum):
    STAFF = "staff"
    ADMIN = "admin"
    OWNER = "owner"
