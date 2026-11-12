"""Held marks use paper ledger accounting and an injected virtual clock."""

from __future__ import annotations

import asyncio
import json
import random
from pathlib import Path

import pytest

from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.datafeed.graduation import GapSettings
from pumpgrok.datafeed.marks import HeldMarkScheduler, InMemoryTimeoutSink
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.tools.onchain import curve_layout

START = 1_769_900_000.0
S = 42_000_000_000
T = 766_428_571_428_571
UNITS = 3_000_000_000


class CountingClock(FixtureClock):
    def __init__(self) -> None:
        super().__init__(START)
        self.sleepers = 0

    async def sleep(self, seconds: float) -> None:
        self.sleepers += 1
        try:
            await super().sleep(seconds)
        finally:
            self.sleepers -= 1


class Curves:
    def __init__(self, clock: FixtureClock) -> None:
        self.clock = clock
        self.sources: dict[str, str | None] = {}

    async def curve(self, mint: str) -> CurveSnapshot | None:
        source = self.sources.get(mint)
        if source is None:
            return None
        return CurveSnapshot(mint=mint, s_lamports=S, t_units=T, source=source, ts=self.clock.now())


class Desk:
    def __init__(
        self,
        tmp_path: Path,
        *,
        capacity: int = 8,
        settings: GapSettings | None = None,
        timeout_sink: InMemoryTimeoutSink | None = None,
    ) -> None:
        self.clock = CountingClock()
        self.store = LedgerStore(str(tmp_path / "ledger.sqlite"))
        self.store.set_meta("initial_equity_lamports", "10000000000")
        self.store.set_meta("source", "paper")
        self.curves = Curves(self.clock)
        budget = RiskBudget()
        risk = RiskEngine(
            store=self.store,
            budget=budget,
            ids=IdFactory(self.clock, random.Random(7)),
            clock=self.clock,
            autonomy="autonomous-paper",  # type: ignore[arg-type]
            get_reserves=lambda _mint: (S, T),
        )
        self.adapter = PaperAdapter(
            store=self.store,
            risk=risk,
            ids=IdFactory(self.clock, random.Random(8)),
            clock=self.clock,
            rng=random.Random(9),
            budget=budget,
            price_source=self.curves,
            p_drop=0.0,
        )
        self.scheduler = HeldMarkScheduler(
            adapter=self.adapter,
            clock=self.clock,
            settings=settings or GapSettings(gap_after_s=30, timeout_after_s=120),
            max_observations=capacity,
            timeout_sink=timeout_sink,
        )

    def open(self, mint: str, source: str = "fixture") -> None:
        self.curves.sources[mint] = source
        self.store.append(
            ts_utc=self.clock.utc_iso(),
            source="paper",
            correlation_id="test",
            idempotency_key=f"open-{mint}",
            type="PositionOpened",
            payload={
                "source": "paper",
                "mint": mint,
                "price_entry": "0.00001",
                "token_units": UNITS,
                "cost_basis_lamports": 200_000_000,
                "opened_ts_utc": self.clock.utc_iso(),
            },
        )

    def remove(self, mint: str) -> None:
        self.store.append(
            ts_utc=self.clock.utc_iso(),
            source="paper",
            correlation_id="test",
            idempotency_key=f"close-{mint}",
            type="PositionClosed",
            payload={
                "source": "paper",
                "mint": mint,
                "price_exit": "0",
                "proceeds_lamports": 0,
                "realized_pnl_lamports": 0,
                "reason": "manual",
            },
        )

    def marks(self) -> list[dict]:
        return self.store.read(types=["MarkToMarket"], limit=None)

    def prices(self) -> list[dict]:
        return [json.loads(row["payload"]["prices_json"]) for row in self.marks()]

    async def advance(self, seconds: float) -> None:
        self.clock.advance_to(self.clock.now() + seconds)
        for _ in range(4):
            await self.clock.yield_to_loop()


async def test_held_mints_marked_within_sixty_seconds(tmp_path: Path) -> None:
    desk = Desk(tmp_path)
    desk.open("a")
    desk.open("b")
    await desk.scheduler.holdings_changed()
    await desk.advance(60)
    marks = desk.prices()
    # This is the semantic RED target: the temporary scheduler produces no ledger mark.
    assert {mint for row in marks for mint in row} == {"a", "b"}
    assert all(row[mint]["mtm_lamports"] > 0 for row in marks for mint in row)
    await desk.scheduler.close()


