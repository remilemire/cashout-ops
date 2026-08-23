# backend/app/document_ai/hints.py

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel

from .schemas import ClassificationT


@dataclass(frozen=True)
class ClassificationHint:
    """Per-type content cues for classification prompts."""

    # Content whose presence indicates this document type.
    markers: tuple[str, ...] = ()
    # Content whose presence argues against this document type.
    anti_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class FieldHint:
    """Where one schema field's value appears, attached via `Annotated` metadata.

    Riding the annotation keeps the hint beside the field it describes while
    staying out of the JSON schema sent to providers (unlike
    `Field(description=...)`).
    """

    # Printed labels the value may appear under.
    labels: tuple[str, ...] = ()
    # Document sections or headings the value appears within.
    sections: tuple[str, ...] = ()
    # Nearby text that confirms a candidate value.
    anchors: tuple[str, ...] = ()
    # Nearby text that disqualifies a candidate value.
    anti_anchors: tuple[str, ...] = ()


# The renderers translate hints into plain guidance: the prompt never sees the
# structural vocabulary above (markers, labels, anchors, ...) and carries no
# preamble explaining it. Empty groups are skipped, a hint with no content
# renders nothing, and both renderers return None when nothing renders so
# hint-less calls stay byte-identical to before.


def render_classification_hints(
    hints: Mapping[ClassificationT, ClassificationHint],
) -> str | None:
    lines: list[str] = []
    for classification, hint in hints.items():
        parts: list[str] = []
        if hint.markers:
            parts.append(f"expect: {', '.join(hint.markers)}")
        if hint.anti_markers:
            parts.append(f"unlikely if: {', '.join(hint.anti_markers)}")
        if not parts:
            continue
        # Keyed by enum value: the exact token the response schema permits.
        lines.append(f"* {classification.value} — {'; '.join(parts)}.")
    if not lines:
        return None
    return "\n".join(lines)


def collect_field_hints(model: type[BaseModel]) -> Mapping[str, FieldHint]:
    """Pick each field's `FieldHint` out of its `Annotated` metadata.

    Top-level fields only — nested models would need their own harvest.
    """
    hints: dict[str, FieldHint] = {}
    for name, field in model.model_fields.items():
        for metadata in field.metadata:
            if isinstance(metadata, FieldHint):
                hints[name] = metadata
    return hints


def _quoted(values: tuple[str, ...]) -> str:
    return " or ".join(f'"{value}"' for value in values)


def render_field_hints(hints: Mapping[str, FieldHint]) -> str | None:
    lines: list[str] = []
    for field, hint in hints.items():
        parts: list[str] = []
        if hint.labels:
            parts.append(f"usually labelled {_quoted(hint.labels)}")
        if hint.sections:
            parts.append(f"found in the {' or '.join(hint.sections)} section")
        if hint.anchors:
            parts.append(f"look near: {', '.join(hint.anchors)}")
        if hint.anti_anchors:
            parts.append(
                f"do not confuse with values marked {_quoted(hint.anti_anchors)}"
            )
        if not parts:
            continue
        lines.append(f"* {field} — {'; '.join(parts)}.")
    if not lines:
        return None
    return "\n".join(lines)


__all__ = [
    "ClassificationHint",
    "FieldHint",
    "collect_field_hints",
    "render_classification_hints",
    "render_field_hints",
]
