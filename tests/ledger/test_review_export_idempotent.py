"""Regression: export_ledger writes each derived row exactly once across retries.

Greptile review finding 25 (src/pumpgrok/ledger/export.py): the export appended
the journal and trade files before advancing export_seq, so a retry after a
failed trade write, or after a crash between the file flush and the cursor
update, appended the journal rows a second time.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.ledger.export import EXPORT_SEQ_KEY, export_ledger
from pumpgrok.ledger.store import LedgerStore

MINT = "ExportIdem1111111111111111111111111111111111"
CID = "01J0000000000000000000001"
DAY_FILE = "2026-01-01.jsonl"


def _row(ts: str, key: str, type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts_utc": ts,
        "source": "paper",
        "correlation_id": CID,
        "idempotency_key": key,
        "type": type,
        "payload": payload,
    }


def _store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(tmp_path / "ledger.sqlite")
    store.set_meta("source", "paper")
    store.set_meta("initial_equity_lamports", "10000000000")
    store.append_batch(
        [
            _row(
                "2026-01-01T00:00:01.000001Z",
                "fill-buy-0001",
                "FillRecorded",
                {
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
            ),
            _row(
                "2026-01-01T00:00:02.000001Z",
                "rejected-0001",
                "OrderRejected",
                {
                    "source": "paper",
                    "order_id": "01J0000000000000000000005",
                    "decision_id": "01J0000000000000000000006",
                    "reason": "slippage_exceeded",
                    "detail": "confirm 1 < threshold 2",
                    "stage": "CONFIRMING",
                    "fees_lamports": 9000,
                },
            ),
            _row(
                "2026-01-01T00:00:03.000001Z",
                "closed-0001",
                "PositionClosed",
                {
                    "source": "paper",
                    "mint": MINT,
                    "price_exit": "6.2e-5",
                    "proceeds_lamports": 225000000,
                    "realized_pnl_lamports": 25000000,
                    "reason": "take_profit",
                    "pnl_pct": "12.5",
                    "hold_seconds": 300,
                    "venue_tx_ref": "dry_run:01J0000000000000000000007",
                },
            ),
            _row(
                "2026-01-01T00:00:04.000001Z",
                "note-0001",
                "JournalNote",
                {"source": "paper", "seat": "desk", "note_kind": "note", "text": "note"},
            ),
        ]
    )
    return store


def _records(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _export_seqs(path: Path) -> list[int]:
    """Seqs of export records only; a record without ``type`` is not one of ours."""
    return [record["seq"] for record in _records(path) if "type" in record]


def test_retry_after_failed_trade_write_appends_each_row_once(tmp_path: Path) -> None:
    store = _store(tmp_path)
    journal_dir = tmp_path / "journal"
    trades_path = tmp_path / "trades.jsonl"
    trades_path.mkdir()  # the journal write succeeds, then the trade write fails
    with pytest.raises(OSError):
        export_ledger(store, journal_dir=journal_dir, trades_path=trades_path)
    assert _export_seqs(journal_dir / DAY_FILE) == [1, 2, 3, 4]
    trades_path.rmdir()
    retry = export_ledger(store, journal_dir=journal_dir, trades_path=trades_path)
    assert retry == {"journal_lines": 0, "trade_lines": 3, "export_seq": 4}
    assert _export_seqs(journal_dir / DAY_FILE) == [1, 2, 3, 4]
    trades = _records(trades_path)
    assert [record["type"] for record in trades] == ["buy", "skip", "close"]


def test_crash_between_flush_and_cursor_update_appends_nothing_on_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    journal_dir = tmp_path / "journal"
    trades_path = tmp_path / "trades.jsonl"

    def crash(key: str, value: str) -> None:
        raise RuntimeError("crash before cursor update")

    monkeypatch.setattr(store, "set_meta", crash)
    with pytest.raises(RuntimeError):
        export_ledger(store, journal_dir=journal_dir, trades_path=trades_path)
    journal_bytes = (journal_dir / DAY_FILE).read_bytes()
    trades_bytes = trades_path.read_bytes()
    assert store.get_meta(EXPORT_SEQ_KEY) is None

    monkeypatch.undo()
    retry = export_ledger(store, journal_dir=journal_dir, trades_path=trades_path)
    assert retry == {"journal_lines": 0, "trade_lines": 0, "export_seq": 4}
    assert (journal_dir / DAY_FILE).read_bytes() == journal_bytes
    assert trades_path.read_bytes() == trades_bytes
    assert store.get_meta(EXPORT_SEQ_KEY) == "4"


def test_torn_trailing_fragment_is_cut_and_each_row_lands_once(tmp_path: Path) -> None:
    store = _store(tmp_path)
    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    (journal_dir / DAY_FILE).write_text('{"seq":1,"ts_utc":"2026-01-0', encoding="utf-8")
    trades_path = tmp_path / "trades.jsonl"
    trades_path.write_text('{"type":"buy","seq":1', encoding="utf-8")
    result = export_ledger(store, journal_dir=journal_dir, trades_path=trades_path)
    assert result == {"journal_lines": 4, "trade_lines": 3, "export_seq": 4}
    assert _export_seqs(journal_dir / DAY_FILE) == [1, 2, 3, 4]
    assert [record["seq"] for record in _records(trades_path)] == [1, 2, 3]


def test_journal_append_line_for_same_seq_is_not_an_export_record(tmp_path: Path) -> None:
    store = _store(tmp_path)
    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    foreign = {"seq": 4, "kind": "journal_note", "payload": {"text": "note"}}
    (journal_dir / DAY_FILE).write_text(json.dumps(foreign) + "\n", encoding="utf-8")
    result = export_ledger(store, journal_dir=journal_dir, trades_path=tmp_path / "trades.jsonl")
    assert result["journal_lines"] == 4
    assert _export_seqs(journal_dir / DAY_FILE) == [1, 2, 3, 4]
