"""Production entry policy: BUY reads are bound to one source object at both stages.

Direct-constructor adapters keep their existing behaviour; the policy slot is only
consulted when a policy is installed. Sells never consult it.
"""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.entry_hook import BoundEntryPolicy
from pumpgrok.execution.paper_adapter import CurveSnapshot, OrderRejectedError, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

START = 1_769_900_000.0
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-101"
MINT = "So11111111111111111111111111111111111111112"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SIZE = 200_000_000


class ScriptedCurves:
    """Fixture-labeled test source: pops one scripted snapshot per read, holds the last."""

    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


class SwappingCurves(ScriptedCurves):
    """Replaces the adapter's bound source during read number ``swap_at`` (zero-based)."""

    def __init__(self, reads: list[CurveSnapshot], *, swap_at: int) -> None:
        super().__init__(reads)
        self._calls = 0
        self._swap_at = swap_at
        self.adapter: PaperAdapter | None = None

    async def curve(self, mint: str) -> CurveSnapshot | None:
        index = self._calls
        self._calls += 1
        snapshot = await super().curve(mint)
        if index == self._swap_at and self.adapter is not None:
            self.adapter._price = ScriptedCurves([_snap("fixture")])
        return snapshot


class FailingCurves(ScriptedCurves):
    """Raises on read number ``fail_at`` (zero-based); otherwise behaves as scripted."""

    def __init__(self, reads: list[CurveSnapshot], *, fail_at: int) -> None:
        super().__init__(reads)
        self._calls = 0
        self._fail_at = fail_at

    async def curve(self, mint: str) -> CurveSnapshot | None:
        index = self._calls
        self._calls += 1
        if index == self._fail_at:
            raise RuntimeError("curve endpoint unavailable")
        return await super().curve(mint)


class DenyingEntryPolicy:
    """Test-owned policy: admits every source, refuses every entry snapshot."""

    def check_source(self, source: object | None) -> str | None:
        return None

    def check_snapshot(self, snapshot: CurveSnapshot) -> str | None:
        return "test policy denies entry"


def _snap(source: str) -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0, source=source)


