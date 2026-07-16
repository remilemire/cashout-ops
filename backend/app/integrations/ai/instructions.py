from __future__ import annotations

_EXTRA_HEADER = "# Additional instructions"

# Base system prompt every provider client applies; caller instructions layer on
# top of it (see compose_instructions).
BASE_INSTRUCTIONS = (
    "You are a meticulous document-analysis assistant. Work only from what is "
    "visible in the provided document; never invent, guess, or infer values "
    "that are not present. When a requested value is missing or illegible, "
    "leave it empty rather than fabricating it."
)


def compose_instructions(base: str, extra: str | None = None) -> str:
    """Return `base`, with `extra` appended under a header when provided.

    Every AI abstraction keeps its own always-present base instructions and
    layers caller-supplied instructions on top, rather than letting callers
    replace the base wholesale.
    """
    if extra is None:
        return base
    return f"{base}\n\n{_EXTRA_HEADER}\n\n{extra}"


__all__ = ["BASE_INSTRUCTIONS", "compose_instructions"]
