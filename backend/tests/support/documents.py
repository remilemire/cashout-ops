# backend/tests/support/documents.py

"""Sample document payloads for upload tests.

The app never parses uploaded bytes (it stores them, checksums them, and hands
them to the — faked — AI), so tiny placeholder bytes are sufficient. The PNG is
a genuinely valid 1x1 image in case something ever sniffs it.
"""

from __future__ import annotations

import base64

SAMPLE_PDF_BYTES = b"%PDF-1.4 fake bytes"
SAMPLE_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

# (filename, bytes, mime) tuples in the shape httpx's `files=` expects.
SAMPLE_PDF_UPLOAD = ("receipt.pdf", SAMPLE_PDF_BYTES, "application/pdf")
SAMPLE_PNG_UPLOAD = ("receipt.png", SAMPLE_PNG_BYTES, "image/png")
