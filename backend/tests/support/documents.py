# backend/tests/support/documents.py

"""Sample document payloads for upload tests.

The extraction path never parses uploaded bytes (it stores them, checksums
them, and hands them to the — faked — AI), so tiny placeholder bytes serve
most tests. The PNG is a genuinely valid 1x1 image in case something ever
sniffs it. The photo is a real, decodable image for the tests that exercise
cropping: the cropper decodes it, shows it to the (faked) text detector, and
cuts the crop out of it.
"""

from __future__ import annotations

import base64
import io

from PIL import Image, ImageDraw

from app.integrations.ocr import TextBox

SAMPLE_PDF_BYTES = b"%PDF-1.4 fake bytes"
SAMPLE_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _photo() -> bytes:
    """A 640×480 "photo": a light receipt on a dark table, with a few dark
    lines where its print would be. Small enough that the cropper detects on
    it at full size, so box coordinates below are photo coordinates."""
    image = Image.new("RGB", (640, 480), (60, 50, 40))
    draw = ImageDraw.Draw(image)
    draw.rectangle((150, 100, 490, 370), fill=(245, 245, 240))
    for top in (120, 170, 220, 270, 320):
        draw.rectangle((160, top, 470, top + 30), fill=(20, 20, 20))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


SAMPLE_PHOTO_BYTES = _photo()
SAMPLE_PHOTO_SIZE = (640, 480)
# What a detector would find on the photo above: one box per printed line.
SAMPLE_PHOTO_TEXT_BOXES = [
    TextBox(left=160, top=top, right=right, bottom=top + 30)
    for top, right in ((120, 480), (170, 440), (220, 470), (270, 400), (320, 480))
]


# (paper's left edge, printed line width): the right receipt's lines are
# shorter, so the two crops differ.
_TWO_RECEIPTS = ((40, 230), (460, 200))


def _two_receipts_photo() -> bytes:
    """An 800×480 "photo" of two receipts side by side on a dark table, each
    with three printed lines. The table shows between them, which is what
    lets the cropper tell them apart."""
    image = Image.new("RGB", (800, 480), (60, 50, 40))
    draw = ImageDraw.Draw(image)
    for left, line_width in _TWO_RECEIPTS:
        draw.rectangle((left, 80, left + 300, 400), fill=(245, 245, 240))
        for top in (120, 200, 280):
            draw.rectangle(
                (left + 30, top, left + 30 + line_width, top + 24), fill=(20, 20, 20)
            )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


SAMPLE_TWO_RECEIPTS_BYTES = _two_receipts_photo()
# One box per printed line, left receipt first.
SAMPLE_TWO_RECEIPTS_TEXT_BOXES = [
    TextBox(left=left + 30, top=top, right=left + 30 + line_width, bottom=top + 24)
    for left, line_width in _TWO_RECEIPTS
    for top in (120, 200, 280)
]


def _receipt_pdf() -> bytes:
    """A two-page PDF whose pages are the single-receipt photo, saved at 200
    dpi so the cropper's 200-dpi render reproduces the photo's 640×480 pixels
    and SAMPLE_PHOTO_TEXT_BOXES apply to each page."""
    page = Image.open(io.BytesIO(SAMPLE_PHOTO_BYTES)).convert("RGB")
    buffer = io.BytesIO()
    page.save(buffer, format="PDF", save_all=True, append_images=[page], resolution=200)
    return buffer.getvalue()


SAMPLE_RECEIPT_PDF_BYTES = _receipt_pdf()

# (filename, bytes, mime) tuples in the shape httpx's `files=` expects.
SAMPLE_PDF_UPLOAD = ("receipt.pdf", SAMPLE_PDF_BYTES, "application/pdf")
SAMPLE_PNG_UPLOAD = ("receipt.png", SAMPLE_PNG_BYTES, "image/png")
SAMPLE_PHOTO_UPLOAD = ("receipt-photo.png", SAMPLE_PHOTO_BYTES, "image/png")
SAMPLE_TWO_RECEIPTS_UPLOAD = (
    "two-receipts.png",
    SAMPLE_TWO_RECEIPTS_BYTES,
    "image/png",
)
SAMPLE_RECEIPT_PDF_UPLOAD = ("reports.pdf", SAMPLE_RECEIPT_PDF_BYTES, "application/pdf")


__all__ = [
    "SAMPLE_PDF_BYTES",
    "SAMPLE_PDF_UPLOAD",
    "SAMPLE_PHOTO_BYTES",
    "SAMPLE_PHOTO_SIZE",
    "SAMPLE_PHOTO_TEXT_BOXES",
    "SAMPLE_PHOTO_UPLOAD",
    "SAMPLE_PNG_BYTES",
    "SAMPLE_PNG_UPLOAD",
    "SAMPLE_RECEIPT_PDF_BYTES",
    "SAMPLE_RECEIPT_PDF_UPLOAD",
    "SAMPLE_TWO_RECEIPTS_BYTES",
    "SAMPLE_TWO_RECEIPTS_TEXT_BOXES",
    "SAMPLE_TWO_RECEIPTS_UPLOAD",
]
