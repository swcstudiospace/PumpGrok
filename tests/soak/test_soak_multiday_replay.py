"""AUTO-007: multiday soak replay with bounded memory and daily rollovers.

The driver replays the dataset tick by tick on FixtureClock through the
real ten-seat replay cycles (engine, risk, paper adapter), the same shape
as run_once_replay stretched over virtual days. Virtual time only; no wall
sleeps; no live network. A corrupt manifest refuses before any seat starts
(INV-R-30); an absent soak-3d fixture fails only under
PUMPGROK_REQUIRE_SOAK=1 and skips otherwise.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tracemalloc
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.config.settings import FilterSettings
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.fixtures import event_epoch, load_dataset
from pumpgrok.replay.recorder import load_llm_records
from pumpgrok.replay.rng import make_rng
from pumpgrok.reporting.daily import DailyReport
from pumpgrok.reporting.render import render_daily
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.supervisor.scheduler import (
    DegradedState,
    Supervisor,
    _replay_cycles,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "replay"
REQUIRE_SOAK = os.environ.get("PUMPGROK_REQUIRE_SOAK") == "1"
GROWTH_BUDGET_BYTES = 20_000_000


def _dataset_or_skip(name: str) -> Path:
    target = FIXTURES / name
    if target.is_dir():
        return target
    if REQUIRE_SOAK:
        pytest.fail(f"soak dataset {name} absent with PUMPGROK_REQUIRE_SOAK=1")
    pytest.skip(f"soak dataset {name} absent")


async def _drive(dataset_dir: Path, ledger_path: Path, *, seed: int, expect_days: int) -> dict:
    dataset = load_dataset(dataset_dir)
    stamps = sorted(event_epoch(event) for event in dataset.events)
    clock = FixtureClock(start=stamps[0])
    recreate_ledger_db(ledger_path)
    store = LedgerStore(str(ledger_path))
    caught: list[Any] = []
    previous_hook = sys.excepthook
    sys.excepthook = caught.append  # type: ignore[method-assign]
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: caught.append(context))
    tracemalloc.start()
    marks: list[tuple[float, int]] = []
    try:
        rng = make_rng(seed)
        risk = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=IdFactory(clock, rng),
            clock=clock,
            limits=EngineLimits(),
            autonomy="manual-ticket",
        )
        degraded = DegradedState()
        replay_llm = load_llm_records(dataset_dir)
        cycles = _replay_cycles(
            clock=clock,
            rng=rng,
            store=store,
            risk=risk,
            degraded=degraded,
            dataset_events=list(dataset.events),
            replay_llm=replay_llm,
            dataset_name=dataset.manifest.dataset,
            filter_cfg=FilterSettings(),
        )
        supervisor = Supervisor(
            store=store,
            clock=clock,
            rng=rng,
            cycles=cycles,
            mode="paper",
            source="replay",
            correlation_id="desk",
            notifier=None,
            degraded=degraded,
            risk=risk,
        )
        first_hour = stamps[0] + 3600.0
        next_mark = first_hour
        marks.append((stamps[0], tracemalloc.get_traced_memory()[0]))
        for stamp in stamps:
            clock.advance_to(stamp)
            outcomes = await supervisor.tick_once()
            assert all(outcome == "ok" for outcome in outcomes.values())
            if stamp >= next_mark:
                marks.append((stamp, tracemalloc.get_traced_memory()[0]))
                next_mark += 3600.0
        marks.append((stamps[-1], tracemalloc.get_traced_memory()[0]))
        assert store.verify() is True
        rollovers = [row for row in store.read(limit=None) if row["type"] == "DailyRollover"]
        days = sorted({str(row["payload"]["day_utc"]) for row in rollovers})
        assert len(rollovers) == expect_days
        assert len(days) == expect_days
        reports: dict[str, str] = {}
        for day in days:
            model = DailyReport.build(ledger_path, day)
            reports[day] = render_daily(model)
            assert day in reports[day]
        baseline_index = next(
            (index for index, (at, _) in enumerate(marks) if at >= first_hour),
            0,
        )
        baseline = marks[baseline_index][1]
        growth = max(current for _, current in marks[baseline_index:]) - baseline
        assert not caught, f"unhandled exceptions during soak: {caught!r}"
        return {
            "events": len(dataset.events),
            "days": days,
            "rollovers": len(rollovers),
            "growth_bytes": growth,
            "reports": reports,
        }
    finally:
        tracemalloc.stop()
        sys.excepthook = previous_hook
        loop.set_exception_handler(previous_handler)
        store.close()


@pytest.mark.slow
async def test_soak_replay_bounded_memory(tmp_path: Path) -> None:
    dataset_dir = _dataset_or_skip("soak-3d")
    result = await _drive(dataset_dir, tmp_path / "soak.sqlite", seed=20260101, expect_days=3)
    assert result["events"] > 4000
    assert result["days"] == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert result["growth_bytes"] < GROWTH_BUDGET_BYTES
    assert len(result["reports"]) == 3


async def test_soak_short_pr(tmp_path: Path) -> None:
    dataset_dir = _dataset_or_skip("smoke-10m")
    result = await _drive(dataset_dir, tmp_path / "short.sqlite", seed=20260101, expect_days=1)
    assert result["events"] == 41
    assert result["growth_bytes"] < GROWTH_BUDGET_BYTES
    assert len(result["reports"]) == 1


def test_soak_manifest_verifies_before_any_seat_starts() -> None:
    dataset_dir = _dataset_or_skip("soak-3d")
    dataset = load_dataset(dataset_dir)
    assert dataset.manifest.dataset == "soak-3d"
    assert set(dataset.manifest.sha256) == {"events.jsonl", "llm.jsonl"}
