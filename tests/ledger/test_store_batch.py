"""Batch atomicity, reducer/views fold, and restart reconcile (PAPER-002)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import threading
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.desk_bus import mirror_halt, mirror_halt_cleared, mirror_killswitch
from pumpgrok.ledger.export import export_ledger
from pumpgrok.ledger.reconcile import CONSISTENT, INCONSISTENT, reconcile
from pumpgrok.ledger.reducer import dump_state, initial_state, load_state, reduce
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore
from pumpgrok.ledger.tickets import TICKET_RE, allocate_ticket
from pumpgrok.ledger.views import cash_lamports, equity_lamports, unrealized_pnl_lamports
from pumpgrok.ledger.views import positions as open_positions


def _note(**overrides):
    base = {
        "ts_utc": "2026-01-01T00:00:00.000001Z",
        "source": "replay",
        "correlation_id": "01J0000000000000000000000",
        "idempotency_key": "aaaabbbbccccdddd",
        "type": "JournalNote",
        "payload": {"source": "replay", "seat": "desk", "note_kind": "note", "text": "skip"},
    }
    base.update(overrides)
    return base


def test_batch_single_journal_note_verifies(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    rows = store.append_batch([_note()])
    assert len(rows) == 1
    assert rows[0]["seq"] == 1
    assert rows[0]["prev_hash"] == "0" * 64
    assert store.verify() is True
    result = reconcile(store)
    assert result["status"] == CONSISTENT
    assert result["tail_events"] == 1
    assert result["head_seq"] == 1


def test_batch_duplicate_key_refused_no_partial_rows(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    with pytest.raises(sqlite3.IntegrityError):
        store.append_batch(
            [
                _note(),
                _note(ts_utc="2026-01-01T00:00:01.000001Z"),
            ]
        )
    assert store.count() == 0
    assert store.verify() is True


def test_batch_rejects_float_money(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    bad = _note()
    bad["payload"] = dict(bad["payload"])
    bad["payload"]["text"] = 1.5  # type: ignore[dict-item]
    with pytest.raises((TypeError, ValueError)):
        store.append_batch([bad])
    assert store.count() == 0


MINT = "ExpoLate1111111111111111111111111111111111"
INITIAL_EQUITY = 10_000_000_000


def _approval(**overrides):
    base = {
        "ts_utc": "2026-01-01T00:00:00.000001Z",
        "source": "paper",
        "correlation_id": "01J0000000000000000000001",
        "idempotency_key": "approval-key-0001",
        "type": "ApprovalRecorded",
        "payload": {
            "source": "paper",
            "id": "apr-01J0000000000000000000001",
            "kind": "human_buy",
            "approved_by": "human:chief",
            "at": "2026-01-01T00:00:00.000001Z",
            "ticket_id": "SOL-20260101-001",
            "mint": MINT,
            "size_lamports": 200_000_000,
            "token_units": 0,
            "max_slippage_bps": 100,
            "raw_message": "buy 0.2 SOL of ExpoLate",
            "consumed": False,
        },
    }
    base.update(overrides)
    return base


def _order(**overrides):
    base = {
        "ts_utc": "2026-01-01T00:00:01.000001Z",
        "source": "paper",
        "correlation_id": "01J0000000000000000000001",
        "idempotency_key": "order-key-0001",
        "type": "OrderPlaced",
        "payload": {
            "source": "paper",
            "order_id": "01J0000000000000000000002",
            "decision_id": "01J0000000000000000000003",
            "ticket_id": "SOL-20260101-001",
            "side": "buy",
            "mint": MINT,
            "slippage_bps": 100,
            "size_lamports": 200_000_000,
            "approval_json": "approval-key-0001",
        },
    }
    base.update(overrides)
    return base


def _consume_approval(**overrides):
    row = _approval(
        ts_utc="2026-01-01T00:00:01.000002Z",
        idempotency_key="approval-key-0002",
    )
    consumed = dict(row["payload"])
    consumed["consumed"] = True
    row["payload"] = consumed
    row.update(overrides)
    return row


def test_batch_approval_consume_plus_order_commits_atomically(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    rows = store.append_batch([_approval(), _consume_approval(), _order()])
    assert [r["seq"] for r in rows] == [1, 2, 3]
    assert store.verify() is True
    first = store.by_key("approval-key-0001")
    assert first is not None
    assert first["payload"]["consumed"] is False
    second = store.by_key("approval-key-0002")
    assert second is not None
    assert second["payload"]["consumed"] is True
    assert store.by_key("order-key-0001")["type"] == "OrderPlaced"
    assert store.by_key("missing-key") is None


def test_batch_failure_after_valid_row_leaves_no_partials(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.append(**_note())
    bad = _note(ts_utc="2026-01-01T00:00:05.000001Z", idempotency_key="fresh-key-1")
    broken = _note(ts_utc="2026-01-01T00:00:06.000001Z", type="NotARealEvent")
    with pytest.raises(ValueError):
        store.append_batch([bad, broken])
    assert store.count() == 1
    assert store.by_key("fresh-key-1") is None


def test_concurrent_writers_never_interleave_rows(tmp_path) -> None:
    path = tmp_path / "ledger.sqlite"
    LedgerStore(path).close()

    def worker(slot: int) -> None:
        handle = LedgerStore(path)
        try:
            for i in range(10):
                handle.append_batch(
                    [
                        _note(
                            ts_utc=f"2026-01-01T00:{slot:02d}:{i:02d}.000001Z",
                            correlation_id=f"01J0000000000000000{slot:06d}",
                            idempotency_key=f"slot-{slot}-row-{i}",
                        )
                    ]
                )
        finally:
            handle.close()

    threads = [threading.Thread(target=worker, args=(slot,)) for slot in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    store = LedgerStore(path)
    try:
        assert store.count() == 40
        assert store.verify() is True
        seqs = sorted(e["seq"] for e in store.read(since_seq=1, limit=None))
        assert seqs == list(range(1, 41))
    finally:
        store.close()


def test_tamper_verifies_inconsistent_and_refuses_appends(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.append(**_note())
    store.append(**_note(ts_utc="2026-01-01T00:00:01.000001Z", idempotency_key="key-2"))
    store._db.execute("DROP TRIGGER events_append_only_u;")
    store._db.execute("UPDATE events SET payload_json = '{}' WHERE seq = 1;")
    result = reconcile(store)
    assert result["status"] == INCONSISTENT
    with pytest.raises(LedgerInconsistent):
        store.append(**_note(idempotency_key="after-tamper"))


def test_source_column_rejects_unknown_sources(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    with pytest.raises(ValueError):
        store.append(**_note(source="live"))
    store.append_batch([_note(), _note(source="manual", idempotency_key="manual-1")])
    for event in store.read(since_seq=1, limit=None):
        assert event["source"] in ("paper", "replay", "manual")


def test_reducer_views_fold_over_paper_fill(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.set_meta("source", "paper")
    store.set_meta("initial_equity_lamports", str(INITIAL_EQUITY))
    fill = {
        "ts_utc": "2026-01-01T00:00:02.000001Z",
        "source": "paper",
        "correlation_id": "01J0000000000000000000001",
        "idempotency_key": "fill-key-0001",
        "type": "FillRecorded",
        "payload": {
            "source": "paper",
            "order_id": "01J0000000000000000000002",
            "decision_id": "01J0000000000000000000003",
            "side": "buy",
            "mint": MINT,
            "filled_lamports": 200_000_000,
            "filled_units": 3579186000000,
            "filled_fraction": "1",
            "price_avg": "5.532e-5",
            "venue_fee_lamports": 2000000,
            "network_cost_lamports": 9000,
            "cash_delta_lamports": -200009000,
            "latency_s": "1.4",
            "venue_tx_ref": "dry_run:01J0000000000000000000004",
        },
    }
    opened = {
        "ts_utc": "2026-01-01T00:00:02.000002Z",
        "source": "paper",
        "correlation_id": "01J0000000000000000000001",
        "idempotency_key": "opened-key-0001",
        "type": "PositionOpened",
        "payload": {
            "source": "paper",
            "mint": MINT,
            "price_entry": "5.532e-5",
            "token_units": 3579186000000,
            "cost_basis_lamports": 200009000,
            "opened_ts_utc": "2026-01-01T00:00:02.000002Z",
            "symbol": "EXPO",
            "ticket_id": "SOL-20260101-001",
        },
    }
    mtm = {
        "ts_utc": "2026-01-01T00:01:00.000001Z",
        "source": "paper",
        "correlation_id": "desk",
        "idempotency_key": "mtm-key-0001",
        "type": "MarkToMarket",
        "payload": {
            "source": "paper",
            "ts_source": "curve",
            "cash_lamports": INITIAL_EQUITY - 200009000,
            "equity_lamports": INITIAL_EQUITY - 200009000 + 196020000,
            "unrealized_lamports": -3989000,
            "prices_json": json.dumps({MINT: {"mtm_lamports": 196020000, "source": "curve"}}),
        },
    }
    store.append_batch([_approval(), _consume_approval(), _order(), fill, opened, mtm])
    assert store.verify() is True
    result = reconcile(store)
    assert result["status"] == CONSISTENT
    state = load_state(result["state"])
    assert cash_lamports(state) == INITIAL_EQUITY - 200009000
    assert list(open_positions(state)) == [MINT]
    assert unrealized_pnl_lamports(state) == -3989000
    assert equity_lamports(state) == INITIAL_EQUITY - 200009000 + 196020000
    assert state.counters.trades_today == 1
    assert state.counters.fees_today_lamports == 2009000
    void = dump_state(initial_state(source="paper", initial_equity_lamports=0, day_utc=""))
    assert isinstance(void, dict)


def test_restart_replays_snapshot_plus_tail(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.set_meta("source", "replay")
    store.set_meta("initial_equity_lamports", "0")
    store.append_batch(
        [
            _note(idempotency_key="snap-1"),
            _note(ts_utc="2026-01-01T00:00:01.000001Z", idempotency_key="snap-2"),
        ]
    )
    genesis = initial_state(source="replay", initial_equity_lamports=0, day_utc="2026-01-01")
    folded = genesis
    for event in store.read(since_seq=1, limit=None):
        folded = reduce(folded, event)
    body = dump_state(folded)
    head = store.read(since_seq=2, limit=1)[0]
    body["meta"] = {"chain_hash": head["hash"]}
    store.write_snapshot(seq=2, ts_utc="2026-01-01T00:00:01.000001Z", state=body)
    store.append(**_note(ts_utc="2026-01-01T00:00:02.000001Z", idempotency_key="tail-1"))
    result = reconcile(store)
    assert result["status"] == CONSISTENT
    assert result["snapshot_seq"] == 2
    assert result["tail_events"] == 1
    assert result["head_seq"] == 3


def _fill_row(**overrides):
    base = {
        "ts_utc": "2026-01-01T00:00:02.000001Z",
        "source": "paper",
        "correlation_id": "01J0000000000000000000001",
        "idempotency_key": "fill-key-0001",
        "type": "FillRecorded",
        "payload": {
            "source": "paper",
            "order_id": "01J0000000000000000000002",
            "decision_id": "01J0000000000000000000003",
            "side": "buy",
            "mint": MINT,
            "filled_lamports": 200_000_000,
            "filled_units": 3579186000000,
            "filled_fraction": "1",
            "price_avg": "5.532e-5",
            "venue_fee_lamports": 2000000,
            "network_cost_lamports": 9000,
            "cash_delta_lamports": -200009000,
            "latency_s": "1.4",
            "venue_tx_ref": "dry_run:01J0000000000000000000004",
        },
    }
    base.update(overrides)
    return base


def _closed_row(**overrides):
    base = {
        "ts_utc": "2026-01-01T00:00:03.000001Z",
        "source": "paper",
        "correlation_id": "01J0000000000000000000001",
        "idempotency_key": "closed-key-0001",
        "type": "PositionClosed",
        "payload": {
            "source": "paper",
            "mint": MINT,
            "price_exit": "6.2e-5",
            "proceeds_lamports": 225000000,
            "realized_pnl_lamports": 25000000,
            "reason": "take_profit",
            "pnl_pct": "12.5",
            "hold_seconds": 300,
            "venue_tx_ref": "dry_run:01J0000000000000000000005",
        },
    }
    base.update(overrides)
    return base


def _rejected_row(**overrides):
    base = {
        "ts_utc": "2026-01-01T00:00:04.000001Z",
        "source": "paper",
        "correlation_id": "01J0000000000000000000001",
        "idempotency_key": "rejected-key-0001",
        "type": "OrderRejected",
        "payload": {
            "source": "paper",
            "order_id": "01J0000000000000000000006",
            "decision_id": "01J0000000000000000000007",
            "reason": "slippage_exceeded",
            "detail": "confirm 3512285 < threshold 3560247",
            "stage": "CONFIRMING",
            "fees_lamports": 9000,
        },
    }
    base.update(overrides)
    return base


def test_export_resumes_without_duplicate_rows(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.set_meta("source", "paper")
    store.set_meta("initial_equity_lamports", str(INITIAL_EQUITY))
    store.append_batch([_approval(), _order(), _fill_row(), _closed_row(), _rejected_row()])
    journal_dir = tmp_path / "journal"
    trades_path = journal_dir / "trades.jsonl"
    first = export_ledger(store, journal_dir=journal_dir, trades_path=trades_path)
    assert first == {"journal_lines": 5, "trade_lines": 3, "export_seq": 5}
    day_lines = (journal_dir / "2026-01-01.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(day_lines) == 5
    assert json.loads(day_lines[0])["seq"] == 1
    trades = [json.loads(line) for line in trades_path.read_text(encoding="utf-8").splitlines()]
    assert [record["type"] for record in trades] == ["buy", "close", "skip"]
    assert trades[0]["tx_hash"] == "dry_run"
    assert Decimal(trades[0]["size_sol"]) == Decimal("0.2")
    assert trades[2]["reason"] == "slippage_exceeded"
    before = hashlib.sha256(trades_path.read_bytes()).hexdigest()
    second = export_ledger(store, journal_dir=journal_dir, trades_path=trades_path)
    assert second == {"journal_lines": 0, "trade_lines": 0, "export_seq": 5}
    assert hashlib.sha256(trades_path.read_bytes()).hexdigest() == before
    assert (journal_dir / "2026-01-01.jsonl").read_text(encoding="utf-8").splitlines() == day_lines


def test_desk_mirrors_swap_atomically(tmp_path) -> None:
    desk = tmp_path / "desk"
    desk.mkdir()
    (desk / "desk.md").write_text("# Desk\n\nHalt: false\n", encoding="utf-8")
    first = mirror_halt(desk, reason="daily_loss", ts_utc="2026-01-01T00:00:00Z")
    body = first.read_text(encoding="utf-8")
    assert "Halt: true" in body
    assert "FLOOR HALTED - daily_loss @ 2026-01-01T00:00:00Z" in body
    assert "# Desk" in body
    mirror_halt(desk, reason="drawdown", ts_utc="2026-01-01T01:00:00Z")
    body = first.read_text(encoding="utf-8")
    assert body.count("Halt: true") == 1
    assert "FLOOR HALTED - drawdown @ 2026-01-01T01:00:00Z" in body
    mirror_halt_cleared(
        desk, reason="daily_loss", cleared_by="human:chief", ts_utc="2026-01-01T02:00:00Z"
    )
    body = first.read_text(encoding="utf-8")
    assert "Halt: false" in body
    mirror_killswitch(desk, source="file", reason="manual", ts_utc="2026-01-01T03:00:00Z")
    body = first.read_text(encoding="utf-8")
    assert "FLOOR HALTED - KILL SWITCH (file): manual @ 2026-01-01T03:00:00Z" in body


def test_tickets_allocate_per_day_sequences(tmp_path) -> None:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    first = allocate_ticket(
        store,
        ts_utc="2026-01-01T00:00:00.000001Z",
        source="paper",
        correlation_id="01J0000000000000000000001",
        seat="chief",
        title="scout candidate review",
    )
    second = allocate_ticket(
        store,
        ts_utc="2026-01-01T00:01:00.000001Z",
        source="paper",
        correlation_id="01J0000000000000000000002",
        seat="chief",
        title="second review",
    )
    third = allocate_ticket(
        store,
        ts_utc="2026-01-02T00:00:00.000001Z",
        source="paper",
        correlation_id="01J0000000000000000000003",
        seat="chief",
        title="next day review",
    )
    assert first == "SOL-20260101-001"
    assert second == "SOL-20260101-002"
    assert third == "SOL-20260102-001"
    assert TICKET_RE.match(first) is not None
    assert store.verify() is True
    rows = store.read(since_seq=1, limit=None)
    assert [row["payload"]["note_kind"] for row in rows] == ["ticket"] * 3
    assert [row["payload"]["refs"][0] for row in rows] == [first, second, third]
