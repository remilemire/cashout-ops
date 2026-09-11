# backend/tests/unit/test_deskew.py

"""The cropper's leveling geometry: the tilt of the print, and the map
between a photo and its leveled copy."""

from __future__ import annotations

import math

import numpy as np
from PIL import Image

from app.document_cropping.deskew import Leveled, dominant_orientation
from app.integrations.ocr import TextBox


def _line(
    x: float, y: float, length: float, angle: float, height: float = 20
) -> TextBox:
    """A line of text `length` long at `angle` degrees (clockwise on screen),
    as a detector would report it: a tilted outline in an upright envelope."""
    radians = math.radians(angle)
    along = (math.cos(radians), math.sin(radians))
    down = (-math.sin(radians), math.cos(radians))
    outline = (
        (x, y),
        (x + along[0] * length, y + along[1] * length),
        (
            x + along[0] * length + down[0] * height,
            y + along[1] * length + down[1] * height,
        ),
        (x + down[0] * height, y + down[1] * height),
    )
    xs = [px for px, _ in outline]
    ys = [py for _, py in outline]
    return TextBox(
        left=math.floor(min(xs)),
        top=math.floor(min(ys)),
        right=math.ceil(max(xs)),
        bottom=math.ceil(max(ys)),
        outline=outline,
    )


def test_the_dominant_tilt_is_the_length_weighted_median() -> None:
    boxes = [
        _line(0, 0, 300, 10),
        _line(0, 50, 300, 12),
        _line(0, 100, 100, 40),
    ]

    # 10 and 12 carry 600 of the 700 units of length; the median lands on 12.
    assert math.isclose(dominant_orientation(boxes), 12)


def test_short_boxes_do_not_vote() -> None:
    # A squat box's rectangle can point either way, so only lines at least
    # twice as long as tall count.
    boxes = [_line(0, 0, 300, 5), _line(0, 50, 30, 40), _line(0, 100, 38, 40)]

    assert math.isclose(dominant_orientation(boxes), 5)


def test_no_outlines_means_no_tilt() -> None:
    assert dominant_orientation([TextBox(left=0, top=0, right=100, bottom=20)]) == 0.0
    assert dominant_orientation([]) == 0.0


def test_leveling_maps_source_pixels_where_pillow_puts_them() -> None:
    # A white mark in a black image: the map must land on the mark's new
    # position, to the pixel, in every direction of turn.
    for angle in (25, -20, 7.5):
        image = Image.new("RGB", (640, 480), (0, 0, 0))
        for x, y in ((100, 100), (500, 380), (10, 470)):
            image.paste((255, 255, 255), (x, y, x + 2, y + 2))

        leveled = Leveled.of(image, angle)

        bright = np.asarray(leveled.image)[:, :, 0] > 128
        for x, y in ((100, 100), (500, 380), (10, 470)):
            px, py = leveled.to_level((x + 1, y + 1))
            assert bright[
                round(py) - 1 : round(py) + 2, round(px) - 1 : round(px) + 2
            ].any()
            back = leveled.to_source((px, py))
            assert abs(back[0] - (x + 1)) < 1e-6 and abs(back[1] - (y + 1)) < 1e-6


def test_the_corners_of_a_photo_fit_the_leveled_canvas() -> None:
    leveled = Leveled.of(Image.new("RGB", (640, 480), (90, 70, 50)), 33)

    for corner in ((0, 0), (640, 0), (640, 480), (0, 480)):
        x, y = leveled.to_level(corner)
        assert -1 <= x <= leveled.image.width + 1
        assert -1 <= y <= leveled.image.height + 1


def test_a_tilted_line_becomes_a_tight_upright_box() -> None:
    image = Image.new("RGB", (640, 480), (90, 70, 50))
    line = _line(200, 200, 300, 25)
    # A line leaning 25° clockwise levels under a 25° counter-clockwise turn.
    leveled = Leveled.of(image, 25)

    level = leveled.level_box(line)

    # The envelope of a 300 × 20 line tilted 25° is about 280 × 147; leveled
    # it is the line itself (rounded outward by a pixel).
    assert 300 <= level.width <= 302
    assert 20 <= level.height <= 22
    assert not level.outline


def test_the_source_envelope_of_a_level_rectangle_is_clamped() -> None:
    leveled = Leveled.of(Image.new("RGB", (640, 480), (90, 70, 50)), 30)

    left, top, right, bottom = leveled.envelope_in_source(
        0, 0, leveled.image.width, leveled.image.height
    )

    assert (left, top, right, bottom) == (0, 0, 640, 480)
