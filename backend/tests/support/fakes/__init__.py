# backend/tests/support/fakes/__init__.py

"""In-memory doubles for the AI, storage, email, and text-detection integrations.

The document-extraction stack (processor, registry, DocumentAIClient) is real in
tests; only the AI *provider*, the object store, the mailer, and the text
detector are faked so tests never make a network call, touch the filesystem,
or load the detection model.

SDK-shaped fakes for the provider adapter unit tests live in ``.sdk``.
"""

from .ai import FakeAIClient
from .email import FakeEmailClient, SentEmail
from .oauth import FakeOAuthClient
from .ocr import FakeTextDetector
from .storage import FakeDocumentStorage

__all__ = [
    "FakeAIClient",
    "FakeDocumentStorage",
    "FakeEmailClient",
    "FakeOAuthClient",
    "FakeTextDetector",
    "SentEmail",
]
