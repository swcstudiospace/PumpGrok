"""Tickets, approvals, and atomic consume-and-order (PAPER-007, TOOL-004, R64).

Ticket ids allocate as SOL-YYYYMMDD-NNN with per-day sequencing; a human
buy needs a token-for-token phrase; approval consumption and OrderPlaced
commit in one ledger transaction; a repeated decision returns the first
Fill; unknown approval ids fail closed with no OrderPlaced row.
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.core.approvals import (
    ApprovalRecord,
    parse_human_phrase,
    record_human_approval,
)
from pumpgrok.core.errors import PermissionDenied
from pumpgrok.core.ids import IdFactory, bind_calling_seat
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.tickets import allocate_ticket, day_ticket_count
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.risk.limits import EngineLimits
from pumpgrok.tools.exec.cancel import CancelIn, run_cancel
from pumpgrok.tools.exec.place import PlaceIn, run_place
from pumpgrok.tools.exec.positions import PositionsIn, run_positions

START = 1_769_900_000.0
EQUITY = 10_000_000_000
MINT = "So11111111111111111111111111111111111111112"
OTHER_MINT = "So22222222222222222222222222222222222222222"
S0 = 42_000_000_000
T0 = 766_428_571_428_571
SIZE = 200_000_000
SEAT = "bot-04-sniper"


class ScriptedCurves:
    """Pop one scripted snapshot per read; hold the last."""

    def __init__(self, reads: list[CurveSnapshot]) -> None:
        self._reads = list(reads)

    async def curve(self, mint: str) -> CurveSnapshot | None:
        if len(self._reads) > 1:
            return self._reads.pop(0)
        return self._reads[0]


def _snap() -> CurveSnapshot:
    return CurveSnapshot(mint=MINT, s_lamports=S0, t_units=T0)


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    store.set_meta("initial_equity_lamports", str(EQUITY))
    store.set_meta("source", "paper")
    return store


def _harness(
    tmp_path: Path,
    *,
    seed: int = 7,
    autonomy: str = "manual-ticket",
    limits: EngineLimits | None = None,
    reads: list[CurveSnapshot] | None = None,
) -> tuple[PaperAdapter, FixtureClock, RiskEngine, IdFactory, LedgerStore]:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    ids = IdFactory(clock, make_rng(seed))
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(seed)),
        clock=clock,
        autonomy=autonomy,  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    adapter = PaperAdapter(
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(seed),
        budget=RiskBudget(),
        limits=limits,
        price_source=ScriptedCurves(reads if reads is not None else [_snap(), _snap()]),
        p_drop=0.0,
    )
    return adapter, clock, engine, ids, store


def _approve(
    store: LedgerStore,
    clock: FixtureClock,
    ids: IdFactory,
    ticket_id: str,
    phrase_size_sol: str = "0.2",
    *,
    kind: str = "human_buy",
    mint: str = MINT,
) -> str:
    approval_id = f"apr-{ids.ulid()}"
    record = parse_human_phrase(
        f"approve {ticket_id} {mint} {phrase_size_sol} 100",
        kind=kind,  # type: ignore[arg-type]
        by="human:alice",
        approval_id=approval_id,
        at=datetime.fromtimestamp(clock.now(), UTC),
    )
    record_human_approval(
        store,
        record,
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
    )
    return approval_id


def _buy_in(ticket_id: str, decision_id: str, approval_id: str, *, mint: str = MINT) -> PlaceIn:
    return PlaceIn.model_validate(
        {
            "ticket_id": ticket_id,
            "mint": mint,
            "side": "buy",
            "decision_id": decision_id,
            "size_lamports": SIZE,
            "max_slippage_bps": 100,
            "approval_id": approval_id,
        }
    )


async def _drive(coro: Any, clock: FixtureClock) -> Any:
    task = asyncio.create_task(coro)
    for _ in range(400):
        if task.done():
            break
        clock.advance_to(clock.now() + 1.0)
        await asyncio.sleep(0)
    return await task


def _placed(store: LedgerStore) -> list[dict[str, Any]]:
    return [e for e in store.read(limit=None) if e["type"] == "OrderPlaced"]


def test_ticket_ids_sequence_per_day(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        ts = format_ts_utc(clock.now())
        day = ts[:10].replace("-", "")
        first = allocate_ticket(
            store, ts_utc=ts, source="paper", correlation_id="t", seat=SEAT, title="lead"
        )
        second = allocate_ticket(
            store, ts_utc=ts, source="paper", correlation_id="t", seat=SEAT, title="lead"
        )
        assert first == f"SOL-{day}-001"
        assert second == f"SOL-{day}-002"
        assert day_ticket_count(store, day) == 2
        notes = [e for e in store.read(limit=None) if e["type"] == "JournalNote"]
        assert len(notes) == 2
        assert notes[0]["payload"]["note_kind"] == "ticket"
        assert notes[0]["payload"]["refs"] == [first]
        assert notes[0]["payload"]["seat"] == SEAT
    finally:
        store.close()


def test_ticket_ids_restart_each_day(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        day_one = format_ts_utc(clock.now())
        clock.advance_to(clock.now() + 86_400.0)
        day_two = format_ts_utc(clock.now())
        assert day_one[:10] != day_two[:10]
        first = allocate_ticket(
            store, ts_utc=day_one, source="paper", correlation_id="t", seat=SEAT, title="a"
        )
        second = allocate_ticket(
            store, ts_utc=day_two, source="paper", correlation_id="t", seat=SEAT, title="b"
        )
        assert first == f"SOL-{day_one[:10].replace('-', '')}-001"
        assert second == f"SOL-{day_two[:10].replace('-', '')}-001"
    finally:
        store.close()


def test_approval_kinds_are_exactly_seven() -> None:
    kinds = get_args(ApprovalRecord.model_fields["kind"].annotation)
    assert sorted(kinds) == sorted(
        [
            "human_buy",
            "human_sell",
            "exit_rule",
            "autonomous_paper",
            "killswitch_clear",
            "halt_clear",
            "live_gate",
        ]
    )


def test_phrase_parses_token_for_token(tmp_path: Path) -> None:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    try:
        ids = IdFactory(clock, make_rng(3))
        approval_id = f"apr-{ids.ulid()}"
        record = parse_human_phrase(
            f"approve SOL-20260201-001 {MINT} 0.2 100",
            kind="human_buy",
            by="human:alice",
            approval_id=approval_id,
            at=datetime.fromtimestamp(clock.now(), UTC),
        )
        assert record.ticket_id == "SOL-20260201-001"
        assert record.size_lamports == SIZE
        assert record.max_slippage_bps == 100
        row = record_human_approval(
            store,
            record,
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
        )
        assert row["type"] == "ApprovalRecorded"
        assert json.loads(row["payload_json"])["consumed"] is False
        with pytest.raises(ValueError, match="five whitespace"):
            parse_human_phrase(
                "approve SOL-20260201-001 0.2 100",
                kind="human_buy",
                by="human:alice",
                approval_id=approval_id,
                at=datetime.fromtimestamp(clock.now(), UTC),
            )
        with pytest.raises(ValueError, match="ticket"):
            parse_human_phrase(
                f"approve SOL-9999 {MINT} 0.2 100",
                kind="human_buy",
                by="human:alice",
                approval_id=approval_id,
                at=datetime.fromtimestamp(clock.now(), UTC),
            )
    finally:
        store.close()


async def test_paper_buy_atomic_consume_and_order(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path)
    try:
        ticket_id = allocate_ticket(
            store,
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
            seat=SEAT,
            title="lead",
        )
        approval_id = _approve(store, clock, ids, ticket_id)
        decision_id = ids.ulid()
        with bind_calling_seat(SEAT):
            out = await _drive(
                run_place(_buy_in(ticket_id, decision_id, approval_id), adapter, RiskBudget, clock),
                clock,
            )
        assert out["status"] == "filled", out
        placed = _placed(store)
        assert len(placed) == 1
        consumes = [
            e
            for e in store.read(limit=None)
            if e["type"] == "ApprovalRecorded" and e["payload"].get("consumed") is True
        ]
        assert len(consumes) == 1
        assert consumes[0]["payload"]["id"] == approval_id
        with bind_calling_seat(SEAT):
            repeat = await _drive(
                run_place(_buy_in(ticket_id, decision_id, approval_id), adapter, RiskBudget, clock),
                clock,
            )
        assert repeat["status"] == "filled", repeat
        assert len(_placed(store)) == 1
    finally:
        store.close()


async def test_consumed_approval_fails_closed_on_reuse(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path)
    try:
        ticket_id = allocate_ticket(
            store,
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
            seat=SEAT,
            title="lead",
        )
        approval_id = _approve(store, clock, ids, ticket_id)
        with bind_calling_seat(SEAT):
            first = await _drive(
                run_place(_buy_in(ticket_id, ids.ulid(), approval_id), adapter, RiskBudget, clock),
                clock,
            )
        assert first["status"] == "filled", first
        with bind_calling_seat(SEAT):
            second = await _drive(
                run_place(_buy_in(ticket_id, ids.ulid(), approval_id), adapter, RiskBudget, clock),
                clock,
            )
        assert second["status"] == "rejected"
        assert second["reason"] == "approval_missing"
        assert len(_placed(store)) == 1
    finally:
        store.close()


async def test_phrase_mismatch_rejects_approval_mismatch(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path)
    try:
        ticket_id = allocate_ticket(
            store,
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
            seat=SEAT,
            title="lead",
        )
        approval_id = _approve(store, clock, ids, ticket_id, phrase_size_sol="0.5")
        with bind_calling_seat(SEAT):
            out = await _drive(
                run_place(_buy_in(ticket_id, ids.ulid(), approval_id), adapter, RiskBudget, clock),
                clock,
            )
        assert out["status"] == "rejected"
        assert out["reason"] == "approval_mismatch"
        assert _placed(store) == []
    finally:
        store.close()


async def test_unknown_approval_id_fails_closed(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path)
    try:
        ticket_id = allocate_ticket(
            store,
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
            seat=SEAT,
            title="lead",
        )
        with bind_calling_seat(SEAT):
            out = await _drive(
                run_place(
                    _buy_in(ticket_id, ids.ulid(), f"apr-{ids.ulid()}"),
                    adapter,
                    RiskBudget,
                    clock,
                ),
                clock,
            )
        assert out["status"] == "rejected"
        assert out["reason"] == "approval_missing"
        assert _placed(store) == []
    finally:
        store.close()


async def test_wrong_ticket_approval_fails_closed(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path)
    try:
        ticket_id = allocate_ticket(
            store,
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
            seat=SEAT,
            title="lead",
        )
        other = allocate_ticket(
            store,
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="test",
            seat=SEAT,
            title="other",
        )
        approval_id = _approve(store, clock, ids, other)
        with bind_calling_seat(SEAT):
            out = await _drive(
                run_place(_buy_in(ticket_id, ids.ulid(), approval_id), adapter, RiskBudget, clock),
                clock,
            )
        assert out["status"] == "rejected"
        assert out["reason"] == "approval_missing"
        assert _placed(store) == []
    finally:
        store.close()


EXIT_SEAT = "bot-06-exit"


def _ticket(store: LedgerStore, clock: FixtureClock) -> str:
    """Allocate one ticket for the current fixture day."""
    return allocate_ticket(
        store,
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id="test",
        seat=SEAT,
        title="lead",
    )


def _sell_in(
    ticket_id: str,
    decision_id: str,
    approval_id: str,
    *,
    token_units: int | None = None,
    size_lamports: int | None = SIZE,
) -> PlaceIn:
    """One paper sell; unit-priced, SOL-notional, or both."""
    fields: dict[str, Any] = {
        "ticket_id": ticket_id,
        "mint": MINT,
        "side": "sell",
        "decision_id": decision_id,
        "max_slippage_bps": 100,
        "approval_id": approval_id,
    }
    if token_units is not None:
        fields["token_units"] = token_units
    if size_lamports is not None:
        fields["size_lamports"] = size_lamports
    return PlaceIn.model_validate(fields)


def _fills(store: LedgerStore) -> list[dict[str, Any]]:
    return [e for e in store.read(limit=None) if e["type"] == "FillRecorded"]


async def test_confirmation_timeout_is_unknown_without_retry(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(
        tmp_path, limits=EngineLimits(confirm_timeout_s=0.05)
    )
    try:
        ticket_id = _ticket(store, clock)
        approval_id = _approve(store, clock, ids, ticket_id)
        decision_id = ids.ulid()
        with bind_calling_seat(SEAT):
            out = await _drive(
                run_place(_buy_in(ticket_id, decision_id, approval_id), adapter, RiskBudget, clock),
                clock,
            )
        assert out["status"] == "unknown", out
        assert out["reason"] == "confirmation_timeout"
        assert len(_placed(store)) == 1
        rejects = [e for e in store.read(limit=None) if e["type"] == "OrderRejected"]
        assert [r["payload"]["reason"] for r in rejects] == ["confirmation_timeout"]
        assert _fills(store) == []
        with bind_calling_seat(SEAT):
            repeat = await _drive(
                run_place(_buy_in(ticket_id, decision_id, approval_id), adapter, RiskBudget, clock),
                clock,
            )
        assert repeat["status"] == "unknown"
        assert repeat["reason"] == "confirmation_timeout"
        assert len(_placed(store)) == 1
        assert _fills(store) == []
    finally:
        store.close()


async def test_autonomous_paper_buy_mints_approval_and_fills(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path, autonomy="autonomous-paper")
    try:
        ticket_id = _ticket(store, clock)
        with bind_calling_seat(SEAT):
            out = await _drive(
                run_place(
                    _buy_in(ticket_id, ids.ulid(), f"apr-{ids.ulid()}"),
                    adapter,
                    RiskBudget,
                    clock,
                ),
                clock,
            )
        assert out["status"] == "filled", out
        placed = _placed(store)
        assert len(placed) == 1
        assert json.loads(placed[0]["payload"]["approval_json"])["kind"] == "autonomous_paper"
        consumes = [
            e
            for e in store.read(limit=None)
            if e["type"] == "ApprovalRecorded" and e["payload"].get("consumed") is True
        ]
        assert consumes == []
    finally:
        store.close()


async def test_autonomous_size_based_sell_derives_units_and_closes(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(
        tmp_path, autonomy="autonomous-paper", reads=[_snap()] * 8
    )
    try:
        ticket_id = _ticket(store, clock)
        with bind_calling_seat(SEAT):
            buy = await _drive(
                run_place(
                    _buy_in(ticket_id, ids.ulid(), f"apr-{ids.ulid()}"),
                    adapter,
                    RiskBudget,
                    clock,
                ),
                clock,
            )
        assert buy["status"] == "filled", buy
        await adapter.mark_to_market(MINT)
        with bind_calling_seat(EXIT_SEAT):
            sell = await _drive(
                run_place(
                    _sell_in(ticket_id, ids.ulid(), f"apr-{ids.ulid()}"),
                    adapter,
                    RiskBudget,
                    clock,
                ),
                clock,
            )
        assert sell["status"] in ("filled", "partial"), sell
        assert _fills(store)[-1]["payload"]["filled_lamports"] > 0
        closes = [e for e in store.read(limit=None) if e["type"] == "PositionClosed"]
        assert len(closes) == 1
    finally:
        store.close()


async def test_manual_sell_without_position_refuses_no_position(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path)
    try:
        ticket_id = _ticket(store, clock)
        approval_id = _approve(store, clock, ids, ticket_id, kind="human_sell")
        with bind_calling_seat(EXIT_SEAT):
            out = await _drive(
                run_place(
                    _sell_in(ticket_id, ids.ulid(), approval_id, token_units=1000),
                    adapter,
                    RiskBudget,
                    clock,
                ),
                clock,
            )
        assert out["status"] == "rejected"
        assert out["reason"] == "no_position"
        assert _placed(store) == []
    finally:
        store.close()


async def test_manual_unit_sell_closes_position(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path, reads=[_snap()] * 8)
    try:
        ticket_id = _ticket(store, clock)
        with bind_calling_seat(SEAT):
            buy = await _drive(
                run_place(
                    _buy_in(ticket_id, ids.ulid(), _approve(store, clock, ids, ticket_id)),
                    adapter,
                    RiskBudget,
                    clock,
                ),
                clock,
            )
        assert buy["status"] == "filled", buy
        units = int(_fills(store)[0]["payload"]["filled_units"])
        assert units > 0
        await adapter.mark_to_market(MINT)
        sell_approval = _approve(store, clock, ids, ticket_id, kind="human_sell")
        with bind_calling_seat(EXIT_SEAT):
            sell = await _drive(
                run_place(
                    _sell_in(ticket_id, ids.ulid(), sell_approval, token_units=units),
                    adapter,
                    RiskBudget,
                    clock,
                ),
                clock,
            )
        assert sell["status"] == "filled", sell
        closes = [e for e in store.read(limit=None) if e["type"] == "PositionClosed"]
        assert len(closes) == 1
    finally:
        store.close()


async def test_oversize_sell_caps_at_open_position(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path, reads=[_snap()] * 8)
    try:
        ticket_id = _ticket(store, clock)
        with bind_calling_seat(SEAT):
            buy = await _drive(
                run_place(
                    _buy_in(ticket_id, ids.ulid(), _approve(store, clock, ids, ticket_id)),
                    adapter,
                    RiskBudget,
                    clock,
                ),
                clock,
            )
        assert buy["status"] == "filled", buy
        units = int(_fills(store)[0]["payload"]["filled_units"])
        await adapter.mark_to_market(MINT)
        sell_approval = _approve(store, clock, ids, ticket_id, kind="human_sell")
        with bind_calling_seat(EXIT_SEAT):
            sell = await _drive(
                run_place(
                    _sell_in(ticket_id, ids.ulid(), sell_approval, token_units=units * 2),
                    adapter,
                    RiskBudget,
                    clock,
                ),
                clock,
            )
        assert sell["status"] == "partial", sell
        assert _fills(store)[-1]["payload"]["filled_units"] == units
        closes = [e for e in store.read(limit=None) if e["type"] == "PositionClosed"]
        assert len(closes) == 1
    finally:
        store.close()


async def test_cancel_unknown_order_is_not_found(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path)
    try:
        ticket_id = _ticket(store, clock)
        before = store.count()
        out = await run_cancel(
            CancelIn(
                order_id=ids.ulid(),
                ticket_id=ticket_id,
                approval_id=f"apr-{ids.ulid()}",
            ),
            adapter,
            store,
            clock,
        )
        assert out["cancelled"] is False
        assert out["status_after"] == "not_found"
        assert store.count() == before
    finally:
        store.close()


async def test_cancel_wrong_approval_fails_closed(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path)
    try:
        ticket_id = _ticket(store, clock)
        approval_id = _approve(store, clock, ids, ticket_id)
        with bind_calling_seat(SEAT):
            buy = await _drive(
                run_place(_buy_in(ticket_id, ids.ulid(), approval_id), adapter, RiskBudget, clock),
                clock,
            )
        assert buy["status"] == "filled", buy
        before = store.count()
        with pytest.raises(PermissionDenied):
            await run_cancel(
                CancelIn(
                    order_id=_placed(store)[0]["payload"]["order_id"],
                    ticket_id=ticket_id,
                    approval_id=f"apr-{ids.ulid()}",
                ),
                adapter,
                store,
                clock,
            )
        assert store.count() == before
    finally:
        store.close()


async def test_cancel_inflight_then_terminal(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path, reads=[_snap()] * 8)
    try:
        ticket_id = _ticket(store, clock)
        approval_id = _approve(store, clock, ids, ticket_id)
        with bind_calling_seat(SEAT):
            task = asyncio.create_task(
                run_place(_buy_in(ticket_id, ids.ulid(), approval_id), adapter, RiskBudget, clock)
            )
            placed_id: str | None = None
            for _ in range(400):
                placed = _placed(store)
                if placed:
                    placed_id = str(placed[0]["payload"]["order_id"])
                    break
                clock.advance_to(clock.now() + 0.1)
                await asyncio.sleep(0)
            assert placed_id is not None
            cancel = await run_cancel(
                CancelIn(order_id=placed_id, ticket_id=ticket_id, approval_id=approval_id),
                adapter,
                store,
                clock,
            )
            assert cancel["cancelled"] is True
            assert cancel["status_after"] == "cancelled"
            for _ in range(400):
                if task.done():
                    break
                clock.advance_to(clock.now() + 1.0)
                await asyncio.sleep(0)
            finish = await task
        assert finish["status"] == "rejected"
        assert finish["reason"] == "cancelled"
        assert _fills(store) == []
        again = await run_cancel(
            CancelIn(order_id=placed_id, ticket_id=ticket_id, approval_id=approval_id),
            adapter,
            store,
            clock,
        )
        assert again["cancelled"] is False
        assert again["status_after"] == "not_found"
    finally:
        store.close()


async def test_cancel_after_fill_is_already_filled(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path)
    try:
        ticket_id = _ticket(store, clock)
        approval_id = _approve(store, clock, ids, ticket_id)
        with bind_calling_seat(SEAT):
            buy = await _drive(
                run_place(_buy_in(ticket_id, ids.ulid(), approval_id), adapter, RiskBudget, clock),
                clock,
            )
        assert buy["status"] == "filled", buy
        before = store.count()
        out = await run_cancel(
            CancelIn(
                order_id=_placed(store)[0]["payload"]["order_id"],
                ticket_id=ticket_id,
                approval_id=approval_id,
            ),
            adapter,
            store,
            clock,
        )
        assert out["cancelled"] is False
        assert out["status_after"] == "already_filled"
        assert store.count() == before
    finally:
        store.close()


async def test_positions_reports_ledger_equity_and_cash(tmp_path: Path) -> None:
    adapter, clock, _engine, ids, store = _harness(tmp_path, reads=[_snap()] * 8)
    try:
        ticket_id = _ticket(store, clock)
        with bind_calling_seat(SEAT):
            buy = await _drive(
                run_place(
                    _buy_in(ticket_id, ids.ulid(), _approve(store, clock, ids, ticket_id)),
                    adapter,
                    RiskBudget,
                    clock,
                ),
                clock,
            )
        assert buy["status"] == "filled", buy
        await adapter.mark_to_market(MINT)
        out = await run_positions(PositionsIn(), adapter, clock)
        assert len(out["positions"]) == 1
        assert out["positions"][0]["ticket_id"] == ticket_id
        for key in ("equity_lamports", "cash_lamports"):
            assert isinstance(out[key], int)
            assert out[key] >= 0
        assert out["cash_lamports"] == adapter.cash_lamports()
        assert out["equity_lamports"] == adapter.equity_lamports()
        assert out["cash_lamports"] < EQUITY
        assert out["equity_lamports"] >= out["cash_lamports"]
    finally:
        store.close()
