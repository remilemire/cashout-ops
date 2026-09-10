from __future__ import annotations

import hashlib
import secrets


def generate_secret_token() -> str:
    return secrets.token_urlsafe(32)


def hash_secret_token(token: str) -> str:
    """Hash an issued token or code for comparison without storing its plaintext.

    Session tokens have 256 bits of randomness. Six-digit sign-in codes have
    only one million possible values: their hashes can be guessed offline.
    Code expiry and attempt limits bound online guessing; hashing alone does
    not protect short codes if their stored hashes are exposed.
    """
    return hashlib.sha256(token.encode()).hexdigest()
