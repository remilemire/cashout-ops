"""Fake integration clients, and the real processor and cropper wired over them."""

from __future__ import annotations

import pytest

from app.document_ai import DocumentAIClient
from app.document_cropping import DocumentCropper
from app.features.cashout.extraction import CashoutDocumentProcessor

from ..fakes import (
    FakeAIClient,
    FakeDocumentStorage,
    FakeEmailClient,
    FakeOAuthClient,
    FakeTextDetector,
)


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
def text_detector() -> FakeTextDetector:
    # No boxes by default: uploads stay uncropped and extract from the
    # original, so tests that are not about cropping see the pre-crop flow.
    # A cropping test assigns `boxes` (see SAMPLE_PHOTO_TEXT_BOXES).
    return FakeTextDetector()


@pytest.fixture
def cropper(text_detector: FakeTextDetector) -> DocumentCropper:
    # Real cropper over the fake detector, with the settings defaults.
    return DocumentCropper(
        text_detector,
        detection_max_side=1280,
        margin=0.03,
        min_text_boxes=3,
        max_area_ratio=0.95,
        split_enabled=True,
        split_gap=4.0,
        pdf_dpi=200,
        pdf_max_pages=10,
    )


@pytest.fixture
def processor(
    ai_client: FakeAIClient, storage: FakeDocumentStorage, cropper: DocumentCropper
) -> CashoutDocumentProcessor:
    # Real processor, DocumentAIClient, and cropper over the fake provider,
    # storage, and detector.
    return CashoutDocumentProcessor(
        DocumentAIClient(
            ai_client,
            storage,
            classification_max_tokens=512,
            extraction_max_tokens=2048,
        ),
        cropper=cropper,
        storage=storage,
    )


__all__ = [
    "ai_client",
    "cropper",
    "email_client",
    "oauth_client",
    "processor",
    "storage",
    "text_detector",
]