async def test_changing_holdings_and_flat_cancel_timer(tmp_path: Path) -> None:
    desk = Desk(tmp_path)
    await desk.scheduler.holdings_changed()
    await desk.advance(5)
    assert desk.clock.sleepers == 0
    desk.open("a")
    await desk.scheduler.holdings_changed()
    await desk.advance(30)
    desk.open("b")
    await desk.scheduler.holdings_changed()
    await desk.advance(30)
    assert any("a" in row for row in desk.prices())
    await desk.advance(30)
    assert any("b" in row for row in desk.prices())
    desk.remove("a")
    desk.remove("b")
    await desk.scheduler.holdings_changed()
    await desk.clock.yield_to_loop()
    assert desk.clock.sleepers == 0
    before = len(desk.marks())
    await desk.advance(120)
    assert len(desk.marks()) == before
    await desk.scheduler.close()


async def test_assumed_live_price_cannot_create_trusted_positive_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
    desk = Desk(tmp_path)
    desk.open("a", source="rpc")
    await desk.scheduler.holdings_changed()
    await desk.advance(60)
    assert all(row.get("a", {}).get("mtm_lamports", 0) == 0 for row in desk.prices())
    assert desk.adapter._fold_state().positions["a"].last_mtm_lamports == 0
    await desk.scheduler.close()


async def test_gap_and_timeout_preserve_last_mark_and_degrade_without_sale(
    tmp_path: Path,
) -> None:
    desk = Desk(tmp_path)
    desk.open("a")
    await desk.adapter.mark_open_positions(correlation_id="baseline")
    baseline = desk.adapter._fold_state().positions["a"].last_mtm_lamports
    assert baseline > 0
    reserves = desk.adapter._last_reserves["a"]
    last_price = desk.adapter._last_price_ts["a"]
    desk.curves.sources["a"] = None
    await desk.scheduler.holdings_changed()
    await desk.advance(60)
    assert desk.adapter._fold_state().positions["a"].last_mtm_lamports == baseline
    assert not desk.scheduler.degraded_mints
    before = len(desk.marks())
    await desk.advance(60)
    state = desk.adapter._fold_state()
    assert state.positions["a"].last_mtm_lamports == baseline
    assert len(desk.marks()) == before
    assert desk.scheduler.degraded_mints == {"a"}
    assert state.positions["a"].last_mtm_ts_utc
    assert state.positions["a"].token_units == UNITS
    assert desk.adapter._last_reserves["a"] == reserves
    assert desk.adapter._last_price_ts["a"] == last_price
    assert not desk.store.read(types=["FillRecorded", "PositionClosed"], limit=None)
    await desk.scheduler.close()


@pytest.mark.parametrize("marked", [True, False])
@pytest.mark.parametrize("elapsed", [10, 25])
async def test_restart_outage_uses_persisted_age_without_granting_trust(
    tmp_path: Path, marked: bool, elapsed: int
) -> None:
    settings = GapSettings(gap_after_s=10, timeout_after_s=20)
    first = Desk(tmp_path, settings=settings)
    first.open("a")
    if marked:
        await first.adapter.mark_open_positions(correlation_id="baseline")
    baseline = first.adapter._fold_state().positions["a"].last_mtm_lamports
    await first.scheduler.close()
    first.store.close()

    reopened = Desk(tmp_path, settings=settings)
    reopened.clock.advance_to(START + elapsed)
    before = len(reopened.marks())
    await reopened.scheduler.holdings_changed()
    if elapsed < 20:
        assert not reopened.scheduler.degraded_mints
        await reopened.advance(20 - elapsed)
    assert reopened.scheduler.degraded_mints == {"a"}
    assert reopened.adapter._fold_state().positions["a"].last_mtm_lamports == baseline
    assert len(reopened.marks()) == before
    assert not reopened.store.read(types=["FillRecorded", "PositionClosed"], limit=None)
    await reopened.scheduler.close()


