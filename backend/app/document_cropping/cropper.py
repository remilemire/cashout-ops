"""Detect candidate document regions and crop them for analysis.

Text boxes are grouped by empty bands and a luminance contrast heuristic.
This can separate receipts on a contrasting table, but shadows, shaded
paper, and missed text can cause incorrect splits or omissions. Matching
paper and background can leave several documents in one crop.

PDFs are rendered up to the configured page limit. Pages with insufficient
detected text contribute no crops. If any crops are returned, only those
regions are analyzed; an omitted page does not receive a whole-page fallback.
If no crops are returned, the caller reads the original upload. Recognized
decode, render, and detection failures also return no crops.
"""

from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.integrations.ocr import TextBox, TextDetectionError, TextDetector
from app.lib.documents import DocumentContent, DocumentContentType

from .deskew import MIN_LEVELING_ANGLE, Leveled, dominant_orientation
from .pdf import PdfRenderError, render_pdf_pages
from .types import CropBounds, DocumentCrop

logger = logging.getLogger(__name__)

# Pillow format and save options per image content type. A crop keeps its
# source's format, though JPEG and WebP encoding may introduce further loss.
# A PDF's crops are cut from rendered pages and stored as PNG.
_ENCODINGS: Mapping[DocumentContentType, tuple[str, dict[str, Any]]] = {
    DocumentContentType.JPEG: ("JPEG", {"quality": 90, "optimize": True}),
    DocumentContentType.PNG: ("PNG", {"optimize": True}),
    DocumentContentType.WEBP: ("WEBP", {"quality": 90}),
}

# How far (0–255 luminance) an empty band must differ from the paper beside
# it to count as background between two documents rather than a gap on one.
_BACKGROUND_CONTRAST = 30

type _Axis = Literal["x", "y"]
type _Luminance = NDArray[np.uint8]


@dataclass(frozen=True)
class _Region:
    """One document to cut: the rectangle to cut from the image it is cut
    from (the upload, or its leveled copy), and where that lands in the
    upload — the same rectangle unless the image was leveled."""

    cut: tuple[int, int, int, int]
    bounds: CropBounds


class DocumentCropper:
    """Crop candidate documents identified by text detection.

    A None detector disables cropping without decoding the upload.
    """

    def __init__(
        self,
        detector: TextDetector | None,
        *,
        detection_max_side: int,
        margin: float,
        min_text_boxes: int,
        max_area_ratio: float,
        deskew_enabled: bool,
        split_enabled: bool,
        split_gap: float,
        pdf_dpi: int,
        pdf_max_pages: int,
    ) -> None:
        self._detector = detector
        self._detection_max_side = detection_max_side
        self._margin = margin
        self._min_text_boxes = min_text_boxes
        self._max_area_ratio = max_area_ratio
        self._deskew_enabled = deskew_enabled
        self._split_enabled = split_enabled
        self._split_gap = split_gap
        self._pdf_dpi = pdf_dpi
        self._pdf_max_pages = pdf_max_pages

    async def crop(self, content: DocumentContent) -> list[DocumentCrop]:
        """Return detected regions in reading order, with page numbers for PDFs.

        Recognized decoding, PDF-rendering, and text-detection errors are logged
        and return an empty list. Pages without enough text boxes contribute no
        crops; other pages can still produce results. Unexpected processing or
        encoding errors propagate to the caller.
        """
        if self._detector is None:
            return []

        if content.content_type is DocumentContentType.PDF:
            try:
                pages = await asyncio.to_thread(
                    render_pdf_pages,
                    content.data,
                    dpi=self._pdf_dpi,
                    max_pages=self._pdf_max_pages,
                )
            except PdfRenderError as exc:
                logger.warning("PDF could not be rendered for cropping: %s", exc)
                return []
            # A page's crop stands in for the page: even print that fills the
            # page is cut out, or a later page would be lost to "read whole".
            sources = [(number, page, False) for number, page in enumerate(pages, 1)]
            output_type = DocumentContentType.PNG
        elif content.content_type in _ENCODINGS:
            try:
                image = await asyncio.to_thread(_decode, content.data)
            except (
                UnidentifiedImageError,
                Image.DecompressionBombError,
                OSError,
            ) as exc:
                logger.warning("Document could not be decoded for cropping: %s", exc)
                return []
            sources = [(None, image, True)]
            output_type = content.content_type
        else:
            return []

        crops: list[DocumentCrop] = []
        for page, image, whole_is_pointless in sources:
            try:
                source, regions = await self._find_documents(
                    image, whole_is_pointless=whole_is_pointless
                )
            except TextDetectionError as exc:
                logger.warning(
                    "Text detection failed; reading the upload whole: %s", exc
                )
                return []
            for region in regions:
                data = await asyncio.to_thread(
                    _encode, source.crop(region.cut), output_type
                )
                crops.append(
                    DocumentCrop(
                        content=DocumentContent(data=data, content_type=output_type),
                        bounds=replace(region.bounds, page=page),
                    )
                )
        return crops

    async def _find_documents(
        self, image: Image.Image, *, whole_is_pointless: bool
    ) -> tuple[Image.Image, list[_Region]]:
        """The documents printed in one image, in reading order, and the image
        to cut them from: the image itself, or a leveled copy of it when its
        print is tilted.

        `whole_is_pointless` skips a lone region that keeps nearly the whole
        image: a second copy of a photo saves nothing. A leveled copy is
        never pointless — it is a different image, upright and tighter.
        """
        assert self._detector is not None
        detection_image, scale = await asyncio.to_thread(
            _downscale, image, self._detection_max_side
        )
        boxes = await self._detector.detect(np.asarray(detection_image, dtype=np.uint8))
        if len(boxes) < self._min_text_boxes:
            return image, []

        # Tilted print is leveled before splitting: the bands the splitter
        # cuts along run with the axes, so documents lying at an angle would
        # never come apart. The boxes are mapped into the level frame rather
        # than detected again, so the detection scale is unchanged.
        # The height of a line of print, measured before leveling: a region's
        # thickness does not change with its tilt, where its envelope's height
        # does — and print left sideways by the leveling (tilted past 45°, so
        # the nearer level is a quarter turn off) has envelopes as tall as its
        # lines are long.
        line_height = _line_height(boxes)
        angle = dominant_orientation(boxes) if self._deskew_enabled else 0.0
        leveled: Leveled | None = None
        frame = detection_image
        if abs(angle) >= MIN_LEVELING_ANGLE:
            leveled = await asyncio.to_thread(Leveled.of, detection_image, angle)
            frame = leveled.image
            boxes = [leveled.level_box(box) for box in boxes]

        if self._split_enabled:
            luminance = np.asarray(frame.convert("L"), dtype=np.uint8)
            groups = _split(
                boxes,
                luminance,
                line_height=line_height,
                gap_ratio=self._split_gap,
                min_boxes=self._min_text_boxes,
            )
        else:
            groups = [list(boxes)]

        if leveled is None:
            width, height = image.size
            regions = [
                _with_margin(
                    _scale(_union(group), 1 / scale, 1 / scale),
                    margin=self._margin,
                    width=width,
                    height=height,
                )
                for group in groups
            ]
            if (
                whole_is_pointless
                and len(regions) == 1
                and regions[0].width * regions[0].height
                > self._max_area_ratio * width * height
            ):
                return image, []
            return image, [
                _Region(cut=_as_box(region), bounds=region) for region in regions
            ]

        # Cut from the upload leveled the same way. Its canvas is the detection
        # canvas scaled up, so a region scales between the two — by each side's
        # own ratio, which absorbs the rounding in the canvas sizes — and its
        # recorded bounds are where that region lands back in the upload.
        source = await asyncio.to_thread(Leveled.of, image, angle)
        regions_in_source: list[_Region] = []
        for group in groups:
            cut = _with_margin(
                _scale(
                    _union(group),
                    source.image.width / frame.width,
                    source.image.height / frame.height,
                ),
                margin=self._margin,
                width=source.image.width,
                height=source.image.height,
            )
            regions_in_source.append(
                _Region(
                    cut=_as_box(cut),
                    bounds=CropBounds(*source.envelope_in_source(*_as_box(cut))),
                )
            )
        return source.image, regions_in_source


