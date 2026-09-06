# backend/tests/unit/test_ocr_lifespan.py

"""The OCR lifespan loads the detector exactly when cropping is enabled."""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.integrations.ocr import PPOCRTextDetector
from app.integrations.ocr.lifespan import ocr_lifespan


async def test_enabled_cropping_loads_the_detector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.ocr, "ENABLED", True)

    async with ocr_lifespan() as detector:
        assert isinstance(detector, PPOCRTextDetector)


async def test_disabled_cropping_loads_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The kill switch must keep the model out of memory entirely, not merely
    # skip the crop: None is what the cropper reads as "do not crop".
    monkeypatch.setattr(settings.ocr, "ENABLED", False)

    async with ocr_lifespan() as detector:
        assert detector is None
