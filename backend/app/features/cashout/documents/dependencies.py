# backend/app/features/cashout/documents/dependencies.py

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.document_ai import DocumentCropper, build_document_cropper
from app.integrations.ocr import TextDetector
from app.integrations.ocr.dependencies import get_text_detector


def get_document_cropper(
    detector: Annotated[TextDetector | None, Depends(get_text_detector)],
) -> DocumentCropper:
    return build_document_cropper(detector)


__all__ = ["get_document_cropper"]