def _build(
    tmp_path: Path, source: Any, *, bound: bool
) -> tuple[PaperAdapter, FixtureClock, LedgerStore]:
    clock = FixtureClock(START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    ids = IdFactory(clock, make_rng(7))
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(7)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    policy = BoundEntryPolicy(source, supported=(type(source),)) if bound else None
    adapter = PaperAdapter(
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(7),
        budget=RiskBudget(),
        price_source=source,
        entry_policy=policy,
        p_drop=0.0,
    )
    if isinstance(source, SwappingCurves):
        source.adapter = adapter
    return adapter, clock, store


def _harness(tmp_path: Path, reads: list[CurveSnapshot]) -> tuple[PaperAdapter, FixtureClock]:
    adapter, clock, _store = _build(tmp_path, ScriptedCurves(reads), bound=False)
    return adapter, clock


def _request(adapter: PaperAdapter, ticket: str, *, side: Side, units: int | None) -> OrderRequest:
    buy = side is Side.BUY
    return OrderRequest(
        ticket_id=ticket,
        mint=MINT,
        side=side,
        decision_id=adapter._ids.ulid(),
        size_lamports=SIZE if buy else None,
        token_units=None if buy else units,
        max_slippage_bps=100,
        approval_id=f"apr-{adapter._ids.ulid()}",
        correlation_id="test",
    )


async def _place(
    adapter: PaperAdapter,
    clock: FixtureClock,
    request: OrderRequest,
    *,
    seat: str,
    exit_reason: str | None = None,
) -> Fill:
    task = asyncio.create_task(
        adapter.place(request, seat=seat, exit_reason=exit_reason, correlation_id="test")
    )
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return await task


def _event_kinds(store: LedgerStore) -> list[str]:
    return [event["type"] for event in store.read(limit=None)]


def _rejections(store: LedgerStore) -> list[tuple[str, str]]:
    return [
        (row["payload"]["stage"], row["payload"]["reason"])
        for row in store.read(types=["OrderRejected"], limit=None)
    ]


async def test_installed_entry_policy_denies_buy_before_fill(tmp_path: Path) -> None:
    """The policy slot is honoured: a fixture BUY that every other gate admits is refused."""
    adapter, clock = _harness(tmp_path, [_snap("fixture")] * 3)
    adapter._entry_policy = DenyingEntryPolicy()  # type: ignore[attr-defined]
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    try:
        await _place(adapter, clock, request, seat="bot-04-sniper")
    except OrderRejectedError as exc:
        assert exc.reason == "data_unavailable"
    kinds = [event["type"] for event in adapter._store.read(limit=None)]
    assert "FillRecorded" not in kinds


async def test_bound_policy_admits_fixture_buy_at_both_stages(tmp_path: Path) -> None:
    adapter, clock, store = _build(tmp_path, ScriptedCurves([_snap("fixture")] * 3), bound=True)
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    fill = await _place(adapter, clock, request, seat="bot-04-sniper")
    assert fill.filled_units > 0
    assert "FillRecorded" in _event_kinds(store)
    assert _rejections(store) == []


async def test_source_replaced_during_accepted_read_denies_buy(tmp_path: Path) -> None:
    source = SwappingCurves([_snap("fixture")] * 3, swap_at=0)
    adapter, clock, store = _build(tmp_path, source, bound=True)
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    with pytest.raises(OrderRejectedError) as exc_info:
        await _place(adapter, clock, request, seat="bot-04-sniper")
    assert exc_info.value.reason == "data_unavailable"
    assert _rejections(store) == [("ACCEPTED", "data_unavailable")]
    assert "FillRecorded" not in _event_kinds(store)


async def test_source_replaced_during_confirming_read_denies_buy(tmp_path: Path) -> None:
    source = SwappingCurves([_snap("fixture")] * 3, swap_at=1)
    adapter, clock, store = _build(tmp_path, source, bound=True)
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    with pytest.raises(OrderRejectedError) as exc_info:
        await _place(adapter, clock, request, seat="bot-04-sniper")
    assert exc_info.value.reason == "data_unavailable"
    assert _rejections(store) == [("CONFIRMING", "data_unavailable")]
    assert "FillRecorded" not in _event_kinds(store)


@pytest.mark.parametrize(("fail_at", "stage"), [(0, "ACCEPTED"), (1, "CONFIRMING")])
async def test_read_error_at_each_buy_stage_denies_buy(
    tmp_path: Path, fail_at: int, stage: str
) -> None:
    source = FailingCurves([_snap("fixture")] * 3, fail_at=fail_at)
    adapter, clock, store = _build(tmp_path, source, bound=True)
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    with pytest.raises(OrderRejectedError) as exc_info:
        await _place(adapter, clock, request, seat="bot-04-sniper")
    assert exc_info.value.reason == "data_unavailable"
    assert _rejections(store) == [(stage, "data_unavailable")]
    assert "FillRecorded" not in _event_kinds(store)


async def test_bound_policy_calls_class_implementation_not_instance_attribute(
    tmp_path: Path,
) -> None:
    source = ScriptedCurves([_snap("fixture")] * 3)

    async def injected(mint: str) -> CurveSnapshot:
        return _snap("rpc")

    source.curve = injected  # type: ignore[method-assign]
    adapter, clock, store = _build(tmp_path, source, bound=True)
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    fill = await _place(adapter, clock, request, seat="bot-04-sniper")
    assert fill.filled_units > 0
    assert _rejections(store) == []


def test_subclass_of_supported_source_is_refused_at_policy_construction() -> None:
    class SubCurves(ScriptedCurves):
        pass

    with pytest.raises(ValueError, match="unsupported entry source"):
        BoundEntryPolicy(SubCurves([_snap("fixture")]), supported=(ScriptedCurves,))


def test_policy_without_supported_classes_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one supported"):
        BoundEntryPolicy(ScriptedCurves([_snap("fixture")]), supported=())


async def test_protective_sell_fills_while_entry_policy_is_installed(tmp_path: Path) -> None:
    """Entries only: a stop-loss exit on an rpc snapshot fills under the bound policy."""
    source = ScriptedCurves([_snap("fixture")] * 2 + [_snap("rpc")] * 8)
    adapter, clock, store = _build(tmp_path, source, bound=True)
    buy = _request(adapter, TICKET, side=Side.BUY, units=None)
    bought = await _place(adapter, clock, buy, seat="bot-04-sniper")
    sell = _request(adapter, TICKET, side=Side.SELL, units=bought.filled_units)
    sold = await _place(adapter, clock, sell, seat="bot-06-exit", exit_reason="stop_loss")
    assert sold.filled_units > 0
    assert _rejections(store) == []
