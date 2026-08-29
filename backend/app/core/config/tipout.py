# backend/app/core/config/tipout.py

from __future__ import annotations

from decimal import Decimal

from pydantic_settings import SettingsConfigDict

from .base import SettingsGroup


class TipoutSettings(SettingsGroup):
    """Per-department tipout rates, as a fraction of the sales they apply to.

    0.05 is 5%. The bar tips out on drink sales, the kitchen on food sales,
    expo and host on total sales — see the generated columns on `cashout_data`.

    These are the rates *currently* in force. Completion copies them onto the
    row it writes, so changing one here only ever affects cashouts closed after
    the change; every cashout already closed keeps the rate it was reconciled
    under.
    """

    model_config = SettingsConfigDict(env_prefix="TIPOUT_")

    # TODO(tipout): placeholder rates — replace with the real ones before this
    # reaches a real cashout.
    BAR_RATE: Decimal = Decimal("0.0500")
    KITCHEN_RATE: Decimal = Decimal("0.0300")
    EXPO_RATE: Decimal = Decimal("0.0100")
    HOST_RATE: Decimal = Decimal("0.0100")


__all__ = ["TipoutSettings"]
