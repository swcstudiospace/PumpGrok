"""Greptile review regressions for the paper adapter (findings 8, 10, 12, 13).

8:  one approval consumed by overlapping orders must yield exactly one order.
10: forced closes (graduation, blind flatten) must credit proceeds to cash.
12: a mark must value every open position, not only the marked mint.
13: a restarted adapter must honour the blind-close deadline from the ledger.
"""

from __future__ import annotations

import asyncio
import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.approvals import parse_human_phrase, record_human_approval
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.curve_math import sell_out
from pumpgrok.execution.fees import FeeModel
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine

START = 1_769_900_000.0
EQUITY = 10_000_000_000
TICKET = "SOL-20260201-001"
MINT = "So11111111111111111111111111111111111111112"
OTHER = "So22222222222222222222222222222222222222222"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
UNITS = 3_000_000
BASIS = 200_000_000
SIZE = 200_000_000
OTHER_UNITS = 1_000_000
OTHER_BASIS = 50_000_000
OTHER_MTM = 61_000_000
DATA_STALE_COOLDOWN_S = 60.0


def _store(tmp_path: Path) -> LedgerStore:
    path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(path)
    store = LedgerStore(str(path))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _seed_position(
    store: LedgerStore, clock: FixtureClock, mint: str, units: int, basis: int
) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=f"pos-{mint}",
        type="PositionOpened",
        payload={
            "source": "paper",
            "mint": mint,
            "price_entry": "0.00001",
            "token_units": units,
            "cost_basis_lamports": basis,
            "opened_ts_utc": format_ts_utc(clock.now()),
            "symbol": "TST",
            "creator": "Creator1111111111111111111111111111111111",
            "ticket_id": TICKET,
            "score": "0.8",
        },
    )


def _adapter(
    store: LedgerStore,
    clock: FixtureClock,
    *,
    price_source: Any,
    autonomy: str = "autonomous-paper",
) -> PaperAdapter:
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(52)),
        clock=clock,
        autonomy=autonomy,  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
        env={},
    )
    return PaperAdapter(
        store=store,
        risk=engine,
        ids=IdFactory(clock, make_rng(52)),
        clock=clock,
        rng=make_rng(52),
        budget=RiskBudget(),
        price_source=price_source,
        p_drop=0.0,
    )


class _Fixed:
    """Curve source that answers immediately with one snapshot."""

    def __init__(self, snap: CurveSnapshot) -> None:
        self._snap = snap

    async def curve(self, mint: str) -> CurveSnapshot | None:
        return self._snap


class _Yielding:
    """Curve source that yields to the loop before answering (live RPC shape)."""

    def __init__(self, snap: CurveSnapshot) -> None:
        self._snap = snap

    async def curve(self, mint: str) -> CurveSnapshot | None:
        await asyncio.sleep(0)
        return self._snap


def _snap() -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0)


async def _drive(clock: FixtureClock, *coros: Any) -> list[Any]:
    tasks = [asyncio.create_task(coro) for coro in coros]
    for _ in range(400):
        if all(task.done() for task in tasks):
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return list(await asyncio.gather(*tasks, return_exceptions=True))


# -- finding 8: one approval, one order ----------------------------------


