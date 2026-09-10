from __future__ import annotations

from collections.abc import Iterable

from app.integrations.ocr import (
    ImageArray,
    TextBox,
    TextDetectionError,
    TextDetector,
)


class FakeTextDetector(TextDetector):
    """`TextDetector` that returns canned boxes (or raises) and records the
    size of every image it was shown."""

    def __init__(
        self,
        boxes: Iterable[TextBox] = (),
        *,
        error: TextDetectionError | None = None,
    ) -> None:
        self.boxes = list(boxes)
        self.error = error
        # (height, width) of each image handed to detect, in call order.
        self.calls: list[tuple[int, int]] = []

    async def detect(self, image: ImageArray) -> list[TextBox]:
        self.calls.append((int(image.shape[0]), int(image.shape[1])))
        if self.error is not None:
            raise self.error
        return list(self.boxes)


__all__ = ["FakeTextDetector"]
