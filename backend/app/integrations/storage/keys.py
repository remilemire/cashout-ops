from __future__ import annotations

from pathlib import PurePosixPath

from .errors import InvalidStorageKeyError


def validate_storage_key(storage_key: str) -> str:
    """Validate a relative POSIX storage key without rewriting it.

    Rejects empty paths, surrounding whitespace, absolute paths, and parent
    segments. These lexical checks do not resolve filesystem symlinks or
    establish object ownership; local storage assumes a controlled root.
    """
    if storage_key != storage_key.strip():
        raise InvalidStorageKeyError(storage_key)

    pure = PurePosixPath(storage_key)
    if not pure.parts or pure.is_absolute() or ".." in pure.parts:
        raise InvalidStorageKeyError(storage_key)

    return storage_key


__all__ = ["validate_storage_key"]
