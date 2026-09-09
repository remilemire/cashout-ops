# backend/tests/unit/test_cropping.py

"""`DocumentCropper` over the fake text detector.

The detector is faked: these tests are about what the cropper does with the
boxes it gets — the geometry, the formats, the rotation, telling documents
apart, the PDF pages, and every reason it declines to crop — not about
finding text.
"""

from __future__ import annotations

import io
from collections.abc import Sequence

import pytest
from PIL import Image, ImageDraw

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

_TABLE = (60, 50, 40)
_PAPER = (245, 245, 240)


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


def _table_photo(
    papers: Sequence[tuple[int, int, int, int]],
    *,
    size: tuple[int, int] = (800, 480),
    image_format: str = "PNG",
) -> Image.Image:
    """Light paper rectangles on a dark table."""
    image = Image.new("RGB", size, _TABLE)
    draw = ImageDraw.Draw(image)
    for paper in papers:
        draw.rectangle(paper, fill=_PAPER)
    return image


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _lines(
    left: int, right: int, tops: Sequence[int], height: int = 24
) -> list[TextBox]:
    return [
        TextBox(left=left, top=top, right=right, bottom=top + height) for top in tops
    ]


def _cropper(
    detector: FakeTextDetector | None,
    *,
    detection_max_side: int = 1280,
    margin: float = 0.03,
    min_text_boxes: int = 3,
    max_area_ratio: float = 0.95,
    split_enabled: bool = True,
    split_gap: float = 4.0,
    pdf_dpi: int = 200,
    pdf_max_pages: int = 10,
) -> DocumentCropper:
    return DocumentCropper(
        detector,
        detection_max_side=detection_max_side,
        margin=margin,
        min_text_boxes=min_text_boxes,
        max_area_ratio=max_area_ratio,
        split_enabled=split_enabled,
        split_gap=split_gap,
        pdf_dpi=pdf_dpi,
        pdf_max_pages=pdf_max_pages,
    )


def _content(
    data: bytes, content_type: DocumentContentType = DocumentContentType.PNG
) -> DocumentContent:
    return DocumentContent(data=data, content_type=content_type)


def _decoded(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data))


# ================================
# --------- One document ---------
# ================================


async def test_crops_to_the_union_of_the_boxes_plus_a_margin() -> None:
    cropper = _cropper(FakeTextDetector(_LINES))

    (cropped,) = await cropper.crop(_content(_image_bytes()))

    # The union is 220 wide and 160 tall; 3% of the larger side is 7 pixels
    # of margin on every side.
    assert cropped.bounds == CropBounds(left=93, top=93, right=327, bottom=267)
    assert (cropped.width, cropped.height) == (234, 174)
    assert cropped.content_type is DocumentContentType.PNG
    assert cropped.page is None
    assert _decoded(cropped.data).size == (234, 174)


async def test_the_margin_is_clamped_to_the_image() -> None:
    at_the_edge = [
        TextBox(left=0, top=0, right=300, bottom=40),
        TextBox(left=0, top=60, right=300, bottom=100),
        TextBox(left=0, top=120, right=300, bottom=160),
    ]
    cropper = _cropper(FakeTextDetector(at_the_edge))

    (cropped,) = await cropper.crop(_content(_image_bytes()))

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

    (cropped,) = await cropper.crop(_content(_image_bytes(content_type), content_type))

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

    (cropped,) = await cropper.crop(
        _content(
            _image_bytes(DocumentContentType.JPEG, exif_orientation=6),
            DocumentContentType.JPEG,
        )
    )

    assert detector.calls == [(640, 480)]
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

    (cropped,) = await cropper.crop(_content(_image_bytes(size=(2560, 1920))))

    assert detector.calls == [(960, 1280)]
    # Twice the union (200, 200)–(640, 520), then 3% of 440 = 13 of margin.
    assert cropped.bounds == CropBounds(left=187, top=187, right=653, bottom=533)
    assert _decoded(cropped.data).size == (466, 346)


# ================================
# ------ Several documents -------
# ================================

