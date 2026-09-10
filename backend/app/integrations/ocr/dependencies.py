from __future__ import annotations

from fastapi import Request

from .client import TextDetector


def get_text_detector(request: Request) -> TextDetector | None:
    """The startup-loaded detector, or None when cropping is disabled."""
    return request.app.state.text_detector


__all__ = ["get_text_detector"]
