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


def hash_identifier(identifier: str) -> str:
    """Hash a normalized identifier into a stable Redis key component.

    This keeps plaintext identifiers out of key names, not out of stored
    values or command logs. Low-entropy identifiers such as email addresses
    can be recovered by enumeration; this is not a confidentiality control.
    Callers must normalize the identifier before hashing it.
    """
    return hashlib.sha256(identifier.encode()).hexdigest()
