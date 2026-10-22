"""Greptile review regressions for the paper adapter.

Round 2 (findings 8, 10, 12, 13): one approval, one order; forced closes
credit proceeds; marks value every position; restart keeps the blind deadline.

Round 3 (findings 1, 8, 9, 14): a concurrent repeat must not release the
owner's probe; a flatten refuses a damaged ledger; emergency exits book their
venue and network fees; a buy fill is clipped to a CONFIRMING cap.

RISK-004: close_position is the kill-flatten exit on the forced-close path.
"""

from __future__ import annotations

import asyncio
import json
import random
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.core.adapter import Fill, OrderRequest, Side
from pumpgrok.core.approvals import parse_human_phrase, record_human_approval
from pumpgrok.core.errors import OrderRejectedError
from pumpgrok.core.idempotency import exec_place_key
from pumpgrok.core.ids import IdFactory
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.curve_math import sell_out
from pumpgrok.execution.fees import FeeModel
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.tools.risk.kill_switch import FlattenIntent, execute_flatten

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


def _mark(store: LedgerStore, clock: FixtureClock, mint: str, mtm: int, key: str) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        idempotency_key=key,
        type="MarkToMarket",
        payload={
            "source": "paper",
            "ts_source": format_ts_utc(clock.now()),
            "cash_lamports": EQUITY,
            "equity_lamports": EQUITY + mtm,
            "unrealized_lamports": mtm,
            "prices_json": json.dumps(
                {mint: {"mtm_lamports": mtm, "spot": "1", "source": "curve"}}
            ),
        },
    )


def _engine(store: LedgerStore, clock: FixtureClock) -> RiskEngine:
    return RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(52)),
        clock=clock,
        autonomy="autonomous-paper",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
        env={},
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


def _order(ids: IdFactory, mint: str, size: int = SIZE) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=mint,
        side=Side.BUY,
        decision_id=ids.ulid(),
        size_lamports=size,
        max_slippage_bps=100,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


async def _drive(clock: FixtureClock, *coros: Any) -> list[Any]:
    tasks = [asyncio.create_task(coro) for coro in coros]
    for _ in range(400):
        if all(task.done() for task in tasks):
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return list(await asyncio.gather(*tasks, return_exceptions=True))


def _tripped_engine(store: LedgerStore, clock: FixtureClock) -> RiskEngine:
    """Engine whose data_stale breaker is half-open: one probe may be admitted."""
    engine = _engine(store, clock)
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
    return engine


# -- round 2, finding 8: one approval, one order -------------------------


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


# -- round 2, finding 10: forced closes credit proceeds ------------------


