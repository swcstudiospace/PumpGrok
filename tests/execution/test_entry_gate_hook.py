"""Production entry policy: BUY reads are bound to one source object at both stages.

Direct-constructor adapters keep their existing behaviour; the policy slot is only
consulted when a policy is installed. Sells never consult it.
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


class DenyingEntryPolicy:
    """Test-owned policy: admits every source, refuses every entry snapshot."""

    def check_source(self, source: object | None) -> str | None:
        return None

    def check_snapshot(self, snapshot: CurveSnapshot) -> str | None:
        return "test policy denies entry"


def _snap(source: str) -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0, source=source)


def _harness(tmp_path: Path, reads: list[CurveSnapshot]) -> tuple[PaperAdapter, FixtureClock]:
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
    adapter = PaperAdapter(
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(7),
        budget=RiskBudget(),
        price_source=ScriptedCurves(reads),
        p_drop=0.0,
    )
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


async def test_installed_entry_policy_denies_buy_before_fill(tmp_path: Path) -> None:
    """RED: the adapter ignores the policy slot, so a fixture BUY that every other gate admits fills."""
    adapter, clock = _harness(tmp_path, [_snap("fixture")] * 3)
    adapter._entry_policy = DenyingEntryPolicy()  # type: ignore[attr-defined]
    request = _request(adapter, TICKET, side=Side.BUY, units=None)
    try:
        await _place(adapter, clock, request, seat="bot-04-sniper")
    except OrderRejectedError as exc:
        assert exc.reason == "data_unavailable"
    kinds = [event["type"] for event in adapter._store.read(limit=None)]
    assert "FillRecorded" not in kinds
