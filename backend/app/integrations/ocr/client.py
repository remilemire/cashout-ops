from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

# An image as detectors receive it: height × width × 3, RGB, 8-bit.
type ImageArray = NDArray[np.uint8]


@dataclass(frozen=True)
class TextBox:
    """An axis-aligned region of text, in pixel coordinates of the image it
    was detected on: `left`/`top` inclusive, `right`/`bottom` exclusive."""

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


class TextDetector(Protocol):
    """Finds the regions of an image that carry text.

    `detect` raises `TextDetectionError` when inference itself fails; an
    image with no text simply yields an empty list. Async like the other
    integration protocols, so a remote OCR service could stand behind it.
    """

    async def detect(self, image: ImageArray) -> list[TextBox]: ...


__all__ = ["ImageArray", "TextBox", "TextDetector"]
