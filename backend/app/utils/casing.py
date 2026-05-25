# backend/app/utils/casing.py

from __future__ import annotations

# ================================
# ------------ Snake -------------
# ================================


def snake_to_camel(s: str) -> str:
    head, *rest = s.split("_")
    return head + "".join(w.capitalize() for w in rest)


def camel_to_snake(s: str) -> str:
    return "".join(f"_{c.lower()}" if c.isupper() else c for c in s)


# ================================
# ------------ Kebab -------------
# ================================


def snake_to_kebab(s: str) -> str:
    return s.replace("_", "-")


def kebab_to_snake(s: str) -> str:
    return s.replace("-", "_")


# ================================
# ------------ Pascal ------------
# ================================


def snake_to_pascal(s: str) -> str:
    return "".join(w.capitalize() for w in s.split("_"))


def pascal_to_snake(s: str) -> str:
    return "".join(
        f"_{c.lower()}" if i and c.isupper() else c.lower()
        for i, c in enumerate(s)
    )
