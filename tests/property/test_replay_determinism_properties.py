"""QLT-07: replay determinism under the injected FixtureClock and the pure ledger fold (D-02).

Virtual time moves only through advance_to. Timers fire in (deadline, scheduling order), so the
wake order of a set of sleepers depends on their deadlines and never on how the clock is advanced.
The ledger fold is pure: the same rows always produce the same canonical digest, and the digest
moves when the folded state moves.
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pumpgrok.ledger.reducer import dump_state, initial_state, reduce
from pumpgrok.replay.clock import FixtureClock

DELAY = st.integers(min_value=0, max_value=50)
DELAYS = st.lists(DELAY, min_size=1, max_size=12)
CUTS = st.lists(st.integers(min_value=0, max_value=60), min_size=0, max_size=8)


async def _wake_order(delays: list[int], cuts: list[int]) -> list[int]:
    clock = FixtureClock(0.0)
    order: list[int] = []

    async def sleeper(index: int, delay: int) -> None:
        await clock.sleep(float(delay))
        order.append(index)

    tasks = [asyncio.create_task(sleeper(index, delay)) for index, delay in enumerate(delays)]
    await clock.yield_to_loop()
    final = max([*cuts, *delays])
    for stamp in [*sorted(cuts), final]:
        clock.advance_to(float(stamp))
        await clock.yield_to_loop()
    await asyncio.gather(*tasks)
    return order


def _expected_order(delays: list[int]) -> list[int]:
    return [index for index, _ in sorted(enumerate(delays), key=lambda pair: (pair[1], pair[0]))]


@settings(max_examples=150, deadline=None)
@given(delays=DELAYS, cuts=CUTS)
def test_wake_order_follows_deadline_then_scheduling_order_for_any_advance_pattern(
    delays: list[int], cuts: list[int]
) -> None:
    observed = asyncio.run(_wake_order(delays, cuts))
    assert observed == _expected_order(delays)


@settings(max_examples=150, deadline=None)
@given(delays=DELAYS, cuts=CUTS)
def test_advance_pattern_does_not_change_the_wake_order(delays: list[int], cuts: list[int]) -> None:
    chunked = asyncio.run(_wake_order(delays, cuts))
    single = asyncio.run(_wake_order(delays, []))
    assert chunked == single


@settings(max_examples=200, deadline=None)
@given(
    start=st.integers(min_value=1, max_value=1000),
    back_millis=st.integers(min_value=1, max_value=999),
)
def test_virtual_time_never_moves_backwards(start: int, back_millis: int) -> None:
    clock = FixtureClock(float(start))
    with pytest.raises(ValueError, match="cannot move backwards"):
        clock.advance_to(start - back_millis / 1000)
    assert clock.now() == float(start)


def _digest(rows: list[dict[str, Any]]) -> str:
    state = initial_state(source="paper", initial_equity_lamports=10**12, day_utc="2026-01-01")
    for row in rows:
        state = reduce(state, row)
    canonical = json.dumps(dump_state(state), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@settings(max_examples=150, deadline=None)
@given(
    steps=st.lists(st.integers(min_value=1, max_value=5), min_size=1, max_size=10),
    unknown=st.lists(st.booleans(), min_size=10, max_size=10),
)
def test_fold_digest_is_stable_and_moves_with_the_folded_state(
    steps: list[int], unknown: list[bool]
) -> None:
    rows: list[dict[str, Any]] = []
    seq = 0
    for index, step in enumerate(steps):
        seq += step
        is_unknown = unknown[index]
        rows.append(
            {
                "seq": seq,
                "type": "FutureThing" if is_unknown else "HaltSet",
                "ts_utc": "2026-01-01T00:00:00.000000Z",
                "correlation_id": f"cid-{seq}",
                "payload": {"n": index} if is_unknown else {"reason": f"halt-{index}"},
            }
        )
    digest = _digest(rows)
    assert _digest(copy.deepcopy(rows)) == digest
    moved = copy.deepcopy(rows)
    moved[-1]["seq"] = rows[-1]["seq"] + 1
    assert _digest(moved) != digest