async def test_mixed_gap_keeps_last_value_until_timeout_while_other_mint_marks(
    tmp_path: Path,
) -> None:
    desk = Desk(tmp_path)
    desk.open("a")
    desk.open("b")
    await desk.scheduler.holdings_changed()
    original = desk.adapter._fold_state().positions["a"].last_mtm_lamports
    assert original > 0
    desk.curves.sources["a"] = None
    await desk.advance(60)
    state = desk.adapter._fold_state()
    assert state.positions["a"].last_mtm_lamports == original
    assert state.positions["b"].last_mtm_lamports > 0
    assert "a" not in desk.prices()[-1]
    assert "b" in desk.prices()[-1]
    await desk.advance(60)
    state = desk.adapter._fold_state()
    assert state.positions["a"].last_mtm_lamports == original
    assert desk.scheduler.degraded_mints == {"a"}
    assert "a" not in desk.prices()[-1]
    assert state.positions["b"].last_mtm_lamports > 0
    assert state.positions["a"].token_units == UNITS
    assert not desk.store.read(types=["FillRecorded", "PositionClosed"], limit=None)
    await desk.scheduler.close()


async def test_unverified_frames_do_not_extend_short_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(curve_layout, "LAYOUT_STATUS", "ASSUMED")
    desk = Desk(tmp_path, settings=GapSettings(gap_after_s=10, timeout_after_s=20))
    desk.open("a")
    await desk.scheduler.holdings_changed()
    assert desk.adapter._fold_state().positions["a"].last_mtm_lamports > 0
    desk.curves.sources["a"] = "rpc"
    await desk.advance(19)
    assert desk.adapter._fold_state().positions["a"].last_mtm_lamports > 0
    await desk.advance(1)
    assert desk.adapter._fold_state().positions["a"].last_mtm_lamports > 0
    assert desk.scheduler.degraded_mints == {"a"}
    assert desk.adapter._fold_state().positions["a"].token_units == UNITS
    await desk.scheduler.close()


async def test_held_capacity_exhaustion_is_explicit(tmp_path: Path) -> None:
    desk = Desk(tmp_path, capacity=1)
    desk.open("a")
    desk.open("b")
    with pytest.raises(OverflowError):
        await desk.scheduler.holdings_changed()
    await desk.scheduler.close()


async def test_failed_timer_reports_once_then_restarts(tmp_path: Path, monkeypatch) -> None:
    desk = Desk(tmp_path)
    desk.open("a")
    await desk.scheduler.holdings_changed()
    original = desk.curves.curve

    async def failing(_mint: str) -> CurveSnapshot | None:
        raise RuntimeError("source failed")

    monkeypatch.setattr(desk.curves, "curve", failing)
    await desk.advance(60)
    monkeypatch.setattr(desk.curves, "curve", original)
    with pytest.raises(RuntimeError, match="source failed"):
        await desk.scheduler.holdings_changed()
    await desk.scheduler.holdings_changed()
    await desk.advance(60)
    assert "a" in desk.prices()[-1]
    await desk.scheduler.close()


async def test_older_snapshot_does_not_block_other_held_mint(tmp_path: Path, monkeypatch) -> None:
    desk = Desk(tmp_path)
    desk.open("a")
    desk.open("b")
    await desk.scheduler.holdings_changed()
    await desk.advance(1)

    async def curves(mint: str) -> CurveSnapshot:
        timestamp = START - 1 if mint == "a" else desk.clock.now()
        return CurveSnapshot(mint=mint, s_lamports=S, t_units=T, source="fixture", ts=timestamp)

    monkeypatch.setattr(desk.curves, "curve", curves)
    await desk.scheduler.holdings_changed()
    assert "a" not in desk.prices()[-1]
    assert "b" in desk.prices()[-1]
    await desk.advance(60)
    assert "b" in desk.prices()[-1]
    await desk.scheduler.close()


async def test_timeout_zero_request_uses_only_test_sink(tmp_path: Path) -> None:
    sink = InMemoryTimeoutSink()
    desk = Desk(
        tmp_path, settings=GapSettings(gap_after_s=10, timeout_after_s=20), timeout_sink=sink
    )
    desk.open("a")
    await desk.scheduler.holdings_changed()
    baseline = desk.adapter._fold_state().positions["a"].last_mtm_lamports
    desk.curves.sources["a"] = None
    await desk.advance(19)
    assert sink.requests == {}
    await desk.advance(1)
    count = len(desk.marks())
    assert sink.requests == {"a": (START + 20, 0)}
    assert desk.adapter._fold_state().positions["a"].last_mtm_lamports == baseline
    await desk.advance(60)
    assert sink.requests == {"a": (START + 20, 0)}
    assert len(desk.marks()) == count
    desk.curves.sources["a"] = "fixture"
    await desk.scheduler.holdings_changed()
    assert not desk.scheduler.degraded_mints
    await desk.scheduler.close()


