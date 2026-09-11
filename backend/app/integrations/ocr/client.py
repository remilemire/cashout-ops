from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

# An image as detectors receive it: height × width × 3, RGB, 8-bit.
type ImageArray = NDArray[np.uint8]
# A position in image pixels, (x, y), fractional as detectors compute it.
type Point = tuple[float, float]


@dataclass(frozen=True)
class TextBox:
    """A region of text, in pixel coordinates of the image it was detected on.

    `left`/`top` (inclusive) and `right`/`bottom` (exclusive) are the region's
    axis-aligned envelope. `outline` is the region's own shape when the
    detector knows it: the corners of its minimum-area rectangle, in order
    around it, so a tilted line of text is a tilted rectangle inside an
    upright envelope. It is empty when only the envelope is known.
    """

    left: int
    top: int
    right: int
    bottom: int
    outline: tuple[Point, ...] = ()

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def corners(self) -> tuple[Point, ...]:
        """The outline, or the envelope's corners when there is none."""
        if self.outline:
            return self.outline
        return (
            (self.left, self.top),
            (self.right, self.top),
            (self.right, self.bottom),
            (self.left, self.bottom),
        )

    @property
    def length(self) -> float:
        """The outline's longer edge: how far the line of text runs, whatever
        its tilt. The envelope's width without an outline."""
        return max(self._edges) if len(self.outline) >= 3 else float(self.width)

    @property
    def thickness(self) -> float:
        """The outline's shorter edge: the height of the line of text, whatever
        its tilt. The envelope's height without an outline."""
        return min(self._edges) if len(self.outline) >= 3 else float(self.height)

    @property
    def _edges(self) -> tuple[float, float]:
        (x0, y0), (x1, y1), (x2, y2) = self.outline[:3]
        return math.hypot(x1 - x0, y1 - y0), math.hypot(x2 - x1, y2 - y1)

    @property
    def orientation(self) -> float:
        """The text line's tilt in degrees, in (-45, 45]: the direction of the
        outline's longer edge from the x axis, with y pointing down, so a
        positive angle leans clockwise on screen. 0 without an outline."""
        if len(self.outline) < 3:
            return 0.0
        (x0, y0), (x1, y1), (x2, y2) = self.outline[:3]
        edges = ((x1 - x0, y1 - y0), (x2 - x1, y2 - y1))
        dx, dy = max(edges, key=lambda edge: math.hypot(*edge))
        return _line_angle(math.degrees(math.atan2(dy, dx)))


def _line_angle(degrees: float) -> float:
    """A line's direction folded into (-45, 45]: a line has no head, and text
    tilted past 45° reads as lines running the other way."""
    folded = degrees % 180
    if folded > 90:
        folded -= 180
    if folded > 45:
        folded -= 90
    elif folded <= -45:
        folded += 90
    return folded


class TextDetector(Protocol):
    """Finds the regions of an image that carry text.

    `detect` raises `TextDetectionError` when inference itself fails; an
    image with no text simply yields an empty list. Async like the other
    integration protocols, so a remote OCR service could stand behind it.
    """

    async def detect(self, image: ImageArray) -> list[TextBox]: ...


__all__ = ["ImageArray", "Point", "TextBox", "TextDetector"]
