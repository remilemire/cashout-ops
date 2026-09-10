from __future__ import annotations

from enum import StrEnum


# OWNER includes admin access and cannot be demoted or deleted through the
# ordinary role endpoints. Ownership transfers to an existing admin.
# The partial unique index permits at most one owner; bootstrap eligibility
# is decided by auth/shared/accounts.py.
class UserRole(StrEnum):
    STAFF = "staff"
    ADMIN = "admin"
    OWNER = "owner"
