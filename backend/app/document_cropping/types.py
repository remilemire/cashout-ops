"""What a crop is: the cut-out content, and where in the upload it came from."""

from __future__ import annotations

from dataclasses import dataclass

from app.lib.documents import DocumentContent


@dataclass(frozen=True)
class CropBounds:
    """Where a crop sits in the upload: the rectangle in the upright source
    image (after its EXIF rotation is applied) that encloses it — left/top
    inclusive, right/bottom exclusive — and, for a PDF, the 1-based page the
    rectangle is in. Tilted print is cut from a leveled copy of the source,
    so for such a crop this is the envelope of a rotated rectangle and wider
    than the crop itself."""

    left: int
    top: int
    right: int
    bottom: int
    page: int | None = None

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    def as_json(self) -> dict[str, int]:
        bounds = {
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
        }
        if self.page is not None:
            bounds["page"] = self.page
        return bounds


@dataclass(frozen=True)
class DocumentCrop:
    """One document cut out of an upload: its bytes — in the upload's format,
    or PNG for a PDF's rendered page — and where they were cut from."""

    content: DocumentContent
    bounds: CropBounds


__all__ = ["CropBounds", "DocumentCrop"]
