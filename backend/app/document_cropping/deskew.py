# backend/app/document_cropping/deskew.py

"""Leveling a tilted image before its print is split into documents.

A phone photo rarely holds its documents square to the frame, and the
splitter cuts along empty bands parallel to the axes: two documents lying at
an angle overlap on both axes and never come apart. Detected text carries
its own tilt (`TextBox.orientation`); the dominant tilt across the image is
taken as the image's, and rotating the image by it puts the print level. The
same rotation maps the detected boxes into the level frame, so nothing is
detected twice and detection scale and thresholds are untouched. Crops cut
from the level image come out upright.

Two documents lying at different angles level by the dominant one; the other
stays tilted, and still comes apart when the table between them is wide.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from PIL import Image

from app.integrations.ocr import Point, TextBox

# Below this tilt a resample costs more than the leveling is worth.
MIN_LEVELING_ANGLE = 2.0
# A box this many times longer than tall has a tilt worth trusting; a short
# word's rectangle can point either way. Detectors grow their outlines around
# the print (DB's unclip), so even a full line is only two to three times
# longer than tall.
_ELONGATION = 2.0


def dominant_orientation(boxes: Sequence[TextBox]) -> float:
    """The tilt of the print, in degrees: the length-weighted median tilt of
    the elongated boxes, or 0.0 when no box is elongated."""
    weighted: list[tuple[float, float]] = []
    for box in boxes:
        if not box.outline or box.thickness <= 0:
            continue
        if box.length / box.thickness < _ELONGATION:
            continue
        weighted.append((box.orientation, box.length))
    if not weighted:
        return 0.0
    weighted.sort()
    half = sum(weight for _, weight in weighted) / 2
    accumulated = 0.0
    for angle, weight in weighted:
        accumulated += weight
        if accumulated >= half:
            return angle
    return weighted[-1][0]


@dataclass(frozen=True)
class Leveled:
    """An image rotated by `angle` degrees (counter-clockwise, as Pillow
    counts) about its centre and grown to fit, with the map between the
    source's pixels and its own."""

    image: Image.Image
    angle: float
    source_width: int
    source_height: int

    @classmethod
    def of(cls, image: Image.Image, angle: float) -> Leveled:
        """Rotate `image` by `angle`, filling the corners with the image's
        median colour: the table, in a photo, so the fill reads as background
        rather than as a fourth edge of paper."""
        rotated = image.rotate(
            angle,
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor=_median_colour(image),
        )
        return cls(
            image=rotated,
            angle=angle,
            source_width=image.width,
            source_height=image.height,
        )

    def to_level(self, point: Point) -> Point:
        """A source pixel position in the level image."""
        cos, sin = self._cos_sin
        dx = point[0] - self.source_width / 2
        dy = point[1] - self.source_height / 2
        return (
            cos * dx + sin * dy + self.image.width / 2,
            -sin * dx + cos * dy + self.image.height / 2,
        )

    def to_source(self, point: Point) -> Point:
        """A level-image pixel position back in the source."""
        cos, sin = self._cos_sin
        dx = point[0] - self.image.width / 2
        dy = point[1] - self.image.height / 2
        return (
            cos * dx - sin * dy + self.source_width / 2,
            sin * dx + cos * dy + self.source_height / 2,
        )

    def level_box(self, box: TextBox) -> TextBox:
        """The box's envelope in the level image: of its outline when it has
        one, so tilted text becomes a tight upright box."""
        return TextBox(
            *_envelope(
                [self.to_level(corner) for corner in box.corners],
                width=self.image.width,
                height=self.image.height,
            )
        )

    def envelope_in_source(
        self, left: int, top: int, right: int, bottom: int
    ) -> tuple[int, int, int, int]:
        """The source rectangle enclosing a level-image rectangle."""
        corners = [(left, top), (right, top), (right, bottom), (left, bottom)]
        return _envelope(
            [self.to_source(corner) for corner in corners],
            width=self.source_width,
            height=self.source_height,
        )

    @property
    def _cos_sin(self) -> tuple[float, float]:
        radians = math.radians(self.angle)
        return math.cos(radians), math.sin(radians)


def _envelope(
    points: Sequence[Point], *, width: int, height: int
) -> tuple[int, int, int, int]:
    """The pixel rectangle enclosing the points, clamped to the image."""
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return (
        max(0, math.floor(min(xs))),
        max(0, math.floor(min(ys))),
        min(width, math.ceil(max(xs))),
        min(height, math.ceil(max(ys))),
    )


def _median_colour(image: Image.Image) -> tuple[int, int, int]:
    # A thumbnail is plenty to find the colour most of the image is.
    sample = np.asarray(image.resize((64, 64)), dtype=np.uint8).reshape(-1, 3)
    red, green, blue = np.median(sample, axis=0)
    return int(red), int(green), int(blue)


__all__ = ["MIN_LEVELING_ANGLE", "Leveled", "dominant_orientation"]
