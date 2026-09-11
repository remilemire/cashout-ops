# backend/tests/unit/test_text_box.py

"""`TextBox` geometry: the outline a detector may report, and the tilt read
from it."""

from __future__ import annotations

import math

from app.integrations.ocr import TextBox


def _outline(
    angle: float, length: float = 100, height: float = 20
) -> tuple[tuple[float, float], ...]:
    radians = math.radians(angle)
    along = (math.cos(radians) * length, math.sin(radians) * length)
    down = (-math.sin(radians) * height, math.cos(radians) * height)
    return (
        (0.0, 0.0),
        along,
        (along[0] + down[0], along[1] + down[1]),
        down,
    )


def test_tilt_is_read_from_the_outlines_longer_edge() -> None:
    assert math.isclose(TextBox(0, 0, 100, 40, outline=_outline(20)).orientation, 20)
    assert math.isclose(TextBox(0, 0, 100, 40, outline=_outline(-15)).orientation, -15)


def test_the_longer_edge_is_found_whichever_corner_comes_first() -> None:
    outline = _outline(20)
    rotated_start = outline[1:] + outline[:1]

    assert math.isclose(TextBox(0, 0, 100, 40, outline=rotated_start).orientation, 20)


def test_tilt_past_forty_five_degrees_reads_as_the_other_way() -> None:
    # A line has no head: 80° is a line running the other way at -10°.
    assert math.isclose(TextBox(0, 0, 100, 100, outline=_outline(80)).orientation, -10)
    assert math.isclose(TextBox(0, 0, 100, 100, outline=_outline(-135)).orientation, 45)


def test_without_an_outline_there_is_no_tilt_and_the_envelope_is_the_shape() -> None:
    box = TextBox(left=10, top=20, right=110, bottom=40)

    assert box.orientation == 0.0
    assert box.corners == ((10, 20), (110, 20), (110, 40), (10, 40))
