"""`DocumentCropper` over the fake text detector.

The detector is faked: these tests are about what the cropper does with the
boxes it gets — the geometry, the formats, the rotation, telling documents
apart, the PDF pages, and every reason it declines to crop — not about
finding text.
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence

import numpy as np
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
    paper: tuple[int, int, int] = _PAPER,
    table: tuple[int, int, int] = _TABLE,
) -> Image.Image:
    """Paper rectangles on a table: light on dark unless told otherwise."""
    image = Image.new("RGB", size, table)
    draw = ImageDraw.Draw(image)
    for rectangle in papers:
        draw.rectangle(rectangle, fill=paper)
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
    deskew_enabled: bool = True,
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
        deskew_enabled=deskew_enabled,
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
    assert cropped.content.content_type is DocumentContentType.PNG
    assert _decoded(cropped.content.data).size == (234, 174)


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

    assert cropped.content.content_type is content_type
    assert _decoded(cropped.content.data).format == _FORMATS[content_type]


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
    crop = _decoded(cropped.content.data)
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
    assert _decoded(cropped.content.data).size == (466, 346)


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
    assert all(crop.bounds.page is None for crop in crops)


async def test_splits_two_receipts_stacked_on_a_table() -> None:
    stacked = _table_photo([(60, 40, 420, 250), (60, 520, 420, 760)], size=(480, 800))
    lines = _lines(90, 390, (80, 140, 200)) + _lines(90, 390, (560, 620, 680))
    cropper = _cropper(FakeTextDetector(lines))

    crops = await cropper.crop(_content(_png(stacked)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=81, top=71, right=399, bottom=233),
        CropBounds(left=81, top=551, right=399, bottom=713),
    ]


async def test_splits_two_receipts_lying_corner_to_corner() -> None:
    # One receipt top-left, the other bottom-right, with no overlap on
    # either axis. Each side's paper is measured over its own rows and
    # columns; measured over both sides' the table would drown it.
    photo = _table_photo([(40, 40, 340, 300), (460, 340, 760, 600)], size=(800, 640))
    lines = _lines(70, 300, (80, 140, 200)) + _lines(490, 720, (380, 440, 500))
    cropper = _cropper(FakeTextDetector(lines))

    crops = await cropper.crop(_content(_png(photo)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=63, top=73, right=307, bottom=231),
        CropBounds(left=483, top=373, right=727, bottom=531),
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
# -------- Dark documents --------
# ================================

# The same receipts printed light on dark paper — a dark-themed report, a
# screenshot of a dark app. The splitter measures the paper beside the print
# rather than assuming it is light, so every judgement above holds with the
# colours swapped, and so does the one limitation: matching paper and table.
_DARK_PAPER = (12, 12, 12)
_LIGHT_TABLE = (225, 220, 210)
_MID_TABLE = (140, 120, 100)


@pytest.mark.parametrize("table", [_TABLE, _LIGHT_TABLE])
async def test_a_dark_document_crops_like_a_light_one(
    table: tuple[int, int, int],
) -> None:
    photo = _table_photo([(40, 80, 340, 400)], paper=_DARK_PAPER, table=table)
    cropper = _cropper(FakeTextDetector(_lines(70, 300, (120, 200, 280))))

    crops = await cropper.crop(_content(_png(photo)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=63, top=113, right=307, bottom=311)
    ]


async def test_splits_two_dark_documents_on_a_light_table() -> None:
    photo = _table_photo(
        [(40, 80, 340, 400), (460, 80, 760, 400)],
        paper=_DARK_PAPER,
        table=_LIGHT_TABLE,
    )
    cropper = _cropper(FakeTextDetector(_SIDE_BY_SIDE_LINES))

    crops = await cropper.crop(_content(_png(photo)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=63, top=113, right=307, bottom=311),
        CropBounds(left=483, top=113, right=727, bottom=311),
    ]


async def test_splits_a_dark_document_from_a_light_one() -> None:
    # A dark report beside a paper receipt on a mid-tone table: each side's
    # paper is measured on its own, so the table between them is neither.
    photo = _table_photo([(40, 80, 340, 400)], paper=_DARK_PAPER, table=_MID_TABLE)
    ImageDraw.Draw(photo).rectangle((460, 80, 760, 400), fill=_PAPER)
    cropper = _cropper(FakeTextDetector(_SIDE_BY_SIDE_LINES))

    crops = await cropper.crop(_content(_png(photo)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=63, top=113, right=307, bottom=311),
        CropBounds(left=483, top=113, right=727, bottom=311),
    ]


async def test_blank_lines_on_dark_paper_do_not_split() -> None:
    one_tall_sheet = _table_photo(
        [(60, 40, 420, 760)], size=(480, 800), paper=_DARK_PAPER, table=_LIGHT_TABLE
    )
    lines = _lines(90, 390, (80, 120, 160)) + _lines(90, 390, (500, 540, 580))
    cropper = _cropper(FakeTextDetector(lines))

    crops = await cropper.crop(_content(_png(one_tall_sheet)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=74, top=64, right=406, bottom=620)
    ]


async def test_two_dark_documents_on_a_dark_table_stay_one_crop() -> None:
    # The documented limitation, colours swapped: nothing distinguishes the
    # table between the two reports from their paper, so they are one crop.
    photo = _table_photo(
        [(40, 80, 340, 400), (460, 80, 760, 400)], paper=_DARK_PAPER, table=_DARK_PAPER
    )
    cropper = _cropper(FakeTextDetector(_SIDE_BY_SIDE_LINES))

    crops = await cropper.crop(_content(_png(photo)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=50, top=100, right=740, bottom=324)
    ]


# Two receipts whose blank side margins (160 px each) are wider than the
# table between them (100 px): most of the empty band between their print
# is paper. The strip of table inside it is still what separates them.
_WIDE_MARGINS = [(40, 80, 460, 400), (560, 80, 980, 400)]
_WIDE_MARGIN_LINES = _lines(70, 300, (120, 200, 280)) + _lines(
    720, 950, (120, 200, 280)
)


@pytest.mark.parametrize(
    ("paper", "table"), [(_PAPER, _TABLE), (_DARK_PAPER, _LIGHT_TABLE)]
)
async def test_wide_paper_margins_do_not_hide_the_table_between_documents(
    paper: tuple[int, int, int], table: tuple[int, int, int]
) -> None:
    photo = _table_photo(_WIDE_MARGINS, size=(1020, 480), paper=paper, table=table)
    cropper = _cropper(FakeTextDetector(_WIDE_MARGIN_LINES))

    crops = await cropper.crop(_content(_png(photo)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=63, top=113, right=307, bottom=311),
        CropBounds(left=713, top=113, right=957, bottom=311),
    ]


# ================================
# ------- Tilted documents -------
# ================================


def _tilted(image: Image.Image, angle: float) -> Image.Image:
    """The same photo taken with the camera turned by `angle` degrees."""
    return image.rotate(
        angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=_TABLE
    )


def _tilt_lines(
    lines: Sequence[TextBox],
    angle: float,
    *,
    before: tuple[int, int],
    after: tuple[int, int],
) -> list[TextBox]:
    """The boxes a detector reports on the tilted photo: each line's rectangle
    turned with it — a tilted outline inside an upright envelope."""
    radians = math.radians(angle)
    cos, sin = math.cos(radians), math.sin(radians)

    def turn(x: float, y: float) -> tuple[float, float]:
        dx, dy = x - before[0] / 2, y - before[1] / 2
        return (cos * dx + sin * dy + after[0] / 2, -sin * dx + cos * dy + after[1] / 2)

    boxes: list[TextBox] = []
    for line in lines:
        outline = tuple(
            turn(x, y)
            for x, y in (
                (line.left, line.top),
                (line.right, line.top),
                (line.right, line.bottom),
                (line.left, line.bottom),
            )
        )
        xs = [x for x, _ in outline]
        ys = [y for _, y in outline]
        boxes.append(
            TextBox(
                left=math.floor(min(xs)),
                top=math.floor(min(ys)),
                right=math.ceil(max(xs)),
                bottom=math.ceil(max(ys)),
                outline=outline,
            )
        )
    return boxes


def _vertical_lines(
    xs: Sequence[int], top: int, bottom: int, width: int = 24
) -> list[TextBox]:
    """Lines of print running down the page, as on a document photographed
    sideways: a tall, narrow outline whose longer edge is vertical."""
    return [
        TextBox(
            left=x,
            top=top,
            right=x + width,
            bottom=bottom,
            outline=((x, top), (x, bottom), (x + width, bottom), (x + width, top)),
        )
        for x in xs
    ]


_ONE_RECEIPT = _table_photo([(40, 80, 340, 400)])
_ONE_RECEIPT_LINES = _lines(70, 300, (120, 200, 280))


def _corner_pixels(image: Image.Image) -> list[tuple[int, int, int]]:
    pixels = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width = pixels.shape[:2]
    corners = ((1, 1), (width - 2, 1), (1, height - 2), (width - 2, height - 2))
    return [
        (int(pixels[y, x, 0]), int(pixels[y, x, 1]), int(pixels[y, x, 2]))
        for x, y in corners
    ]


def _is_paper(pixel: tuple[int, int, int]) -> bool:
    return all(
        abs(channel - reference) < 20 for channel, reference in zip(pixel, _PAPER)
    )


async def test_levels_tilted_documents_before_splitting() -> None:
    # Two receipts side by side, photographed at 25°: their boxes overlap on
    # both axes, so nothing separates them until the print is leveled.
    tilted = _tilted(_SIDE_BY_SIDE, 25)
    detector = FakeTextDetector(
        _tilt_lines(
            _SIDE_BY_SIDE_LINES, 25, before=_SIDE_BY_SIDE.size, after=tilted.size
        )
    )
    cropper = _cropper(detector)

    crops = await cropper.crop(_content(_png(tilted)))

    assert len(crops) == 2
    # Each crop is its receipt's print, upright, plus the margin — the size
    # the same receipts crop to when photographed square (244 × 198).
    for crop in crops:
        width, height = _decoded(crop.content.data).size
        assert abs(width - 244) <= 3 and abs(height - 198) <= 3
    # Left receipt first; each crop's bounds enclose its tilted region in the
    # photo, so they are wider than the crop and inside the photo.
    left, right = (crop.bounds for crop in crops)
    assert left.left < right.left
    for bounds in (left, right):
        assert bounds.width > 244 and bounds.height > 198
        assert 0 <= bounds.left < bounds.right <= tilted.width
        assert 0 <= bounds.top < bounds.bottom <= tilted.height
        assert bounds.page is None
    # Leveling maps the detected boxes; it does not detect again.
    assert len(detector.calls) == 1


async def test_a_tilted_receipts_crop_comes_out_upright() -> None:
    tilted = _tilted(_ONE_RECEIPT, 30)
    lines = _tilt_lines(
        _ONE_RECEIPT_LINES, 30, before=_ONE_RECEIPT.size, after=tilted.size
    )
    cropper = _cropper(FakeTextDetector(lines))

    (crop,) = await cropper.crop(_content(_png(tilted)))

    decoded = _decoded(crop.content.data)
    width, height = decoded.size
    assert abs(width - 244) <= 3 and abs(height - 198) <= 3
    # Level and within the paper: every corner of the crop is paper, where a
    # crop cut straight from the tilted photo would show table at the corners.
    assert all(_is_paper(pixel) for pixel in _corner_pixels(decoded))


async def test_splits_documents_printed_sideways() -> None:
    # Two receipts side by side, photographed a quarter turn off: their lines
    # run down the photo. A quarter turn is no tilt to level, and the height
    # of a line is its thickness, not how far it runs — measured from the
    # outline, so the gap the splitter asks for stays a few lines wide.
    lines = _vertical_lines((100, 160, 220), 110, 370) + _vertical_lines(
        (520, 580, 640), 110, 370
    )
    cropper = _cropper(FakeTextDetector(lines))

    crops = await cropper.crop(_content(_png(_SIDE_BY_SIDE)))

    assert [crop.bounds for crop in crops] == [
        CropBounds(left=92, top=102, right=252, bottom=378),
        CropBounds(left=512, top=102, right=672, bottom=378),
    ]


async def test_a_slight_tilt_is_left_alone() -> None:
    # A degree of tilt is not worth a resample: the crop is cut straight from
    # the photo, so it is exactly its recorded bounds.
    tilted = _tilted(_ONE_RECEIPT, 1)
    lines = _tilt_lines(
        _ONE_RECEIPT_LINES, 1, before=_ONE_RECEIPT.size, after=tilted.size
    )
    cropper = _cropper(FakeTextDetector(lines))

    (crop,) = await cropper.crop(_content(_png(tilted)))

    assert _decoded(crop.content.data).size == (crop.bounds.width, crop.bounds.height)


async def test_leveling_can_be_switched_off() -> None:
    tilted = _tilted(_SIDE_BY_SIDE, 25)
    lines = _tilt_lines(
        _SIDE_BY_SIDE_LINES, 25, before=_SIDE_BY_SIDE.size, after=tilted.size
    )
    cropper = _cropper(FakeTextDetector(lines), deskew_enabled=False)

    crops = await cropper.crop(_content(_png(tilted)))

    # Unleveled, the two receipts' boxes overlap on both axes: one crop.
    assert len(crops) == 1
    assert _decoded(crops[0].content.data).size == (
        crops[0].bounds.width,
        crops[0].bounds.height,
    )


async def test_boxes_without_outlines_are_not_leveled() -> None:
    # A detector that reports envelopes only gives nothing to measure a tilt
    # from; the photo is cropped as it is.
    tilted = _tilted(_SIDE_BY_SIDE, 25)
    envelopes = [
        TextBox(left=box.left, top=box.top, right=box.right, bottom=box.bottom)
        for box in _tilt_lines(
            _SIDE_BY_SIDE_LINES, 25, before=_SIDE_BY_SIDE.size, after=tilted.size
        )
    ]
    cropper = _cropper(FakeTextDetector(envelopes))

    crops = await cropper.crop(_content(_png(tilted)))

    assert len(crops) == 1
    assert _decoded(crops[0].content.data).size == (
        crops[0].bounds.width,
        crops[0].bounds.height,
    )


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
    # Rendered print is lossless: the crops are PNG whatever the source.
    assert all(crop.content.content_type is DocumentContentType.PNG for crop in crops)
    assert all(_decoded(crop.content.data).format == "PNG" for crop in crops)
    # Each crop records its page beside its rectangle.
    assert [crop.bounds for crop in crops] == [
        CropBounds(left=93, top=93, right=327, bottom=267, page=1),
        CropBounds(left=93, top=93, right=327, bottom=267, page=2),
    ]


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

    assert [crop.bounds.page for crop in crops] == [1]
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