# Two receipts side by side on a table, three printed lines each. The print
# is 24 px tall, so a qualifying gap is 96 px; the receipts' print sits 190
# px apart, across the table.
_SIDE_BY_SIDE = _table_photo([(40, 80, 340, 400), (460, 80, 760, 400)])
_SIDE_BY_SIDE_LINES = _lines(70, 300, (120, 200, 280)) + _lines(
    490, 720, (120, 200, 280)
)


async def test_splits_two_receipts_side_by_side_on_a_table() -> None:
    cropper = _cropper(FakeTextDetector(_SIDE_BY_SIDE_LINES))

    crops = await cropper.crop(_content(_png(_SIDE_BY_SIDE)))

    # Left receipt first; each crop is its own lines plus the 3% margin (7 px
    # on a 230-px-wide block).
    assert [crop.bounds for crop in crops] == [
        CropBounds(left=63, top=113, right=307, bottom=311),
        CropBounds(left=483, top=113, right=727, bottom=311),
    ]
    assert all(crop.page is None for crop in crops)


async def test_splits_two_receipts_stacked_on_a_table() -> None:
    stacked = _table_photo([(60, 40, 420, 250), (60, 520, 420, 760)], size=(480, 800))
    lines = _lines(90, 390, (80, 140, 200)) + _lines(90, 390, (560, 620, 680))
    cropper = _cropper(FakeTextDetector(lines))

    crops = await cropper.crop(_content(_png(stacked)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=81, top=71, right=399, bottom=233),
        CropBounds(left=81, top=551, right=399, bottom=713),
    ]


async def test_a_wide_gap_on_paper_does_not_split() -> None:
    # Labels on the left, values far to the right, on one sheet: the gap
    # between them is paper, not table, so it is one document.
    one_wide_sheet = _table_photo([(40, 80, 760, 400)])
    lines = _lines(70, 200, (120, 200, 280)) + _lines(560, 730, (120, 200, 280))
    cropper = _cropper(FakeTextDetector(lines))

    crops = await cropper.crop(_content(_png(one_wide_sheet)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=50, top=100, right=750, bottom=324)
    ]


async def test_blank_lines_on_paper_do_not_split() -> None:
    one_tall_sheet = _table_photo([(60, 40, 420, 760)], size=(480, 800))
    lines = _lines(90, 390, (80, 120, 160)) + _lines(90, 390, (500, 540, 580))
    cropper = _cropper(FakeTextDetector(lines))

    crops = await cropper.crop(_content(_png(one_tall_sheet)))

    # One crop spanning both blocks: the union (80–604) plus 3% of 524.
    assert [crop.bounds for crop in crops] == [
        CropBounds(left=74, top=64, right=406, bottom=620)
    ]


async def test_splitting_can_be_switched_off() -> None:
    cropper = _cropper(FakeTextDetector(_SIDE_BY_SIDE_LINES), split_enabled=False)

    crops = await cropper.crop(_content(_png(_SIDE_BY_SIDE)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=50, top=100, right=740, bottom=324)
    ]


async def test_stray_print_on_the_table_is_dropped() -> None:
    # A single label off to the right (a napkin, a menu) is not a document:
    # fewer boxes than a document needs, it is left out of the crops.
    lines = _lines(70, 300, (120, 200, 280)) + _lines(490, 720, (200,))
    cropper = _cropper(FakeTextDetector(lines))

    crops = await cropper.crop(_content(_png(_SIDE_BY_SIDE)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=63, top=113, right=307, bottom=311)
    ]


# ================================
# ------------- PDFs -------------
# ================================


def _pdf(pages: Sequence[Image.Image], *, resolution: int = 200) -> bytes:
    # Saved at the cropper's render resolution, so a page renders back at
    # its own pixel size and the boxes below apply as-is.
    first, *rest = [page.convert("RGB") for page in pages]
    buffer = io.BytesIO()
    first.save(
        buffer, format="PDF", save_all=True, append_images=rest, resolution=resolution
    )
    return buffer.getvalue()


_RECEIPT_PAGE = _table_photo([(150, 100, 490, 370)], size=(640, 480))


