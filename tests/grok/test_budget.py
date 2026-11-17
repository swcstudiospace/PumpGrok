"""Layered persisted Grok budget: caps, reserve, rollover, restart, concurrency (GRK-04)."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

import pytest

from pumpgrok.grok.budget import (
    DAY_LIMIT,
    HOUR_LIMIT,
    MINUTE_LIMIT,
    RESERVE_PERCENT,
    BudgetUnavailable,
    LayeredBudget,
    reserve_slots,
)
from pumpgrok.replay.clock import FixtureClock

# 08:00:00 UTC on an hour boundary, so minute and hour windows are predictable.
START = 1_800_000_000.0


def test_limits_and_reserve_are_the_design_a_values() -> None:
    assert (MINUTE_LIMIT, HOUR_LIMIT, DAY_LIMIT) == (6, 60, 400)
    assert RESERVE_PERCENT == 20
    assert reserve_slots(MINUTE_LIMIT) == 2
    assert reserve_slots(HOUR_LIMIT) == 12
    assert reserve_slots(DAY_LIMIT) == 80


def test_ordinary_minute_cap_leaves_reserve_untouched(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    budget = LayeredBudget(tmp_path / "b.sqlite", clock)

    granted = [budget.try_charge(reserve_priority=False) for _ in range(6)]

    assert granted == [True, True, True, True, False, False]
    assert budget.usage()["minute"] == 4


def test_reserve_priority_may_use_the_full_minute_limit(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    budget = LayeredBudget(tmp_path / "b.sqlite", clock)

    granted = [budget.try_charge(reserve_priority=True) for _ in range(7)]

    assert granted == [True] * 6 + [False]
    assert budget.usage()["minute"] == 6


def test_ordinary_hour_cap(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    budget = LayeredBudget(tmp_path / "b.sqlite", clock)
    granted = 0
    for minute in range(12):  # 12 minutes x 4 ordinary calls = 48 = 60 - 12 reserve
        clock.advance_to(START + 60 * minute)
        for _ in range(4):
            granted += budget.try_charge(reserve_priority=False)
    clock.advance_to(START + 60 * 12)
    assert granted == 48
    assert budget.try_charge(reserve_priority=False) is False
    assert budget.usage()["hour"] == 48


def test_ordinary_day_cap_and_reserve_survive_the_hour_rollover(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    budget = LayeredBudget(tmp_path / "b.sqlite", clock)
    ordinary = 0
    for hour in range(7):  # 7 x 48 = 336 attempted; the day cap for ordinary calls is 320
        for minute in range(12):
            clock.advance_to(START + 3600 * hour + 60 * minute)
            for _ in range(4):
                ordinary += budget.try_charge(reserve_priority=False)
    assert ordinary == 320
    assert budget.usage()["day"] == 320

    reserved = 0
    for hour in (7, 8):
        for minute in range(10):
            clock.advance_to(START + 3600 * hour + 60 * minute)
            for _ in range(6):
                reserved += budget.try_charge(reserve_priority=True)
    assert reserved == 80
    assert budget.usage()["day"] == 400
    assert budget.try_charge(reserve_priority=True) is False


def test_windows_roll_over_at_utc_midnight(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    budget = LayeredBudget(tmp_path / "b.sqlite", clock)
    for _ in range(4):
        budget.try_charge(reserve_priority=False)
    assert budget.usage() == {"minute": 4, "hour": 4, "day": 4}

    midnight = 1_800_000_000.0 + (86400 - 28_800)  # 00:00:00 UTC of the next day
    clock.advance_to(midnight)
    assert budget.usage() == {"minute": 0, "hour": 0, "day": 0}
    assert budget.try_charge(reserve_priority=False) is True


def test_counts_survive_a_restart(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    first = LayeredBudget(tmp_path / "b.sqlite", clock)
    for _ in range(3):
        assert first.try_charge(reserve_priority=False)

    restarted = LayeredBudget(tmp_path / "b.sqlite", clock)
    assert restarted.usage()["minute"] == 3
    assert restarted.try_charge(reserve_priority=False) is True
    assert restarted.try_charge(reserve_priority=False) is False


def test_concurrent_claims_from_separate_handles_never_overspend(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    path = tmp_path / "b.sqlite"
    LayeredBudget(path, clock)  # create the schema once
    results: list[bool] = []
    lock = threading.Lock()
    barrier = threading.Barrier(20)

    def claim() -> None:
        handle = LayeredBudget(path, clock)
        barrier.wait()
        granted = handle.try_charge(reserve_priority=False)
        with lock:
            results.append(granted)

    threads = [threading.Thread(target=claim) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count(True) == 4
    assert LayeredBudget(path, clock).usage()["minute"] == 4


def test_unwritable_store_is_refused_at_construction(tmp_path: Path) -> None:
    with pytest.raises(BudgetUnavailable):
        LayeredBudget(tmp_path / "absent" / "b.sqlite", FixtureClock(start=START))


def test_store_lost_after_construction_refuses_the_charge(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = tmp_path / "store"
    store.mkdir()
    budget = LayeredBudget(store / "b.sqlite", clock)
    shutil.rmtree(store)

    with pytest.raises(BudgetUnavailable):
        budget.try_charge(reserve_priority=False)
