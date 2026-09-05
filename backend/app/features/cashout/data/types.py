# backend/app/features/cashout/data/types.py

from __future__ import annotations

from enum import StrEnum


class TipoutDepartment(StrEnum):
    BAR = "bar"
    KITCHEN = "kitchen"
    EXPO = "expo"
    HOST = "host"
    # Not selectable: reconciliation adds the manager to every cashout (see
    # data/service.py::reconcile).
    MANAGER = "manager"


__all__ = ["TipoutDepartment"]