async def test_a_pdf_is_cropped_page_by_page() -> None:
    detector = FakeTextDetector(_LINES)
    cropper = _cropper(detector)

    crops = await cropper.crop(
        _content(_pdf([_RECEIPT_PAGE, _RECEIPT_PAGE]), DocumentContentType.PDF)
    )

    # Each page was rendered at its own size and detected on.
    assert len(detector.calls) == 2
    assert all(abs(h - 480) <= 1 and abs(w - 640) <= 1 for h, w in detector.calls)
    assert [crop.page for crop in crops] == [1, 2]
    # Rendered print is lossless: the crops are PNG whatever the source.
    assert all(crop.content_type is DocumentContentType.PNG for crop in crops)
    assert all(_decoded(crop.data).format == "PNG" for crop in crops)
    assert all(
        crop.bounds == CropBounds(left=93, top=93, right=327, bottom=267)
        for crop in crops
    )


async def test_a_pdf_page_that_is_all_print_is_still_cropped() -> None:
    # An image crop that keeps the whole image is skipped (nothing saved);
    # a page's crop stands in for the page, so it is kept even then — a later
    # page would otherwise be lost to "read the upload whole".
    filling = [
        TextBox(left=5, top=5, right=635, bottom=100),
        TextBox(left=5, top=200, right=635, bottom=300),
        TextBox(left=5, top=380, right=635, bottom=475),
    ]
    cropper = _cropper(FakeTextDetector(filling), max_area_ratio=0.95)

    crops = await cropper.crop(_content(_pdf([_RECEIPT_PAGE]), DocumentContentType.PDF))

    assert len(crops) == 1


async def test_pdf_pages_past_the_limit_are_ignored() -> None:
    detector = FakeTextDetector(_LINES)
    cropper = _cropper(detector, pdf_max_pages=1)

    crops = await cropper.crop(
        _content(_pdf([_RECEIPT_PAGE, _RECEIPT_PAGE]), DocumentContentType.PDF)
    )

    assert [crop.page for crop in crops] == [1]
    assert len(detector.calls) == 1


async def test_a_pdf_that_will_not_render_yields_nothing() -> None:
    detector = FakeTextDetector(_LINES)
    cropper = _cropper(detector)

    crops = await cropper.crop(
        _content(b"%PDF-1.4 fake bytes", DocumentContentType.PDF)
    )

    assert crops == []
    assert detector.calls == []


# ================================
# ------ Nothing to crop to ------
# ================================


async def test_without_a_detector_nothing_is_cropped() -> None:
    cropper = _cropper(None)

    assert await cropper.crop(_content(_image_bytes())) == []


async def test_too_few_boxes_means_no_document_was_found() -> None:
    cropper = _cropper(FakeTextDetector(_LINES[:2]), min_text_boxes=3)

    assert await cropper.crop(_content(_image_bytes())) == []


async def test_a_crop_of_nearly_the_whole_image_is_skipped() -> None:
    # Print that fills the frame leaves nothing worth a second stored copy.
    filling = [
        TextBox(left=5, top=5, right=635, bottom=100),
        TextBox(left=5, top=200, right=635, bottom=300),
        TextBox(left=5, top=380, right=635, bottom=475),
    ]
    cropper = _cropper(FakeTextDetector(filling), max_area_ratio=0.95)

    assert await cropper.crop(_content(_image_bytes())) == []


async def test_a_failed_detection_leaves_the_document_uncropped() -> None:
    cropper = _cropper(FakeTextDetector(error=TextDetectionError("model down")))

    assert await cropper.crop(_content(_image_bytes())) == []


async def test_undecodable_bytes_leave_the_document_uncropped() -> None:
    # A file whose declared type is not what its bytes are: the upload path
    # trusts the content type only as far as storing it, and the AI may still
    # cope — the cropper must not turn it into a failed upload.
    detector = FakeTextDetector(_LINES)
    cropper = _cropper(detector)

    assert await cropper.crop(_content(b"not an image")) == []
    assert detector.calls == []


async def test_the_built_cropper_reads_the_ocr_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # One box is normally too few; the settings say otherwise here.
    monkeypatch.setattr(settings.ocr, "MIN_TEXT_BOXES", 1)
    cropper = build_document_cropper(FakeTextDetector(_LINES[:1]))

    assert len(await cropper.crop(_content(_image_bytes()))) == 1
