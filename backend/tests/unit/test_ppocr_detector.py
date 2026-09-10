"""The vendored PP-OCRv4 detector over synthetic images.

These load the real model to exercise preprocessing and box detection on
synthetic inputs. They do not establish accuracy on real receipt photos.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from app.integrations.ocr import PPOCRTextDetector, TextBox, TextDetectionError
from app.integrations.ocr.ppocr import MODEL_SHA256, model_path


def _receipt_image() -> tuple[np.ndarray, TextBox]:
    """A synthetic receipt: a few printed lines on white, plus the exact
    pixel bounds of the print (measured, not assumed)."""
    image = Image.new("RGB", (640, 480), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=26)
    lines = [
        "SERVER SUMMARY REPORT",
        "CREDIT        1,234.56",
        "DEBIT           789.00",
        "GRAND TOTAL   2,023.56",
        "END OF REPORT",
    ]
    bounds: list[tuple[int, int, int, int]] = []
    for index, line in enumerate(lines):
        origin = (124, 106 + index * 44)
        draw.text(origin, line, fill="black", font=font)
        left, top, right, bottom = draw.textbbox(origin, line, font=font)
        bounds.append((int(left), int(top), int(right), int(bottom)))
    printed = TextBox(
        left=min(b[0] for b in bounds),
        top=min(b[1] for b in bounds),
        right=max(b[2] for b in bounds),
        bottom=max(b[3] for b in bounds),
    )
    return np.asarray(image, dtype=np.uint8), printed


def _assert_close(actual: TextBox, expected: TextBox, *, tolerance: int) -> None:
    for side in ("left", "top", "right", "bottom"):
        got, want = getattr(actual, side), getattr(expected, side)
        assert abs(got - want) <= tolerance, f"{side}: {got} vs {want} (±{tolerance})"


def _union(boxes: list[TextBox]) -> TextBox:
    return TextBox(
        left=min(box.left for box in boxes),
        top=min(box.top for box in boxes),
        right=max(box.right for box in boxes),
        bottom=max(box.bottom for box in boxes),
    )


@pytest.fixture(scope="module")
def detector() -> PPOCRTextDetector:
    return PPOCRTextDetector()


def test_the_vendored_model_matches_its_recorded_digest() -> None:
    assert hashlib.sha256(model_path().read_bytes()).hexdigest() == MODEL_SHA256


def test_a_tampered_model_is_refused(tmp_path: Path) -> None:
    # The digest check is what turns a corrupted or swapped model into a boot
    # failure rather than a detector that quietly finds nothing.
    tampered = tmp_path / "det.onnx"
    tampered.write_bytes(model_path().read_bytes() + b"\0")

    with pytest.raises(RuntimeError, match="SHA-256"):
        PPOCRTextDetector(tampered)


async def test_finds_the_printed_lines_and_nothing_else(
    detector: PPOCRTextDetector,
) -> None:
    image, printed = _receipt_image()

    boxes = await detector.detect(image)

    # One box per line, give or take a merged pair; all of them on the print.
    assert 3 <= len(boxes) <= 8
    _assert_close(_union(boxes), printed, tolerance=24)


async def test_a_blank_image_yields_no_boxes(detector: PPOCRTextDetector) -> None:
    blank = np.full((480, 640, 3), 255, dtype=np.uint8)

    assert await detector.detect(blank) == []


async def test_boxes_are_reported_in_the_input_images_coordinates(
    detector: PPOCRTextDetector,
) -> None:
    # An input larger than the network ceiling is downscaled for inference;
    # the boxes must come back scaled to the image that was handed in.
    image, printed = _receipt_image()
    large = np.asarray(Image.fromarray(image).resize((2560, 1920)), dtype=np.uint8)
    scaled = TextBox(
        left=printed.left * 4,
        top=printed.top * 4,
        right=printed.right * 4,
        bottom=printed.bottom * 4,
    )

    boxes = await detector.detect(large)

    _assert_close(_union(boxes), scaled, tolerance=24 * 4)


async def test_rejects_an_image_that_is_not_rgb(detector: PPOCRTextDetector) -> None:
    grayscale = np.full((480, 640), 255, dtype=np.uint8)

    with pytest.raises(TextDetectionError):
        await detector.detect(grayscale)  # pyright: ignore[reportArgumentType]
