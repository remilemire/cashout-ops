# backend/tests/support/fixtures/integrations.py

"""Fake integration clients, and the real processor wired over them."""

from __future__ import annotations

import pytest

from app.document_ai import DocumentAIClient
from app.features.cashout.extraction import CashoutDocumentProcessor

from ..fakes import FakeAIClient, FakeDocumentStorage, FakeEmailClient, FakeOAuthClient


@pytest.fixture
def storage() -> FakeDocumentStorage:
    return FakeDocumentStorage()


@pytest.fixture
def ai_client() -> FakeAIClient:
    return FakeAIClient()


@pytest.fixture
def email_client() -> FakeEmailClient:
    return FakeEmailClient()


@pytest.fixture
def oauth_client() -> FakeOAuthClient:
    return FakeOAuthClient()


@pytest.fixture
def processor(
    ai_client: FakeAIClient, storage: FakeDocumentStorage
) -> CashoutDocumentProcessor:
    # Real processor + DocumentAIClient over the fake provider and storage.
    return CashoutDocumentProcessor(
        DocumentAIClient(
            ai_client,
            storage,
            classification_max_tokens=512,
            extraction_max_tokens=2048,
        )
    )


__all__ = ["ai_client", "email_client", "oauth_client", "processor", "storage"]
