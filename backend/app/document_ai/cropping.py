# backend/app/document_ai/cropping.py

"""Cropping a document image to its printed area before analysis.

A phone photo of a report is mostly tabletop. Text detection says where the
print is; the crop keeps that region plus a margin, so the AI reads far fewer
pixels and the cashier sees the report rather than the table. Best-effort by
design: whatever stops the crop — a PDF, an image with no detectable text, a
failed detection, cropping switched off — leaves the document uncropped, and
the upload proceeds exactly as it did before cropping existed.

The single-document rule lives in `_text_region`: every detected box belongs
to the one document, so the crop is their union. Splitting a photo of several
reports into one crop each is the planned next step, and replaces that one
function with clustering.
"""

from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.integrations.ocr import TextBox, TextDetectionError, TextDetector
from app.lib.documents import DocumentContent, DocumentContentType

logger = logging.getLogger(__name__)

# Pillow format and save options per croppable content type. A crop keeps its
# source's format: a lossless screenshot stays lossless, a photo stays a JPEG.
# PDFs are absent: a PDF is a document already, not a photo of one.
_ENCODINGS: Mapping[DocumentContentType, tuple[str, dict[str, Any]]] = {
    DocumentContentType.JPEG: ("JPEG", {"quality": 90, "optimize": True}),
    DocumentContentType.PNG: ("PNG", {"optimize": True}),
    DocumentContentType.WEBP: ("WEBP", {"quality": 90}),
}


@dataclass(frozen=True)
class CropBounds:
    """The crop's rectangle in the upright source image (after its EXIF
    rotation is applied): left/top inclusive, right/bottom exclusive."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def as_json(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
        }


@dataclass(frozen=True)
class CroppedDocument:
    data: bytes
    content_type: DocumentContentType
    bounds: CropBounds
    width: int
    height: int


class DocumentCropper:
    """Crops an uploaded image to the region its text detector finds.

    `detector` is None when cropping is disabled: every crop then returns
    None without decoding anything.
    """

    def __init__(
        self,
        detector: TextDetector | None,
        *,
        detection_max_side: int,
        margin: float,
        min_text_boxes: int,
        max_area_ratio: float,
    ) -> None:
        self._detector = detector
        self._detection_max_side = detection_max_side
        self._margin = margin
        self._min_text_boxes = min_text_boxes
        self._max_area_ratio = max_area_ratio

    async def crop(self, content: DocumentContent) -> CroppedDocument | None:
        """The cropped document, or None when there is nothing to crop to.

        Never raises for a document-shaped reason: an undecodable image or a
        failed detection is logged and yields None, so the caller stores the
        upload uncropped rather than rejecting it.
        """
        if self._detector is None or content.content_type not in _ENCODINGS:
            return None

        try:
            image = await asyncio.to_thread(_decode, content.data)
        except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
            logger.warning("Document could not be decoded for cropping: %s", exc)
            return None

        detection_image, scale = await asyncio.to_thread(
            _downscale, image, self._detection_max_side
        )
        try:
            boxes = await self._detector.detect(
                np.asarray(detection_image, dtype=np.uint8)
            )
        except TextDetectionError as exc:
            logger.warning(
                "Text detection failed; storing the document uncropped: %s", exc
            )
            return None
        if len(boxes) < self._min_text_boxes:
            return None

        width, height = image.size
        bounds = _with_margin(
            _scale(_text_region(boxes), 1 / scale),
            margin=self._margin,
            width=width,
            height=height,
        )
        if bounds.width * bounds.height > self._max_area_ratio * width * height:
            # The print fills the frame already: a second copy saves nothing.
            return None

        data = await asyncio.to_thread(
            _encode,
            image.crop((bounds.left, bounds.top, bounds.right, bounds.bottom)),
            content.content_type,
        )
        return CroppedDocument(
            data=data,
            content_type=content.content_type,
            bounds=bounds,
            width=bounds.width,
            height=bounds.height,
        )


def build_document_cropper(detector: TextDetector | None) -> DocumentCropper:
    """Compose a cropper over the configured OCR settings.

    Like the extraction processor, the cropper opens no resource of its own —
    the detector owns the model — so each consumer builds one for itself.
    """
    return DocumentCropper(
        detector,
        detection_max_side=settings.ocr.DETECTION_MAX_SIDE,
        margin=settings.ocr.CROP_MARGIN,
        min_text_boxes=settings.ocr.MIN_TEXT_BOXES,
        max_area_ratio=settings.ocr.MAX_CROP_AREA_RATIO,
    )


def _decode(data: bytes) -> Image.Image:
    """The image as it is meant to be viewed: EXIF rotation applied, RGB.

    Phone cameras store the sensor's orientation in EXIF rather than rotating
    the pixels; applying it here means the detector, the crop, the AI, and
    the cashier's preview all see the document upright.
    """
    with Image.open(io.BytesIO(data)) as opened:
        opened.load()
        upright = ImageOps.exif_transpose(opened) or opened
        return upright.convert("RGB")


def _downscale(image: Image.Image, max_side: int) -> tuple[Image.Image, float]:
    """A copy fit under `max_side` for detection, and the factor applied."""
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image, 1.0
    scale = max_side / longest
    resized = image.resize(
        (max(1, round(width * scale)), max(1, round(height * scale))),
        Image.Resampling.BILINEAR,
    )
    return resized, scale


def _text_region(boxes: Sequence[TextBox]) -> CropBounds:
    """The one document's extent: the union of every detected box."""
    return CropBounds(
        left=min(box.left for box in boxes),
        top=min(box.top for box in boxes),
        right=max(box.right for box in boxes),
        bottom=max(box.bottom for box in boxes),
    )


def _scale(bounds: CropBounds, factor: float) -> CropBounds:
    return CropBounds(
        left=round(bounds.left * factor),
        top=round(bounds.top * factor),
        right=round(bounds.right * factor),
        bottom=round(bounds.bottom * factor),
    )


def _with_margin(
    bounds: CropBounds, *, margin: float, width: int, height: int
) -> CropBounds:
    """Grow the region by `margin` of its larger side, clamped to the image."""
    pad = round(margin * max(bounds.width, bounds.height))
    return CropBounds(
        left=max(0, bounds.left - pad),
        top=max(0, bounds.top - pad),
        right=min(width, bounds.right + pad),
        bottom=min(height, bounds.bottom + pad),
    )


def _encode(image: Image.Image, content_type: DocumentContentType) -> bytes:
    # Saved from the upright RGB pixels with no EXIF: the rotation has been
    # applied, so carrying the tag along would rotate the crop twice.
    image_format, options = _ENCODINGS[content_type]
    buffer = io.BytesIO()
    image.save(buffer, format=image_format, **options)
    return buffer.getvalue()


__all__ = [
    "CropBounds",
    "CroppedDocument",
    "DocumentCropper",
    "build_document_cropper",
]
