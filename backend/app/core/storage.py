# backend/app/core/storage.py

from __future__ import annotations

from enum import StrEnum


class StorageProvider(StrEnum):
    LOCAL = "LOCAL"
    S3 = "S3"


__all__ = ["StorageProvider"]
