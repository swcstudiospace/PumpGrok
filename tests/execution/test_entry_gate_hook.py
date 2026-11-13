"""Production entry policy: BUY reads are bound to one source object at both stages.

Replay-bound adapters are composed by :func:`build_paper_adapter` from a
:func:`verify_replay` token, so every BUY that fills prices from the verified
dataset. Direct-constructor adapters keep their existing behaviour; the policy slot
is only consulted when a policy is installed. Sells never consult it.
"""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution import build_paper_adapter
from pumpgrok.execution.entry_hook import BoundEntryPolicy
from pumpgrok.execution.paper_adapter import CurveSnapshot, OrderRejectedError, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock
from pumpgrok.replay.rng import make_rng
from pumpgrok.replay.sources import FixtureCurveSource
from pumpgrok.risk.engine import RiskEngine

from .replay_support import replay_authority, tick

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


class DenyingEntryPolicy:
    """Test-owned policy: admits every source, refuses every entry snapshot."""

    def check_source(self, source: object | None) -> str | None:
        return None

    def check_snapshot(self, snapshot: CurveSnapshot) -> str | None:
        return "test policy denies entry"


def _snap(source: str) -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0, source=source)


def _store(tmp_path: Path, ledger_source: str) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", ledger_source)
    return store


def _engine(store: LedgerStore, clock: FixtureClock) -> RiskEngine:
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(7)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )


def _replay_build(
    tmp_path: Path,
) -> tuple[PaperAdapter, FixtureClock, LedgerStore, FixtureCurveSource]:
    """Replay-bound adapter over one verified tick of S0/T0 at START."""
    clock = FixtureClock(START)
    store = _store(tmp_path, "replay")
    replay = replay_authority(tmp_path, clock, [tick(START, MINT, S0, T0)])
    adapter = build_paper_adapter(
        object(),
        store=store,
        risk=_engine(store, clock),
        ids=IdFactory(clock, make_rng(7)),
        clock=clock,
        rng=make_rng(7),
        replay=replay,
        source="replay",
        p_drop=0.0,
    )
    return adapter, clock, store, replay.curves


def _harness(tmp_path: Path, reads: list[CurveSnapshot]) -> tuple[PaperAdapter, FixtureClock]:
    """Unbound adapter over injected reads: no entry policy, no replay authority."""
    clock = FixtureClock(START)
    store = _store(tmp_path, "paper")
    adapter = PaperAdapter(
        store=store,
        risk=_engine(store, clock),
        ids=IdFactory(clock, make_rng(7)),
        clock=clock,
        rng=make_rng(7),
        budget=RiskBudget(),
        price_source=ScriptedCurves(reads),
        p_drop=0.0,
    )
    return adapter, clock


def _swap_source_on_read(
    monkeypatch: pytest.MonkeyPatch, adapter: PaperAdapter, *, swap_at: int
) -> None:
    """After read ``swap_at`` (zero-based) the adapter's bound source is replaced."""
    real = FixtureCurveSource.curve
    calls = 0

    async def curve(self: FixtureCurveSource, mint: str) -> CurveSnapshot | None:
        nonlocal calls
        index = calls
        calls += 1
        snapshot = await real(self, mint)
        if index == swap_at:
            adapter._price = ScriptedCurves([_snap("fixture")])
        return snapshot

    monkeypatch.setattr(FixtureCurveSource, "curve", curve)


def _fail_read(monkeypatch: pytest.MonkeyPatch, *, fail_at: int) -> None:
    """Read number ``fail_at`` (zero-based) raises; every other read is the real one."""
    real = FixtureCurveSource.curve
    calls = 0

    async def curve(self: FixtureCurveSource, mint: str) -> CurveSnapshot | None:
        nonlocal calls
        index = calls
        calls += 1
        if index == fail_at:
            raise RuntimeError("curve endpoint unavailable")
        return await real(self, mint)

    monkeypatch.setattr(FixtureCurveSource, "curve", curve)


def _rpc_reads(curves: FixtureCurveSource) -> None:
    """Instance-level override: the BUY policy ignores it; sells still read through it."""

    async def injected(mint: str) -> CurveSnapshot:
        return _snap("rpc")

    curves.curve = injected  # type: ignore[method-assign]


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
    adapter, clock, store, _curves = _replay_build(tmp_path)
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    fill = await _place(adapter, clock, request, seat="bot-04-sniper")
    assert fill.filled_units > 0
    assert "FillRecorded" in _event_kinds(store)
    assert _rejections(store) == []


async def test_source_replaced_during_accepted_read_denies_buy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, clock, store, _curves = _replay_build(tmp_path)
    _swap_source_on_read(monkeypatch, adapter, swap_at=0)
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    with pytest.raises(OrderRejectedError) as exc_info:
        await _place(adapter, clock, request, seat="bot-04-sniper")
    assert exc_info.value.reason == "data_unavailable"
    assert _rejections(store) == [("ACCEPTED", "data_unavailable")]
    assert "FillRecorded" not in _event_kinds(store)


async def test_source_replaced_during_confirming_read_denies_buy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter, clock, store, _curves = _replay_build(tmp_path)
    _swap_source_on_read(monkeypatch, adapter, swap_at=1)
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    with pytest.raises(OrderRejectedError) as exc_info:
        await _place(adapter, clock, request, seat="bot-04-sniper")
    assert exc_info.value.reason == "data_unavailable"
    assert _rejections(store) == [("CONFIRMING", "data_unavailable")]
    assert "FillRecorded" not in _event_kinds(store)


@pytest.mark.parametrize(("fail_at", "stage"), [(0, "ACCEPTED"), (1, "CONFIRMING")])
async def test_read_error_at_each_buy_stage_denies_buy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail_at: int, stage: str
) -> None:
    adapter, clock, store, _curves = _replay_build(tmp_path)
    _fail_read(monkeypatch, fail_at=fail_at)
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    with pytest.raises(OrderRejectedError) as exc_info:
        await _place(adapter, clock, request, seat="bot-04-sniper")
    assert exc_info.value.reason == "data_unavailable"
    assert _rejections(store) == [(stage, "data_unavailable")]
    assert "FillRecorded" not in _event_kinds(store)


async def test_bound_policy_calls_class_implementation_not_instance_attribute(
    tmp_path: Path,
) -> None:
    adapter, clock, store, curves = _replay_build(tmp_path)
    _rpc_reads(curves)
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    fill = await _place(adapter, clock, request, seat="bot-04-sniper")
    assert fill.filled_units > 0
    assert _rejections(store) == []


async def test_bound_policy_without_replay_token_refuses_fixture_buy(tmp_path: Path) -> None:
    """A policy built from the class alone grants no replay provenance: BUY is refused."""
    clock = FixtureClock(START)
    store = _store(tmp_path, "paper")
    source = ScriptedCurves([_snap("fixture")] * 3)
    adapter = PaperAdapter(
        store=store,
        risk=_engine(store, clock),
        ids=IdFactory(clock, make_rng(7)),
        clock=clock,
        rng=make_rng(7),
        budget=RiskBudget(),
        price_source=source,
        entry_policy=BoundEntryPolicy(source, supported=(ScriptedCurves,)),
        p_drop=0.0,
    )
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    with pytest.raises(OrderRejectedError) as exc_info:
        await _place(adapter, clock, request, seat="bot-04-sniper")
    assert exc_info.value.reason == "data_unavailable"
    assert _rejections(store) == [("ACCEPTED", "data_unavailable")]
    assert "FillRecorded" not in _event_kinds(store)


def test_replay_token_must_bind_the_policy_source(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    replay = replay_authority(tmp_path, clock, [tick(START, MINT, S0, T0)])
    other = ScriptedCurves([_snap("fixture")])
    with pytest.raises(ValueError, match="does not bind this source"):
        BoundEntryPolicy(
            other,  # type: ignore[arg-type]
            supported=(ScriptedCurves,),
            replay=replay,
        )


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
    adapter, clock, store, curves = _replay_build(tmp_path)
    buy = _request(adapter, TICKET, side=Side.BUY, units=None)
    bought = await _place(adapter, clock, buy, seat="bot-04-sniper")
    _rpc_reads(curves)
    sell = _request(adapter, TICKET, side=Side.SELL, units=bought.filled_units)
    sold = await _place(adapter, clock, sell, seat="bot-06-exit", exit_reason="stop_loss")
    assert sold.filled_units > 0
    assert _rejections(store) == []