async def test_fresh_graduation_prevents_timeout_without_sale(tmp_path: Path, monkeypatch) -> None:
    desk = Desk(tmp_path, settings=GapSettings(gap_after_s=10, timeout_after_s=20))
    desk.open("a")
    await desk.scheduler.holdings_changed()
    original = desk.adapter._fold_state().positions["a"].last_mtm_lamports

    async def completed(mint: str) -> CurveSnapshot:
        return CurveSnapshot(
            mint=mint,
            s_lamports=S,
            t_units=T,
            source="fixture",
            complete=True,
            ts=desk.clock.now(),
        )

    monkeypatch.setattr(desk.curves, "curve", completed)
    await desk.advance(20)
    await desk.advance(20)
    state = desk.adapter._fold_state()
    assert state.positions["a"].last_mtm_lamports == original
    assert state.positions["a"].token_units == UNITS
    assert not desk.store.read(types=["FillRecorded", "PositionClosed"], limit=None)
    await desk.scheduler.close()


async def test_graduation_after_timeout_remains_degraded_without_sale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = Desk(tmp_path, settings=GapSettings(gap_after_s=10, timeout_after_s=20))
    desk.open("a")
    await desk.scheduler.holdings_changed()
    original = desk.adapter._fold_state().positions["a"].last_mtm_lamports
    desk.curves.sources["a"] = None
    await desk.advance(20)
    assert desk.scheduler.degraded_mints == {"a"}

    async def completed(mint: str) -> CurveSnapshot:
        return CurveSnapshot(
            mint=mint,
            s_lamports=S,
            t_units=T,
            source="fixture",
            complete=True,
            ts=desk.clock.now(),
        )

    monkeypatch.setattr(desk.curves, "curve", completed)
    await desk.scheduler.holdings_changed()
    assert desk.scheduler.degraded_mints == {"a"}
    state = desk.adapter._fold_state()
    assert state.positions["a"].last_mtm_lamports == original
    assert state.positions["a"].token_units == UNITS
    assert not desk.store.read(types=["FillRecorded", "PositionClosed"], limit=None)
    await desk.scheduler.close()


async def test_concurrent_reconciliations_finish_without_losing_timer(tmp_path: Path) -> None:
    desk = Desk(tmp_path)
    desk.open("a")

    async def reconcile() -> None:
        async with desk.clock.timeout(1):
            await asyncio.gather(
                desk.scheduler.holdings_changed(), desk.scheduler.holdings_changed()
            )

    task = asyncio.create_task(reconcile())
    for _ in range(100):
        if task.done():
            break
        await desk.clock.yield_to_loop()
    if not task.done():
        await desk.advance(1)
    await task
    assert desk.clock.sleepers == 1
    await desk.scheduler.close()
    assert desk.clock.sleepers == 0


async def test_owner_wait_observes_ledger_failure_without_holdings_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = Desk(tmp_path)
    desk.open("a")
    await desk.scheduler.holdings_changed()

    async def fail_accounting(**_kwargs: object) -> None:
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(desk.adapter, "mark_open_positions", fail_accounting)
    owner = asyncio.create_task(desk.scheduler.wait())
    await desk.advance(60)
    with pytest.raises(RuntimeError, match="ledger unavailable"):
        await owner
    with pytest.raises(RuntimeError, match="ledger unavailable"):
        await desk.scheduler.close()


async def test_observed_timer_failure_allows_single_reconciliation_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    desk = Desk(tmp_path)
    desk.open("a")
    await desk.scheduler.holdings_changed()
    original = desk.adapter.mark_open_positions

    async def fail_accounting(**_kwargs: object) -> None:
        raise RuntimeError("ledger unavailable")

    monkeypatch.setattr(desk.adapter, "mark_open_positions", fail_accounting)
    owner = asyncio.create_task(desk.scheduler.wait())
    await desk.advance(60)
    with pytest.raises(RuntimeError, match="ledger unavailable"):
        await owner
    monkeypatch.setattr(desk.adapter, "mark_open_positions", original)
    await desk.scheduler.holdings_changed()
    before = len(desk.marks())
    await desk.advance(60)
    assert len(desk.marks()) > before
    await desk.scheduler.close()


async def test_owner_wait_completes_on_shutdown_even_when_flat(tmp_path: Path) -> None:
    desk = Desk(tmp_path)
    owner = asyncio.create_task(desk.scheduler.wait())
    await desk.clock.yield_to_loop()
    assert not owner.done()
    await desk.scheduler.close()
    await owner
