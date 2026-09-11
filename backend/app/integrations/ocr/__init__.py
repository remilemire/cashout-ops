from __future__ import annotations

from .client import ImageArray, Point, TextBox, TextDetector
from .errors import TextDetectionError
from .ppocr import PPOCRTextDetector

__all__ = [
    "ImageArray",
    "PPOCRTextDetector",
    "Point",
    "TextBox",
    "TextDetectionError",
    "TextDetector",
]
