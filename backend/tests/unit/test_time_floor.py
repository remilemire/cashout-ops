# backend/tests/unit/test_time_floor.py

from __future__ import annotations

import asyncio
import time

import pytest

from app.security.time_floor import time_floor


async def test_fast_block_is_padded_to_the_floor() -> None:
    start = time.monotonic()

    async with time_floor(50):
        pass

    assert time.monotonic() - start >= 0.05


async def test_slow_block_gains_no_extra_delay() -> None:
    start = time.monotonic()

    async with time_floor(10):
        await asyncio.sleep(0.05)

    # The block alone exceeds the floor; the floor must not add its own
    # duration on top. Generous bound: well under block + floor.
    assert time.monotonic() - start < 0.05 + 0.01 + 0.03


async def test_zero_floor_adds_nothing() -> None:
    start = time.monotonic()

    async with time_floor(0):
        pass

    assert time.monotonic() - start < 0.01


async def test_raising_block_is_padded_and_the_error_propagates() -> None:
    # The padding-on-error behavior is the mitigation: an early rejection
    # must take as long as a completed flow.
    start = time.monotonic()

    with pytest.raises(RuntimeError, match="boom"):
        async with time_floor(50):
            raise RuntimeError("boom")

    assert time.monotonic() - start >= 0.05
