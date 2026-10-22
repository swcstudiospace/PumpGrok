"""INV-R-25: every bot action is replayable from ledger plus journal.

Owning test for SAFETY_INVARIANTS.md section 3.3 row INV-R-25. For every
OrderPlaced in a replay of a ten-minute window there exist, with the same
correlation id, a JournalNote with note_kind=signal, a JournalNote with
note_kind=safety_report, the decision (OrderPlaced.decision_id plus
decision rules), an ApprovalRecorded, and a FillRecorded or
OrderRejected; one var/journal/YYYY-MM-DD.jsonl line exists per event.
Set equality holds between ledger events and JSONL lines by seq, with
zero orphan orders, and pumpgrok verify --ledger succeeds (store.verify
plus reconcile CONSISTENT, the same checks the CLI verb runs).

Harness: FixtureClock plus seeded IdFactory; no wall clock, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

from pumpgrok.core.ids import IdFactory
from pumpgrok.ledger.export import export_ledger
from pumpgrok.ledger.reconcile import CONSISTENT, reconcile
from pumpgrok.ledger.store import LedgerStore, recreate_ledger_db
from pumpgrok.replay.clock import FixtureClock, format_ts_utc
from pumpgrok.replay.rng import make_rng

BASE = 1767225600.0
DAY = "2026-01-01"
CID = "01JAAAAAAAAAAAAAAAAAAAAAAAAA"
MINT = "D" * 44
TICKET = "SOL-20260101-001"


def _append(store: LedgerStore, clock: FixtureClock, key: str, type: str, payload: dict) -> None:
    store.append(
        ts_utc=format_ts_utc(clock.now()),
        source="paper",
        correlation_id=CID,
        idempotency_key=key,
        type=type,
        payload=payload,
    )


def test_order_chain_complete_in_ledger_and_journal(tmp_path: Path) -> None:
    """INV-R-25: complete per-order chain; ledger equals journal by seq."""
    db_path = tmp_path / "ledger.sqlite"
    recreate_ledger_db(db_path)
    clock = FixtureClock(start=BASE)
    ids = IdFactory(clock, make_rng(11))
    store = LedgerStore(str(db_path))
    try:
        decision_id = ids.ulid()
        approval_id = f"apr-{ids.ulid()}"
        order_id = ids.ulid()
        rules = [
            {"id": "kill_switch", "status": "pass"},
            {"id": "daily_loss_halt", "status": "pass"},
            {"id": "seat_may_trade", "status": "pass"},
        ]
        _append(
            store,
            clock,
            "rollover-day",
            "DailyRollover",
            {
                "source": "paper",
                "day_utc": DAY,
                "day_start_equity_lamports": 10_000_000_000,
                "prior_day_json": "{}",
                "open_positions": [],
            },
        )
        _append(
            store,
            clock,
            "note-signal",
            "JournalNote",
            {
                "source": "paper",
                "seat": "desk",
                "note_kind": "signal",
                "text": "signal: mint D passes gates",
                "refs": [decision_id],
            },
        )
        _append(
            store,
            clock,
            "note-safety",
            "JournalNote",
            {
                "source": "paper",
                "seat": "desk",
                "note_kind": "safety_report",
                "text": "safety: mint D not a rug",
                "refs": [decision_id],
            },
        )
        _append(
            store,
            clock,
            "approval-buy",
            "ApprovalRecorded",
            {
                "source": "paper",
                "id": approval_id,
                "kind": "human_buy",
                "approved_by": "human:alice",
                "at": format_ts_utc(clock.now()),
                "ticket_id": TICKET,
                "mint": MINT,
                "size_lamports": 200_000_000,
                "token_units": 1_000_000,
                "max_slippage_bps": 50,
                "consumed": True,
            },
        )
        _append(
            store,
            clock,
            "order-buy",
            "OrderPlaced",
            {
                "source": "paper",
                "order_id": order_id,
                "decision_id": decision_id,
                "ticket_id": TICKET,
                "side": "buy",
                "mint": MINT,
                "slippage_bps": 50,
                "size_lamports": 200_000_000,
                "token_units": 1_000_000,
                "quote_json": "{}",
                "approval_json": approval_id,
                "risk_json": json.dumps({"rules": rules}),
            },
        )
        _append(
            store,
            clock,
            "fill-buy",
            "FillRecorded",
            {
                "source": "paper",
                "order_id": order_id,
                "decision_id": decision_id,
                "side": "buy",
                "mint": MINT,
                "filled_lamports": 200_000_000,
                "filled_units": 1_000_000,
                "filled_fraction": "1",
                "price_avg": "200",
                "venue_fee_lamports": 0,
                "network_cost_lamports": 0,
                "cash_delta_lamports": -200_000_000,
                "latency_s": "0.1",
                "venue_tx_ref": "",
                "route": "curve",
            },
        )
        events = store.read(limit=None)
        assert store.verify() is True
        assert reconcile(store)["status"] == CONSISTENT
        # One chain per order: every OrderPlaced resolves to its companions.
        orders = [event for event in events if event["type"] == "OrderPlaced"]
        assert len(orders) == 1
        order = orders[0]
        assert order["correlation_id"] == CID
        companions = [event for event in events if event["correlation_id"] == CID]
        kinds = [event["type"] for event in companions]
        assert "OrderPlaced" in kinds
        signal = [
            event
            for event in companions
            if event["type"] == "JournalNote" and event["payload"].get("note_kind") == "signal"
        ]
        safety = [
            event
            for event in companions
            if event["type"] == "JournalNote"
            and event["payload"].get("note_kind") == "safety_report"
        ]
        assert len(signal) == 1
        assert len(safety) == 1
        approvals = [event for event in companions if event["type"] == "ApprovalRecorded"]
        assert len(approvals) == 1
        assert approvals[0]["payload"]["id"] in order["payload"]["approval_json"]
        outcomes = [
            event
            for event in companions
            if event["type"] in ("FillRecorded", "OrderRejected")
            and event["payload"].get("order_id") == order["payload"]["order_id"]
        ]
        assert len(outcomes) == 1
        # The decision travels with the order; nothing is orphaned.
        assert order["payload"]["decision_id"] == decision_id
        assert json.loads(order["payload"]["risk_json"]) == {"rules": rules}
        assert signal[0]["payload"]["refs"] == [decision_id]
        # Journal export: one JSONL line per event, seq sets equal.
        journal_dir = tmp_path / "var" / "journal"
        result = export_ledger(
            store, journal_dir=journal_dir, trades_path=tmp_path / "trades.jsonl"
        )
        assert result["journal_lines"] == len(events)
        lines = [
            json.loads(line)
            for path in sorted(journal_dir.glob("*.jsonl"))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]
        assert {line["seq"] for line in lines} == {event["seq"] for event in events}
        assert len(lines) == len(events)
        orphans = [
            event
            for event in events
            if event["type"] == "OrderPlaced"
            and not any(
                other["type"] in ("FillRecorded", "OrderRejected")
                and other["payload"].get("order_id") == event["payload"]["order_id"]
                for other in events
            )
        ]
        assert orphans == []
    finally:
        store.close()
