from __future__ import annotations


class TextDetectionError(Exception):
    """Text detection could not run over an image (a failed inference, or an
    image the detector cannot take). Callers treat it as "no text found" for
    the purpose of cropping; the upload itself is never at stake."""


__all__ = ["TextDetectionError"]
