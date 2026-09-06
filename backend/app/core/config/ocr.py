# backend/app/core/config/ocr.py

from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from .base import SettingsGroup


class OCRSettings(SettingsGroup):
    """Cropping uploaded photos to their printed area.

    A local text-detection model finds the text in an uploaded image; the
    document is cropped to that region (plus a margin), stored beside the
    original, and read by the AI in place of the full photo. ENABLED=false
    skips both the model load at startup and the crop at upload, so uploads
    extract from the original as they did before cropping existed.
    """

    model_config = SettingsConfigDict(env_prefix="OCR_")

    ENABLED: bool = True
    # Long side the image is downscaled to before detection. Detection needs
    # far fewer pixels than the AI does; the crop itself keeps the original
    # resolution.
    DETECTION_MAX_SIDE: int = Field(default=1280, ge=320)
    # Margin kept around the detected text, as a fraction of the crop's
    # larger side, so a document's edges and any faint print stay in frame.
    CROP_MARGIN: float = Field(default=0.03, ge=0, le=0.5)
    # Fewer detected text boxes than this means no document was found (a
    # stray label, a blank photo): the upload stays uncropped.
    MIN_TEXT_BOXES: int = Field(default=3, ge=1)
    # A crop keeping more than this share of the image's pixels saves nothing
    # worth a second stored copy: the upload stays uncropped.
    MAX_CROP_AREA_RATIO: float = Field(default=0.95, gt=0, le=1)


__all__ = ["OCRSettings"]
