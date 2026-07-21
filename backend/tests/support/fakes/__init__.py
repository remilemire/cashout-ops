# backend/tests/support/fakes/__init__.py

"""In-memory doubles for the AI, storage, and email integrations.

The document-extraction stack (processor, registry, DocumentAIClient) is real in
tests; only the AI *provider*, the object store, and the mailer are faked so
tests never make a network call or touch the filesystem.

SDK-shaped fakes for the provider adapter unit tests live in ``.sdk``.
"""

from .ai import FakeAIClient
from .email import FakeEmailClient, SentEmail
from .storage import FakeDocumentStorage

__all__ = [
    "FakeAIClient",
    "FakeDocumentStorage",
    "FakeEmailClient",
    "SentEmail",
]
