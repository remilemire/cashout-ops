# backend/app/integrations/storage/keys.py

from __future__ import annotations

from pathlib import PurePosixPath

from .errors import InvalidStorageKeyError


def validate_storage_key(storage_key: str) -> str:
    """Return `storage_key` unchanged if it safely addresses content in a root.

    A storage key is an opaque, relative POSIX path used to locate content
    inside a storage root. To guarantee it can never escape that root — no
    matter the backend — the key must be non-empty, relative (not absolute),
    and free of parent-directory (`..`) segments. Anything else raises
    `InvalidStorageKeyError`.

    Keys are validated, not rewritten: a suspicious key is rejected rather than
    silently coerced into a different (and possibly colliding) location.
    """
    if storage_key != storage_key.strip():
        raise InvalidStorageKeyError(storage_key)

    pure = PurePosixPath(storage_key)
    if not pure.parts or pure.is_absolute() or ".." in pure.parts:
        raise InvalidStorageKeyError(storage_key)

    return storage_key


__all__ = ["validate_storage_key"]
