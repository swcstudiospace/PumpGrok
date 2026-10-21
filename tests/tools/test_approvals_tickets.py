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
from pumpgrok.core.ids import IdFactory, bind_calling_seat
from pumpgrok.core.risk_budget import RiskBudget
from pumpgrok.execution.paper_adapter import CurveSnapshot, PaperAdapter
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.ledger.tickets import allocate_ticket, day_ticket_count
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng
from pumpgrok.risk.engine import RiskEngine
from pumpgrok.tools.exec.place import PlaceIn, run_place

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
    tmp_path: Path, *, seed: int = 7
) -> tuple[PaperAdapter, FixtureClock, RiskEngine, IdFactory, LedgerStore]:
    clock = FixtureClock(START)
    store = _store(tmp_path)
    ids = IdFactory(clock, make_rng(seed))
    engine = RiskEngine(
        store=store,
        budget=RiskBudget(),
        ids=IdFactory(clock, random.Random(seed)),
        clock=clock,
        autonomy="manual-ticket",  # type: ignore[arg-type]
        get_reserves=lambda _mint: (S0, T0),
    )
    adapter = PaperAdapter(
        store=store,
        risk=engine,
        ids=ids,
        clock=clock,
        rng=make_rng(seed),
        budget=RiskBudget(),
        price_source=ScriptedCurves([_snap(), _snap()]),
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
