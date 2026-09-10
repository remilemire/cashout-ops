from __future__ import annotations

from .client import ImageArray, TextBox, TextDetector
from .errors import TextDetectionError
from .ppocr import PPOCRTextDetector

__all__ = [
    "ImageArray",
    "PPOCRTextDetector",
    "TextBox",
    "TextDetectionError",
    "TextDetector",
]
