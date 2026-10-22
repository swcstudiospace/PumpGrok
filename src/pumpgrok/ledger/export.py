"""JSONL journal export resumed from meta.export_seq (paper-engine.md 3.6, R21).

Two targets share one cursor: the canonical per-day journal (one line per
ledger event) and the vendor-shape ``trades.jsonl`` that the ``pumpgrok scout
pipeline --candidates`` reader and the vendor dashboard keep reading. The
hash-chained sqlite rows stay the single source of truth; export is derived.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pumpgrok.core.idempotency import canonical_json
from pumpgrok.ledger.store import LedgerStore

EXPORT_SEQ_KEY = "export_seq"
LAMPORTS_PER_SOL = 1_000_000_000
DRY_RUN_TX = "dry_run"


def _epoch(ts_utc: str) -> float:
    """ISO-8601 UTC stamp to epoch seconds (vendor ``ts`` is a float)."""
    parsed = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
    return parsed.astimezone(UTC).timestamp()


def _append_lines(path: Path, lines: list[str]) -> None:
    """Append-only write with fsync; readers never see a torn line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for line in lines:
            fh.write(line + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def _journal_batches(events: list[dict[str, Any]]) -> dict[str, list[str]]:
    by_day: dict[str, list[str]] = {}
    for event in events:
        day = str(event.get("ts_utc", ""))[:10]
        line = canonical_json(
            {
                "seq": event["seq"],
                "ts_utc": event["ts_utc"],
                "source": event["source"],
                "correlation_id": event["correlation_id"],
                "type": event["type"],
                "payload": event["payload"],
            }
        )
        by_day.setdefault(day, []).append(line)
    return by_day


def _buy_line(event: dict[str, Any]) -> dict[str, Any]:
    payload = event["payload"]
    return {
        "type": "buy",
        "ts": _epoch(str(event["ts_utc"])),
        "mode": "paper",
        "seq": event["seq"],
        "mint": str(payload.get("mint", "")),
        "symbol": "",
        "name": "",
        "size_sol": round(int(payload.get("filled_lamports", 0)) / LAMPORTS_PER_SOL, 6),
        "entry_price": float(payload.get("price_avg", "0")) / 1000.0,
        "tx_hash": DRY_RUN_TX,
        # Bare tx_hash keeps pumpgrok scout pipeline --candidates matching;
        # the unique paper ref rides alongside per paper-engine 964.
        "venue_tx_ref": str(payload.get("venue_tx_ref", "")),
    }


def _skip_line(event: dict[str, Any]) -> dict[str, Any]:
    payload = event["payload"]
    return {
        "type": "skip",
        "ts": _epoch(str(event["ts_utc"])),
        "mode": "paper",
        "seq": event["seq"],
        "mint": str(payload.get("mint", "")),
        "symbol": "",
        "stage": str(payload.get("stage", "risk")),
        "reason": str(payload.get("reason", "")),
        "detail": str(payload.get("detail", "")),
        "scores": None,
    }


def _close_line(event: dict[str, Any]) -> dict[str, Any]:
    payload = event["payload"]
    return {
        "type": "close",
        "ts": _epoch(str(event["ts_utc"])),
        "mode": "paper",
        "seq": event["seq"],
        "mint": str(payload.get("mint", "")),
        "symbol": "",
        "creator": "",
        "entry_price": 0.0,
        "exit_price": float(payload.get("price_exit", "0")) / 1000.0,
        "pnl_sol": round(int(payload.get("realized_pnl_lamports", 0)) / LAMPORTS_PER_SOL, 6),
        "pnl_pct": float(payload.get("pnl_pct", "0")),
        "hold_seconds": int(payload.get("hold_seconds", 0)),
        "reason": str(payload.get("reason", "")),
        # Bare tx_hash keeps the evidence tooling matching; the unique paper
        # ref rides alongside per paper-engine 964.
        "tx_hash": DRY_RUN_TX,
        "venue_tx_ref": str(payload.get("venue_tx_ref", "")),
        "score": 0,
    }


def _trade_lines(events: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for event in events:
        if event.get("type") == "FillRecorded" and event["payload"].get("side") == "buy":
            lines.append(json.dumps(_buy_line(event), ensure_ascii=False))
        elif event.get("type") == "OrderRejected":
            lines.append(json.dumps(_skip_line(event), ensure_ascii=False))
        elif event.get("type") == "PositionClosed":
            lines.append(json.dumps(_close_line(event), ensure_ascii=False))
    return lines


def export_ledger(
    store: LedgerStore, *, journal_dir: str | Path, trades_path: str | Path
) -> dict[str, Any]:
    """Export both targets under the single export_seq cursor.

    A second run with no new rows writes nothing and keeps the cursor.
    """
    export_seq = int(store.get_meta(EXPORT_SEQ_KEY) or "0")
    events = store.read(since_seq=export_seq + 1, limit=None)
    for day, lines in sorted(_journal_batches(events).items()):
        _append_lines(Path(journal_dir) / f"{day}.jsonl", lines)
    trade_lines = _trade_lines(events)
    if trade_lines:
        _append_lines(Path(trades_path), trade_lines)
    if events:
        store.set_meta(EXPORT_SEQ_KEY, str(events[-1]["seq"]))
        export_seq = int(events[-1]["seq"])
    return {
        "journal_lines": len(events),
        "trade_lines": len(trade_lines),
        "export_seq": export_seq,
    }
