from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from .base import SettingsGroup


class OCRSettings(SettingsGroup):
    """Settings for text-based cropping and PDF rendering.

    Disabling cropping skips the detector load and makes new extractions
    without an existing crop read the original upload. Existing analysis
    crops remain usable by retries.
    """

    model_config = SettingsConfigDict(env_prefix="OCR_")

    ENABLED: bool = True
    # Maximum image side before detection; crops retain source resolution.
    DETECTION_MAX_SIDE: int = Field(default=1280, ge=320)
    # Margin around detected text, as a fraction of the crop's larger side.
    CROP_MARGIN: float = Field(default=0.03, ge=0, le=0.5)
    # Minimum boxes per image/page to attempt a crop. After splitting,
    # groups below this size are dropped unless all groups would be dropped.
    MIN_TEXT_BOXES: int = Field(default=3, ge=1)
    # Skip a lone image crop above this area ratio. Does not apply to PDF
    # pages or to multiple crops from one image.
    MAX_CROP_AREA_RATIO: float = Field(default=0.95, gt=0, le=1)
    # Level tilted print — rotate the image by the dominant text orientation —
    # before splitting and cropping, so documents lying at an angle in a photo
    # still come apart and their crops come out upright.
    DESKEW_ENABLED: bool = True
    # Split text into candidate documents within each image or rendered page.
    # Disabling this does not combine the pages of a PDF.
    SPLIT_ENABLED: bool = True
    # Minimum empty-band width in median text-line heights for a split.
    # The band must also pass the luminance contrast heuristic.
    SPLIT_GAP: float = Field(default=4.0, ge=1)
    # Resolution a PDF page is rendered at before detection and cropping.
    PDF_RENDER_DPI: int = Field(default=200, ge=72, le=400)
    # Pages of a PDF rendered at most; later pages are ignored.
    PDF_MAX_PAGES: int = Field(default=10, ge=1)


__all__ = ["OCRSettings"]
