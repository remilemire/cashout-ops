# backend/app/security/crypto.py

from __future__ import annotations

import hashlib
import secrets


def generate_secret_token() -> str:
    return secrets.token_urlsafe(32)


def hash_secret_token(token: str) -> str:
    """Digest a secret this application issued.

    Unsalted SHA-256 is sound here only because the input is high-entropy:
    session tokens and sign-in codes are unguessable, so the digest cannot be
    reversed by enumeration. Do not reach for this to hide a value the caller
    did not mint — see `hash_identifier`.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def hash_identifier(identifier: str) -> str:
    """Digest a caller-supplied identifier into a stable Redis key component.

    Same primitive as `hash_secret_token`, deliberately named apart because
    it makes a weaker promise. Identifiers such as email addresses are
    low-entropy, so the digest is reversible by enumeration and is NOT a
    confidentiality control. What it buys is that the plaintext stays out of
    key names, which leak into surfaces values do not: SCAN/KEYS output,
    MONITOR, the slowlog, per-key metrics, and logged keys.

    Callers normalize before hashing; the digest is only as stable as the
    normalization applied to its input.
    """
    return hashlib.sha256(identifier.encode()).hexdigest()
