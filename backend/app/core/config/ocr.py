# backend/app/core/config/ocr.py

from __future__ import annotations

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from .base import SettingsGroup


class OCRSettings(SettingsGroup):
    """Cropping uploads down to the documents printed in them.

    A local text-detection model finds the text in an uploaded image (or in
    each rendered page of a PDF); each printed area is cropped out (plus a
    margin), stored beside the original, and read by the AI in place of the
    whole upload — one extraction per document found. ENABLED=false skips
    both the model load at startup and the crop, so uploads extract from the
    original whole, as they did before cropping existed.
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
    # Whether an upload holding several documents (two receipts on the
    # table, a two-page PDF) is split into one crop — and one extraction —
    # per document. Off, every image is one document.
    SPLIT_ENABLED: bool = True
    # An empty band at least this many text-line heights wide, on background
    # rather than paper, separates two documents. Blank lines inside a
    # document are one or two line heights; leave room above that.
    SPLIT_GAP: float = Field(default=4.0, ge=1)
    # Resolution a PDF page is rendered at before detection and cropping.
    PDF_RENDER_DPI: int = Field(default=200, ge=72, le=400)
    # Pages of a PDF rendered at most; later pages are ignored.
    PDF_MAX_PAGES: int = Field(default=10, ge=1)


__all__ = ["OCRSettings"]
