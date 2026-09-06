# backend/app/integrations/ocr/lifespan.py

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from app.core.config import settings

from .client import TextDetector
from .ppocr import PPOCRTextDetector


@asynccontextmanager
async def ocr_lifespan() -> AsyncGenerator[TextDetector | None]:
    """Load the text-detection model once at startup; nothing to tear down.

    Disabled cropping yields None, so no model is read into memory at all. A
    missing or corrupt model file fails boot here rather than on the first
    upload, like a misconfigured storage provider would.
    """
    if not settings.ocr.ENABLED:
        yield None
        return
    yield PPOCRTextDetector()