def build_document_cropper(detector: TextDetector | None) -> DocumentCropper:
    """Build a cropper using the configured geometry and PDF limits.

    The caller owns the detector's lifecycle; this wrapper opens no resources.
    """
    return DocumentCropper(
        detector,
        detection_max_side=settings.ocr.DETECTION_MAX_SIDE,
        margin=settings.ocr.CROP_MARGIN,
        min_text_boxes=settings.ocr.MIN_TEXT_BOXES,
        max_area_ratio=settings.ocr.MAX_CROP_AREA_RATIO,
        deskew_enabled=settings.ocr.DESKEW_ENABLED,
        split_enabled=settings.ocr.SPLIT_ENABLED,
        split_gap=settings.ocr.SPLIT_GAP,
        pdf_dpi=settings.ocr.PDF_RENDER_DPI,
        pdf_max_pages=settings.ocr.PDF_MAX_PAGES,
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
    """Return an image fit under `max_side` and the scale factor applied."""
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


def _line_height(boxes: Sequence[TextBox]) -> int:
    """The median thickness of the boxes, at least a pixel."""
    thicknesses = sorted(box.thickness for box in boxes)
    return max(1, round(thicknesses[len(thicknesses) // 2]))


def _split(
    boxes: Sequence[TextBox],
    luminance: _Luminance,
    *,
    line_height: int,
    gap_ratio: float,
    min_boxes: int,
) -> list[list[TextBox]]:
    """Split text boxes into candidate documents in approximate reading order.

    Drop groups with fewer than `min_boxes`, unless that would drop them all;
    in that case retain all boxes as a single group.
    """
    gap = max(2, round(gap_ratio * line_height))
    groups = _cut(list(boxes), luminance, gap=gap, line_height=line_height)
    kept = [group for group in groups if len(group) >= min_boxes]
    if not kept:
        return [list(boxes)]
    # Approximate reading order using fixed bands two line heights tall,
    # then left to right within each band.
    row_height = 2 * line_height
    return sorted(
        kept,
        key=lambda group: (
            min(box.top for box in group) // row_height,
            min(box.left for box in group),
        ),
    )


def _cut(
    boxes: list[TextBox], luminance: _Luminance, *, gap: int, line_height: int
) -> list[list[TextBox]]:
    """Recursively cut the boxes through the widest qualifying empty band,
    trying horizontal bands (stacked documents) before vertical ones."""
    for axis in ("y", "x"):
        parts = _cut_along(boxes, luminance, axis, gap=gap, line_height=line_height)
        if parts is not None:
            first, second = parts
            return _cut(first, luminance, gap=gap, line_height=line_height) + _cut(
                second, luminance, gap=gap, line_height=line_height
            )
    return [boxes]


def _cut_along(
    boxes: list[TextBox],
    luminance: _Luminance,
    axis: _Axis,
    *,
    gap: int,
    line_height: int,
) -> tuple[list[TextBox], list[TextBox]] | None:
    """The two sides of the widest empty band along `axis` that is at least
    `gap` wide and passes the background heuristic, or None."""
    if len(boxes) < 2:
        return None
    ordered = sorted(boxes, key=lambda box: _span(box, axis)[0])
    other: _Axis = "x" if axis == "y" else "y"

    # Every empty band between one box's end and the next box's start, once
    # all earlier boxes have ended: (width, split index, band start, band end).
    candidates: list[tuple[int, int, int, int]] = []
    reach = _span(ordered[0], axis)[1]
    for index in range(1, len(ordered)):
        start, end = _span(ordered[index], axis)
        if start - reach >= gap:
            candidates.append((start - reach, index, reach, start))
        reach = max(reach, end)

    for _, index, band_start, band_end in sorted(candidates, reverse=True):
        if _is_background(
            luminance,
            axis,
            band_start,
            band_end,
            before=_extent(ordered[:index], other),
            after=_extent(ordered[index:], other),
            line_height=line_height,
        ):
            return ordered[:index], ordered[index:]
    return None


def _is_background(
    luminance: _Luminance,
    axis: _Axis,
    band_start: int,
    band_end: int,
    *,
    before: tuple[int, int],
    after: tuple[int, int],
    line_height: int,
) -> bool:
    """Whether at least a line's height of the band shows something that is
    neither side's paper — the table between two documents.

    `before` and `after` are the extents across the axis of the print on
    each side. Each side's paper is the median of a line's height of its own
    print (text is a minority of those pixels), over that side's own extent:
    a neighbour lying higher or further along the photo would otherwise put
    table into the sample, and the table between them would then read as
    paper. The two papers are kept apart so a dark report beside a white
    receipt keeps both. The band is then read position by position along the
    axis across everything either side prints on, each position summarized
    by its median, and it is background when a run of at least `line_height`
    positions differs from both papers by more than `_BACKGROUND_CONTRAST`.
    Judging a run rather than the band's overall median keeps a document's
    own blank margins, which lie inside the band, from outvoting a narrower
    strip of table. This is a contrast heuristic, not proof that the band
    lies between documents.
    """
    low, high = min(before[0], after[0]), max(before[1], after[1])
    before_strip = _band(
        luminance, axis, max(0, band_start - line_height), band_start, *before
    )
    strip = _band(luminance, axis, band_start, band_end, low, high)
    after_strip = _band(luminance, axis, band_end, band_end + line_height, *after)
    if before_strip.size == 0 or strip.size == 0 or after_strip.size == 0:
        return False
    paper_before = float(np.median(before_strip))
    paper_after = float(np.median(after_strip))
    # One value per position along the axis: per row of a horizontal band,
    # per column of a vertical one.
    profile = np.median(strip, axis=1 if axis == "y" else 0)
    unlike_paper = (np.abs(profile - paper_before) > _BACKGROUND_CONTRAST) & (
        np.abs(profile - paper_after) > _BACKGROUND_CONTRAST
    )
    return _longest_run(unlike_paper) >= line_height


def _longest_run(flags: NDArray[np.bool_]) -> int:
    """The length of the longest run of consecutive True values."""
    longest = current = 0
    for flag in flags.tolist():
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return longest


def _band(
    luminance: _Luminance, axis: _Axis, start: int, end: int, low: int, high: int
) -> _Luminance:
    if axis == "y":
        return luminance[start:end, low:high]
    return luminance[low:high, start:end]


def _span(box: TextBox, axis: _Axis) -> tuple[int, int]:
    return (box.top, box.bottom) if axis == "y" else (box.left, box.right)


def _extent(boxes: Sequence[TextBox], axis: _Axis) -> tuple[int, int]:
    spans = [_span(box, axis) for box in boxes]
    return min(start for start, _ in spans), max(end for _, end in spans)


def _union(boxes: Sequence[TextBox]) -> CropBounds:
    """One document's extent: the union of its boxes."""
    return CropBounds(
        left=min(box.left for box in boxes),
        top=min(box.top for box in boxes),
        right=max(box.right for box in boxes),
        bottom=max(box.bottom for box in boxes),
    )


def _scale(bounds: CropBounds, factor_x: float, factor_y: float) -> CropBounds:
    return CropBounds(
        left=round(bounds.left * factor_x),
        top=round(bounds.top * factor_y),
        right=round(bounds.right * factor_x),
        bottom=round(bounds.bottom * factor_y),
    )


def _as_box(bounds: CropBounds) -> tuple[int, int, int, int]:
    return bounds.left, bounds.top, bounds.right, bounds.bottom


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


__all__ = ["DocumentCropper", "build_document_cropper"]
