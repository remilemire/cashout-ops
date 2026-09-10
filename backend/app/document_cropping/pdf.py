"""Rendering a PDF's pages to images, so a PDF is cropped like a photo.

PDFium (via pypdfium2, a self-contained wheel) draws each page at the
requested resolution. The cropper then treats every page as one more image:
text detection, splitting, and cropping all run on the render, and the crops
are stored as PNG to avoid additional lossy compression of the rendered pixels.
"""

from __future__ import annotations

import logging

import pypdfium2 as pdfium
from PIL import Image

logger = logging.getLogger(__name__)

# PDF user space is 72 points to the inch; `dpi / 72` is the render scale.
_POINTS_PER_INCH = 72


class PdfRenderError(Exception):
    """The PDF could not be opened, or a page could not be drawn."""


def render_pdf_pages(data: bytes, *, dpi: int, max_pages: int) -> list[Image.Image]:
    """The first `max_pages` pages as RGB images at `dpi`, in page order."""
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as exc:
        raise PdfRenderError(str(exc)) from exc
    try:
        count = len(pdf)
        if count > max_pages:
            logger.info(
                "Rendering the first %d of a PDF's %d pages for cropping",
                max_pages,
                count,
            )
        pages: list[Image.Image] = []
        for index in range(min(count, max_pages)):
            try:
                page = pdf[index]
                rendered = page.render(scale=dpi / _POINTS_PER_INCH).to_pil()
            except pdfium.PdfiumError as exc:
                raise PdfRenderError(f"page {index + 1}: {exc}") from exc
            pages.append(rendered.convert("RGB"))
        return pages
    finally:
        pdf.close()


__all__ = ["PdfRenderError", "render_pdf_pages"]
