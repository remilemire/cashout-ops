# backend/tests/unit/test_cropping.py

"""`DocumentCropper` over the fake text detector.

The detector is faked: these tests are about what the cropper does with the
boxes it gets — the geometry, the formats, the rotation, and every reason it
declines to crop — not about finding text.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.core.config import settings
from app.document_cropping import CropBounds, DocumentCropper, build_document_cropper
from app.integrations.ocr import TextBox, TextDetectionError
from app.lib.documents import DocumentContent, DocumentContentType
from tests.support.fakes import FakeTextDetector

_FORMATS = {
    DocumentContentType.JPEG: "JPEG",
    DocumentContentType.PNG: "PNG",
    DocumentContentType.WEBP: "WEBP",
}

# Three lines of "print" on a 640×480 image: their union is (100, 100)–(320, 260).
_LINES = [
    TextBox(left=100, top=100, right=300, bottom=140),
    TextBox(left=100, top=160, right=320, bottom=200),
    TextBox(left=100, top=220, right=280, bottom=260),
]


def _image_bytes(
    content_type: DocumentContentType = DocumentContentType.PNG,
    *,
    size: tuple[int, int] = (640, 480),
    exif_orientation: int | None = None,
) -> bytes:
    image = Image.new("RGB", size, (200, 200, 200))
    buffer = io.BytesIO()
    if exif_orientation is None:
        image.save(buffer, format=_FORMATS[content_type])
    else:
        exif = Image.Exif()
        exif[0x0112] = exif_orientation
        image.save(buffer, format=_FORMATS[content_type], exif=exif.tobytes())
    return buffer.getvalue()


def _cropper(
    detector: FakeTextDetector | None,
    *,
    detection_max_side: int = 1280,
    margin: float = 0.03,
    min_text_boxes: int = 3,
    max_area_ratio: float = 0.95,
) -> DocumentCropper:
    return DocumentCropper(
        detector,
        detection_max_side=detection_max_side,
        margin=margin,
        min_text_boxes=min_text_boxes,
        max_area_ratio=max_area_ratio,
    )


def _decoded(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


async def test_crops_to_the_union_of_the_boxes_plus_a_margin() -> None:
    cropper = _cropper(FakeTextDetector(_LINES))

    cropped = await cropper.crop(
        DocumentContent(data=_image_bytes(), content_type=DocumentContentType.PNG)
    )

    assert cropped is not None
    # The union is 220 wide and 160 tall; 3% of the larger side is 7 pixels
    # of margin on every side.
    assert cropped.bounds == CropBounds(left=93, top=93, right=327, bottom=267)
    assert (cropped.width, cropped.height) == (234, 174)
    assert cropped.content_type is DocumentContentType.PNG
    assert _decoded(cropped.data).size == (234, 174)


async def test_the_margin_is_clamped_to_the_image() -> None:
    at_the_edge = [
        TextBox(left=0, top=0, right=300, bottom=40),
        TextBox(left=0, top=60, right=300, bottom=100),
        TextBox(left=0, top=120, right=300, bottom=160),
    ]
    cropper = _cropper(FakeTextDetector(at_the_edge))

    cropped = await cropper.crop(
        DocumentContent(data=_image_bytes(), content_type=DocumentContentType.PNG)
    )

    assert cropped is not None
    assert cropped.bounds.left == 0
    assert cropped.bounds.top == 0
    assert cropped.bounds.right == 309


@pytest.mark.parametrize(
    "content_type",
    [DocumentContentType.JPEG, DocumentContentType.PNG, DocumentContentType.WEBP],
)
async def test_the_crop_keeps_the_sources_format(
    content_type: DocumentContentType,
) -> None:
    cropper = _cropper(FakeTextDetector(_LINES))

    cropped = await cropper.crop(
        DocumentContent(data=_image_bytes(content_type), content_type=content_type)
    )

    assert cropped is not None
    assert cropped.content_type is content_type
    assert _decoded(cropped.data).format == _FORMATS[content_type]


async def test_the_exif_rotation_is_applied_before_detecting() -> None:
    # A landscape 640×480 file whose EXIF says "rotate 90° clockwise to view"
    # is a portrait 480×640 photo. The detector must see it upright, and the
    # boxes it reports are in that upright frame.
    portrait_lines = [
        TextBox(left=80, top=100, right=400, bottom=140),
        TextBox(left=80, top=160, right=400, bottom=200),
        TextBox(left=80, top=220, right=400, bottom=260),
    ]
    detector = FakeTextDetector(portrait_lines)
    cropper = _cropper(detector)

    cropped = await cropper.crop(
        DocumentContent(
            data=_image_bytes(DocumentContentType.JPEG, exif_orientation=6),
            content_type=DocumentContentType.JPEG,
        )
    )

    assert detector.calls == [(640, 480)]
    assert cropped is not None
    assert cropped.bounds == CropBounds(left=70, top=90, right=410, bottom=270)
    crop = _decoded(cropped.data)
    assert crop.size == (340, 180)
    # The rotation was baked into the pixels: no orientation tag rides along
    # to rotate the crop a second time.
    assert 0x0112 not in crop.getexif()


async def test_detects_on_a_downscaled_copy_and_scales_the_boxes_back() -> None:
    # 2560×1920 goes to the detector at 1280×960 (half size); its boxes come
    # back in the full-size frame, and the crop is cut from the full-size
    # image.
    detector = FakeTextDetector(_LINES)
    cropper = _cropper(detector)

    cropped = await cropper.crop(
        DocumentContent(
            data=_image_bytes(size=(2560, 1920)), content_type=DocumentContentType.PNG
        )
    )

    assert detector.calls == [(960, 1280)]
    assert cropped is not None
    # Twice the union (200, 200)–(640, 520), then 3% of 440 = 13 of margin.
    assert cropped.bounds == CropBounds(left=187, top=187, right=653, bottom=533)
    assert _decoded(cropped.data).size == (466, 346)


async def test_a_pdf_is_never_cropped() -> None:
    detector = FakeTextDetector(_LINES)
    cropper = _cropper(detector)

    cropped = await cropper.crop(
        DocumentContent(data=b"%PDF-1.4", content_type=DocumentContentType.PDF)
    )

    assert cropped is None
    assert detector.calls == []


async def test_without_a_detector_nothing_is_cropped() -> None:
    cropper = _cropper(None)

    cropped = await cropper.crop(
        DocumentContent(data=_image_bytes(), content_type=DocumentContentType.PNG)
    )

    assert cropped is None


async def test_too_few_boxes_means_no_document_was_found() -> None:
    cropper = _cropper(FakeTextDetector(_LINES[:2]), min_text_boxes=3)

    cropped = await cropper.crop(
        DocumentContent(data=_image_bytes(), content_type=DocumentContentType.PNG)
    )

    assert cropped is None


async def test_a_crop_of_nearly_the_whole_image_is_skipped() -> None:
    # Print that fills the frame leaves nothing worth a second stored copy.
    filling = [
        TextBox(left=5, top=5, right=635, bottom=100),
        TextBox(left=5, top=200, right=635, bottom=300),
        TextBox(left=5, top=380, right=635, bottom=475),
    ]
    cropper = _cropper(FakeTextDetector(filling), max_area_ratio=0.95)

    cropped = await cropper.crop(
        DocumentContent(data=_image_bytes(), content_type=DocumentContentType.PNG)
    )

    assert cropped is None


async def test_a_failed_detection_leaves_the_document_uncropped() -> None:
    cropper = _cropper(FakeTextDetector(error=TextDetectionError("model down")))

    cropped = await cropper.crop(
        DocumentContent(data=_image_bytes(), content_type=DocumentContentType.PNG)
    )

    assert cropped is None


async def test_undecodable_bytes_leave_the_document_uncropped() -> None:
    # A file whose declared type is not what its bytes are: the upload path
    # trusts the content type only as far as storing it, and the AI may still
    # cope — the cropper must not turn it into a failed upload.
    detector = FakeTextDetector(_LINES)
    cropper = _cropper(detector)

    cropped = await cropper.crop(
        DocumentContent(data=b"not an image", content_type=DocumentContentType.PNG)
    )

    assert cropped is None
    assert detector.calls == []


async def test_the_built_cropper_reads_the_ocr_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One box is normally too few; the settings say otherwise here.
    monkeypatch.setattr(settings.ocr, "MIN_TEXT_BOXES", 1)
    cropper = build_document_cropper(FakeTextDetector(_LINES[:1]))

    cropped = await cropper.crop(
        DocumentContent(data=_image_bytes(), content_type=DocumentContentType.PNG)
    )

    assert cropped is not None