async def test_graduation_close_credits_proceeds_to_cash(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        adapter = _adapter(store, clock, price_source=None)
        closed = await adapter.close_on_graduation(MINT, last_s=S0, last_t=T0, correlation_id="t")
        assert closed is not None
        gross = sell_out(S0, T0, UNITS)
        fees = FeeModel()
        proceeds = gross - fees.venue_fee(gross) - fees.network_cost()
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
        network = FeeModel().network_cost()
        assert adapter.cash_lamports() == EQUITY + last_good - network
        assert adapter.equity_lamports() == EQUITY + last_good - network
    finally:
        store.close()


# -- round 2, finding 12: a mark values every open position --------------


async def test_mark_values_other_open_positions(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, OTHER, OTHER_UNITS, OTHER_BASIS)
        _mark(store, clock, OTHER, OTHER_MTM, "mtm-other")
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


# -- round 2, finding 13: restart keeps the blind deadline ---------------


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
        assert body["proceeds_lamports"] == last_good - FeeModel().network_cost()
    finally:
        store.close()


# -- round 3, finding 1: a concurrent repeat must not release the owner's probe


async def test_concurrent_repeat_does_not_release_owner_probe(tmp_path: Path) -> None:
    """A retry of an in-flight decision must not reopen the breaker under its owner."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        engine = _tripped_engine(store, clock)
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
        request = _order(IdFactory(clock, random.Random(3)), MINT)
        results = await _drive(
            clock,
            adapter.place(request, seat="bot-04-sniper", correlation_id="test"),
            adapter.place(request, seat="bot-04-sniper", correlation_id="test"),
        )
        assert isinstance(results[0], Fill), results[0]
        assert isinstance(results[1], OrderRejectedError), results[1]
        assert len(store.read(types=["OrderPlaced"], limit=None)) == 1
        assert len(store.read(types=["FillRecorded"], limit=None)) == 1
    finally:
        store.close()


async def test_probe_released_after_order_outcome(tmp_path: Path) -> None:
    """A probe taken by a filled order is released, so a later order is not
    refused breaker_open forever."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        engine = _tripped_engine(store, clock)
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


# -- round 3, finding 8: a flatten refuses a damaged ledger --------------


async def test_flatten_refuses_a_damaged_ledger(tmp_path: Path) -> None:
    """A readable but hash-broken row must stop the flatten before any write."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    _seed_position(store, clock, MINT, UNITS, BASIS)
    path = tmp_path / "ledger.sqlite"
    store.close()
    raw = sqlite3.connect(path)
    raw.execute("DROP TRIGGER events_append_only_u")
    raw.execute(
        "UPDATE events SET payload_json = REPLACE(payload_json, 'TST', 'TSX')"
        " WHERE type = 'PositionOpened'"
    )
    raw.commit()
    raw.close()
    reopened = LedgerStore(str(path))
    try:
        adapter = _adapter(reopened, clock, price_source=_Fixed(_snap()))
        before = reopened.count()
        result = await adapter.close_position(mint=MINT, ticket_id=TICKET, reason="kill_flatten")
        assert result == {"status": "ledger_inconsistent", "mint": MINT}
        assert reopened.count() == before
    finally:
        reopened.close()


# -- round 3, finding 9: emergency exits book venue and network fees -----


async def test_kill_flatten_books_venue_and_network_fees(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        adapter = _adapter(store, clock, price_source=_Fixed(_snap()))
        fees = FeeModel()
        gross = sell_out(S0, T0, UNITS)
        venue = fees.venue_fee(gross)
        network = fees.network_cost()
        result = await adapter.close_position(mint=MINT, ticket_id=TICKET, reason="kill_flatten")
        assert result["status"] == "closed"
        assert result["proceeds_lamports"] == gross - venue - network
        fills = store.read(types=["FillRecorded"], limit=None)
        assert len(fills) == 1
        body = fills[0]["payload"]
        assert body["venue_fee_lamports"] == venue
        assert body["network_cost_lamports"] == network
        assert body["cash_delta_lamports"] == gross - venue - network
        assert adapter.cash_lamports() == EQUITY + gross - venue - network
        assert adapter._fold_state().counters.fees_today_lamports == venue + network
    finally:
        store.close()


# -- round 3, finding 14: a buy fill is clipped to a smaller CONFIRMING cap


async def test_buy_fill_is_clipped_to_confirming_cap(tmp_path: Path) -> None:
    """Equity falls during the wait, so the recheck cap (0.2 SOL) is below the
    requested 0.201 SOL. The fill must not exceed the recomputed cap."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, OTHER, OTHER_UNITS, OTHER_BASIS)
        _mark(store, clock, OTHER, 100_000_000, "mtm-other-high")
        adapter = _adapter(store, clock, price_source=_Fixed(_snap()))
        request = _order(IdFactory(clock, random.Random(4)), MINT, size=201_000_000)
        placed_key = exec_place_key(TICKET, "buy", request.decision_id)
        task = asyncio.create_task(adapter.place(request, seat="bot-04-sniper", correlation_id="t"))
        shrunk = False
        for _ in range(400):
            if task.done():
                break
            if not shrunk and store.by_key(placed_key) is not None:
                _mark(store, clock, OTHER, 0, "mtm-other-zero")
                shrunk = True
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        fill = await task
        assert shrunk
        assert fill.filled_lamports == 200_000_000
        assert fill.status.value == "partial"
    finally:
        store.close()


# -- RISK-004: kill_flatten closes through the forced-close path ---------


async def test_close_position_kill_flatten_writes_one_sell_and_one_close(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        adapter = _adapter(store, clock, price_source=_Fixed(_snap()))
        result = await adapter.close_position(mint=MINT, ticket_id=TICKET, reason="kill_flatten")
        gross = sell_out(S0, T0, UNITS)
        fees = FeeModel()
        proceeds = gross - fees.venue_fee(gross) - fees.network_cost()
        assert result["status"] == "closed"
        assert result["proceeds_lamports"] == proceeds
        fills = store.read(types=["FillRecorded"], limit=None)
        assert len(fills) == 1
        assert fills[0]["payload"]["side"] == "sell"
        assert fills[0]["payload"]["cash_delta_lamports"] == proceeds
        assert fills[0]["payload"]["filled_units"] == UNITS
        closes = store.read(types=["PositionClosed"], limit=None)
        assert len(closes) == 1
        assert closes[0]["payload"]["reason"] == "kill_flatten"
        assert closes[0]["payload"]["proceeds_lamports"] == proceeds
        assert adapter.cash_lamports() == EQUITY + proceeds
    finally:
        store.close()


async def test_close_position_without_position_returns_no_position_and_writes_nothing(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        adapter = _adapter(store, clock, price_source=_Fixed(_snap()))
        before = store.count()
        result = await adapter.close_position(mint=MINT, ticket_id=TICKET, reason="kill_flatten")
        assert result == {"status": "no_position", "mint": MINT}
        assert store.count() == before
    finally:
        store.close()


async def test_close_position_without_any_value_refuses_without_writes(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        adapter = _adapter(store, clock, price_source=None)
        before = store.count()
        result = await adapter.close_position(mint=MINT, ticket_id=TICKET, reason="kill_flatten")
        assert result == {"status": "no_mark", "mint": MINT}
        assert store.count() == before
    finally:
        store.close()


# -- PR6 round 3 finding 7: shared barrier and commit-time holding -------


def _sell(ids: IdFactory, units: int) -> OrderRequest:
    return OrderRequest(
        ticket_id=TICKET,
        mint=MINT,
        side=Side.SELL,
        decision_id=ids.ulid(),
        token_units=units,
        max_slippage_bps=100,
        approval_id=f"apr-{ids.ulid()}",
        correlation_id="test",
    )


async def test_inflight_barrier_tracks_order_until_settled(tmp_path: Path) -> None:
    """The adapter exposes its in-flight barrier; an order is in it until it settles."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        adapter = _adapter(store, clock, price_source=_Fixed(_snap()))
        barrier = adapter.inflight_barrier
        assert len(barrier) == 0
        ids = IdFactory(clock, make_rng(11))
        task = asyncio.create_task(
            adapter.place(_order(ids, MINT), seat="bot-04-sniper", correlation_id="test")
        )
        seen: list[int] = []
        for _ in range(400):
            if task.done():
                break
            seen.append(len(barrier))
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        assert isinstance(await task, Fill)
        assert 1 in seen
        assert len(barrier) == 0
    finally:
        store.close()


async def test_overlapping_exit_sells_cannot_oversell_holding(tmp_path: Path) -> None:
    """Two exits sized from the same holding: the second is refused, no second fill."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        _mark(store, clock, MINT, BASIS, "mtm-seed-exit")
        adapter = _adapter(store, clock, price_source=_Yielding(_snap()))
        ids = IdFactory(clock, make_rng(12))
        part = UNITS * 3 // 4
        results = await _drive(
            clock,
            adapter.place(_sell(ids, part), seat="bot-06-exit", correlation_id="test"),
            adapter.place(_sell(ids, part), seat="bot-06-exit", correlation_id="test"),
        )
        fills = [r for r in results if isinstance(r, Fill)]
        refused = [r for r in results if isinstance(r, OrderRejectedError)]
        assert len(fills) == 1, results
        assert len(refused) == 1, results
        assert refused[0].reason == "no_position"
        sold = [
            e["payload"]["filled_units"] for e in store.read(types=["FillRecorded"], limit=None)
        ]
        assert sold == [part]
        assert adapter._fold_state().positions[MINT].token_units == UNITS - part
    finally:
        store.close()


async def test_sell_refused_when_flatten_closed_holding_during_confirmation(
    tmp_path: Path,
) -> None:
    """A flatten that closes the holding while an exit sell sleeps leaves one fill."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        _seed_position(store, clock, MINT, UNITS, BASIS)
        _mark(store, clock, MINT, BASIS, "mtm-seed-flatten")
        adapter = _adapter(store, clock, price_source=_Yielding(_snap()))
        ids = IdFactory(clock, make_rng(13))
        request = _sell(ids, UNITS)
        placed_key = exec_place_key(TICKET, "sell", request.decision_id)
        task = asyncio.create_task(
            adapter.place(request, seat="bot-06-exit", correlation_id="test")
        )
        flattened = False
        for _ in range(400):
            if task.done():
                break
            if not flattened and store.by_key(placed_key) is not None:
                closed = await adapter.close_position(
                    mint=MINT, ticket_id=TICKET, reason="kill_flatten"
                )
                assert closed["status"] == "closed"
                flattened = True
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        with pytest.raises(OrderRejectedError) as excinfo:
            await task
        assert excinfo.value.reason == "no_position"
        assert len(store.read(types=["FillRecorded"], limit=None)) == 1
        assert flattened
    finally:
        store.close()


async def test_flatten_waits_for_in_flight_order_before_closing(tmp_path: Path) -> None:
    """A flatten started while a buy is in flight closes the position that buy opens."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        adapter = _adapter(store, clock, price_source=_Fixed(_snap()))
        ids = IdFactory(clock, make_rng(14))
        fills_seen: list[int] = []

        def intents() -> list[FlattenIntent]:
            # Called only after the barrier is idle, so the buy's fill is on the ledger.
            fills_seen.append(len(store.read(types=["FillRecorded"], limit=None)))
            return [
                FlattenIntent(mint=pos.mint, ticket_id=TICKET, token_units=pos.token_units)
                for pos in adapter._fold_state().positions.values()
                if pos.token_units > 0
            ]

        async def flatten() -> Any:
            return await execute_flatten(
                intents,
                barrier=adapter.inflight_barrier,
                close_position=adapter.close_position,
            )

        results = await _drive(
            clock,
            adapter.place(_order(ids, MINT), seat="bot-04-sniper", correlation_id="test"),
            flatten(),
        )
        assert isinstance(results[0], Fill), results[0]
        assert fills_seen == [1]
        assert [o.status for o in results[1].outcomes] == ["closed"]
        assert adapter._fold_state().positions.get(MINT) is None
        assert len(store.read(types=["PositionClosed"], limit=None)) == 1
    finally:
        store.close()


# -- PR6 round 5: barrier ownership is per call, cleanup on every exit path --


class _BlockOnReads:
    """Answers each curve read at once unless its 1-based number is in ``block_on``."""

    def __init__(self, snap: CurveSnapshot, block_on: set[int]) -> None:
        self._snap = snap
        self._block_on = block_on
        self.reads = 0
        self.gate = asyncio.Event()

    async def curve(self, mint: str) -> CurveSnapshot | None:
        self.reads += 1
        if self.reads in self._block_on:
            await self.gate.wait()
        return self._snap


async def _pair_at_confirmation(
    adapter: PaperAdapter, clock: FixtureClock, source: _BlockOnReads, request: OrderRequest
) -> tuple[asyncio.Task[Fill], asyncio.Task[Fill]]:
    """Start an owner call (blocked on its decision read), then a same-key retry
    that reaches its own confirmation read (read 3) and blocks there."""
    first = asyncio.create_task(adapter.place(request, seat="bot-04-sniper", correlation_id="test"))
    for _ in range(50):
        await asyncio.sleep(0)
    retry = asyncio.create_task(adapter.place(request, seat="bot-04-sniper", correlation_id="test"))
    for _ in range(400):
        if source.reads >= 3:
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    assert source.reads == 3
    return first, retry


async def test_cancelled_place_during_confirmation_read_clears_barrier(tmp_path: Path) -> None:
    """(a) Cancel a place() waiting on its confirmation curve read: flatten must not wait on it."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        source = _BlockOnReads(_snap(), block_on={2})
        adapter = _adapter(store, clock, price_source=source)
        ids = IdFactory(clock, make_rng(16))
        task = asyncio.create_task(
            adapter.place(_order(ids, MINT), seat="bot-04-sniper", correlation_id="test")
        )
        for _ in range(400):
            if source.reads >= 2:
                break
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        assert len(adapter.inflight_barrier) == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(adapter.inflight_barrier) == 0
        assert adapter.inflight_barrier.wait_empty(timeout_s=0.01) is True
    finally:
        store.close()


async def test_cancelled_retry_clears_only_its_own_barrier_entry(tmp_path: Path) -> None:
    """(c) A cancelled same-key retry removes its own order and leaves nothing behind."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        source = _BlockOnReads(_snap(), block_on={1, 3})
        adapter = _adapter(store, clock, price_source=source)
        request = _order(IdFactory(clock, make_rng(17)), MINT)
        first, retry = await _pair_at_confirmation(adapter, clock, source, request)
        assert len(adapter.inflight_barrier) == 1
        retry.cancel()
        with pytest.raises(asyncio.CancelledError):
            await retry
        assert len(adapter.inflight_barrier) == 0
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert len(adapter.inflight_barrier) == 0
    finally:
        store.close()


async def test_cancelled_owner_does_not_remove_retry_order(tmp_path: Path) -> None:
    """(b) Start a same-key retry, cancel the first call: the retry stays registered.

    The retry keeps its own barrier entry, and flatten waits for it.
    """
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        source = _BlockOnReads(_snap(), block_on={1, 3})
        adapter = _adapter(store, clock, price_source=source)
        request = _order(IdFactory(clock, make_rng(18)), MINT)
        first, retry = await _pair_at_confirmation(adapter, clock, source, request)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert len(adapter.inflight_barrier) == 1
        assert adapter.inflight_barrier.wait_empty(timeout_s=0.01) is False
        source.gate.set()
        for _ in range(400):
            if retry.done():
                break
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        assert isinstance(await retry, Fill)
        assert len(adapter.inflight_barrier) == 0
    finally:
        store.close()


# -- PR6 round 4 finding 2: an aborted order must not block flatten -------


class _AbortsOnConfirm:
    """Answers the decision-time read, then fails the CONFIRMING re-read."""

    def __init__(self, snap: CurveSnapshot) -> None:
        self._snap = snap
        self._reads = 0

    async def curve(self, mint: str) -> CurveSnapshot | None:
        self._reads += 1
        if self._reads > 1:
            raise RuntimeError("curve feed failed during confirmation")
        return self._snap


async def test_aborted_order_clears_barrier_so_flatten_does_not_wait(tmp_path: Path) -> None:
    """An order that dies between ACCEPTED and settlement leaves no barrier entry."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        adapter = _adapter(store, clock, price_source=_AbortsOnConfirm(_snap()))
        ids = IdFactory(clock, make_rng(15))
        results = await _drive(
            clock,
            adapter.place(_order(ids, MINT), seat="bot-04-sniper", correlation_id="test"),
        )
        assert isinstance(results[0], RuntimeError), results[0]
        assert len(adapter.inflight_barrier) == 0
        assert adapter.inflight_barrier.wait_empty(timeout_s=0.01) is True
    finally:
        store.close()


# -- PR6 round 5 follow-up: a failed owner must not release the retry's probe --


async def test_owner_failure_after_retry_keeps_retry_probe(tmp_path: Path) -> None:
    """Owner stalls before its batch write; a same-key retry places the order and holds
    the admitted probe; the owner then fails with in_flight. The retry's probe must stay
    held, so the retry fills and a third order is still refused by the probe."""
    clock = FixtureClock(start=START)
    store = _store(tmp_path)
    try:
        engine = _tripped_engine(store, clock)
        source = _BlockOnReads(_snap(), block_on={1})
        adapter = PaperAdapter(
            store=store,
            risk=engine,
            ids=IdFactory(clock, make_rng(41)),
            clock=clock,
            rng=make_rng(41),
            budget=RiskBudget(),
            price_source=source,
            p_drop=0.0,
        )
        request = _order(IdFactory(clock, random.Random(19)), MINT)
        owner = asyncio.create_task(
            adapter.place(request, seat="bot-04-sniper", correlation_id="test")
        )
        for _ in range(50):
            await asyncio.sleep(0)
        assert source.reads == 1
        retry = asyncio.create_task(
            adapter.place(request, seat="bot-04-sniper", correlation_id="test")
        )
        for _ in range(50):
            await asyncio.sleep(0)
        assert source.reads == 2
        assert len(adapter.inflight_barrier) == 1
        assert len(store.read(types=["OrderPlaced"], limit=None)) == 1

        source.gate.set()
        for _ in range(50):
            await asyncio.sleep(0)
        assert owner.done()
        with pytest.raises(OrderRejectedError) as owner_exc:
            await owner
        assert owner_exc.value.reason == "in_flight"

        probe_blocked = engine.check(_order(IdFactory(clock, random.Random(20)), OTHER))
        assert probe_blocked.passed is False
        assert probe_blocked.reason == "breaker_open"

        for _ in range(400):
            if retry.done():
                break
            clock.advance_to(clock.now() + 1.0)
            await asyncio.sleep(0)
        fill = await retry
        assert isinstance(fill, Fill)
        assert len(store.read(types=["FillRecorded"], limit=None)) == 1
    finally:
        store.close()