async def test_overlapping_orders_consume_one_approval_once(tmp_path: Path) -> None:
    """Two orders racing on one approval: the loser is refused, one OrderPlaced."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(7))
        adapter = _adapter(store, clock, price_source=_Yielding(_snap()), autonomy="manual-ticket")
        approval_id = f"apr-{ids.ulid()}"
        record = parse_human_phrase(
            f"approve {TICKET} {MINT} 0.2 100",
            kind="human_buy",
            by="human:alice",
            approval_id=approval_id,
            at=datetime.fromtimestamp(clock.now(), UTC),
        )
        record_human_approval(
            store, record, ts_utc=format_ts_utc(clock.now()), source="paper", correlation_id="test"
        )

        def order(decision_id: str) -> OrderRequest:
            return OrderRequest(
                ticket_id=TICKET,
                mint=MINT,
                side=Side.BUY,
                decision_id=decision_id,
                size_lamports=SIZE,
                max_slippage_bps=100,
                approval_id=approval_id,
                correlation_id="test",
            )

        results = await _drive(
            clock,
            adapter.place(order(ids.ulid()), seat="bot-04-sniper", correlation_id="test"),
            adapter.place(order(ids.ulid()), seat="bot-04-sniper", correlation_id="test"),
        )
        fills = [r for r in results if isinstance(r, Fill)]
        refused = [r for r in results if isinstance(r, OrderRejectedError)]
        assert len(fills) == 1
        assert len(refused) == 1
        assert refused[0].reason == "approval_missing"
        assert len(store.read(types=["OrderPlaced"], limit=None)) == 1
        consumed = [
            row
            for row in store.read(types=["ApprovalRecorded"], limit=None)
            if row["payload"].get("consumed") is True
        ]
        assert len(consumed) == 1
        assert len(store.read(types=["FillRecorded"], limit=None)) == 1
    finally:
        store.close()


# -- finding 10: forced closes credit proceeds ---------------------------


async def test_graduation_close_credits_proceeds_to_cash(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        adapter = _adapter(store, clock, price_source=None)
        closed = await adapter.close_on_graduation(MINT, last_s=S0, last_t=T0, correlation_id="t")
        assert closed is not None
        gross = sell_out(S0, T0, UNITS)
        proceeds = gross - FeeModel().venue_fee(gross)
        assert adapter.cash_lamports() == EQUITY + proceeds
        assert adapter.equity_lamports() == EQUITY + proceeds
        fills = store.read(types=["FillRecorded"], limit=None)
        assert len(fills) == 1
        body = fills[0]["payload"]
        assert body["side"] == "sell"
        assert body["mint"] == MINT
        assert body["cash_delta_lamports"] == proceeds
        assert body["filled_units"] == UNITS
    finally:
        store.close()


async def test_blind_close_credits_last_good_to_cash(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        adapter = _adapter(store, clock, price_source=_Fixed(_snap()))
        marked = await adapter.mark_to_market(MINT, correlation_id="t")
        assert marked is not None
        last_good = int(json.loads(str(marked["payload_json"]))["equity_lamports"]) - EQUITY
        clock.advance_to(clock.now() + 301.0)
        closed = await adapter.check_blind(MINT, correlation_id="t")
        assert closed is not None
        assert adapter.cash_lamports() == EQUITY + last_good
        assert adapter.equity_lamports() == EQUITY + last_good
    finally:
        store.close()


# -- finding 12: a mark values every open position -----------------------


async def test_mark_values_other_open_positions(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, OTHER, OTHER_UNITS, OTHER_BASIS)
        store.append(
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
            idempotency_key="mtm-other",
            type="MarkToMarket",
            payload={
                "source": "paper",
                "ts_source": format_ts_utc(clock.now()),
                "cash_lamports": EQUITY,
                "equity_lamports": EQUITY + OTHER_MTM,
                "unrealized_lamports": OTHER_MTM - OTHER_BASIS,
                "prices_json": json.dumps(
                    {OTHER: {"mtm_lamports": OTHER_MTM, "spot": "1", "source": "curve"}}
                ),
            },
        )
        _seed_position(store, clock, MINT, UNITS, BASIS)
        adapter = _adapter(store, clock, price_source=_Fixed(_snap()))
        row = await adapter.mark_to_market(MINT, correlation_id="t")
        assert row is not None
        body = json.loads(str(row["payload_json"]))
        gross = sell_out(S0, T0, UNITS)
        mint_mtm = gross - FeeModel().venue_fee(gross)
        assert body["equity_lamports"] == EQUITY + mint_mtm + OTHER_MTM
        assert body["unrealized_lamports"] == (mint_mtm + OTHER_MTM) - (BASIS + OTHER_BASIS)
        assert adapter.equity_lamports() == body["equity_lamports"]
    finally:
        store.close()


# -- finding 13: restart keeps the blind deadline ------------------------


async def test_restarted_adapter_blind_closes_at_deadline(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        first = _adapter(store, clock, price_source=_Fixed(_snap()))
        marked = await first.mark_to_market(MINT, correlation_id="t")
        assert marked is not None
        last_good = int(json.loads(str(marked["payload_json"]))["equity_lamports"]) - EQUITY
        restarted = _adapter(store, clock, price_source=None)
        clock.advance_to(clock.now() + 299.0)
        assert await restarted.check_blind(MINT, correlation_id="t") is None
        clock.advance_to(clock.now() + 2.0)
        closed = await restarted.check_blind(MINT, correlation_id="t")
        assert closed is not None
        body = json.loads(str(closed["payload_json"]))
        assert body["reason"] == "blind_flatten"
        assert body["proceeds_lamports"] == last_good
    finally:
        store.close()


# -- probe release: a probe admitted to an order is released at its outcome --


async def test_probe_released_after_order_outcome(tmp_path: Path) -> None:
    """A probe taken by a filled order is released, so a later order is not
    refused breaker_open forever."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        engine = RiskEngine(
            store=store,
            budget=RiskBudget(),
            ids=IdFactory(clock, random.Random(41)),
            clock=clock,
            autonomy="autonomous-paper",  # type: ignore[arg-type]
            get_reserves=lambda _mint: (S0, T0),
            env={},
        )
        for _ in range(3):
            engine.note_miss(
                clock.now(),
                ts_utc=format_ts_utc(clock.now()),
                source="paper",
                correlation_id="test",
            )
        probe_ids = IdFactory(clock, random.Random(1))
        assert engine.check(_order(probe_ids, OTHER)).passed is False
        clock.advance_to(clock.now() + DATA_STALE_COOLDOWN_S + 1.0)
        adapter = PaperAdapter(
            store=store,
            risk=engine,
            ids=IdFactory(clock, make_rng(41)),
            clock=clock,
            rng=make_rng(41),
            budget=RiskBudget(),
            price_source=_Fixed(_snap()),
            p_drop=0.0,
        )
        ids = IdFactory(clock, random.Random(2))
        first = await _drive(clock, adapter.place(_order(ids, MINT), seat="bot-04-sniper"))
        assert isinstance(first[0], Fill), first[0]
        marked = await adapter.mark_to_market(MINT, correlation_id="test")
        assert marked is not None
        second = await _drive(clock, adapter.place(_order(ids, OTHER), seat="bot-04-sniper"))
        assert isinstance(second[0], Fill), second[0]
    finally:
        store.close()


def _order(ids: IdFactory, mint: str) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=mint,
        side=Side.BUY,
        decision_id=ids.ulid(),
        size_lamports=SIZE,
        max_slippage_bps=100,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )
