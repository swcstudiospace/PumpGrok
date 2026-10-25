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
from decimal import Decimal
from pathlib import Path
from typing import Any

from pumpgrok.core.idempotency import canonical_json
from pumpgrok.core.units import lamports_to_sol
from pumpgrok.ledger.store import LedgerStore

EXPORT_SEQ_KEY = "export_seq"
DRY_RUN_TX = "dry_run"


def _sol_str(lamports: int | str) -> str:
    """Integer lamports to an exact SOL decimal string (INT-01, no float division)."""
    return str(lamports_to_sol(Decimal(int(lamports))))


def _price_str(value: Any) -> str:
    """Scaled ledger price to an exact decimal price string (INT-01, no float division)."""
    return str(Decimal(str(value if value is not None else 0)) / 1000)


def _epoch(ts_utc: str) -> float:
    """ISO-8601 UTC stamp to epoch seconds (vendor ``ts`` is a float)."""
    parsed = datetime.fromisoformat(ts_utc.replace("Z", "+00:00"))
    return parsed.astimezone(UTC).timestamp()


def _exported_seqs(data: bytes) -> set[int]:
    """Seqs of the complete export records in one target's bytes.

    Export records carry ``type``. The journal.append tool writes a shorter
    ``kind`` line for the same seq, which is not an export record.
    """
    seqs: set[int] = set()
    for raw in data.splitlines():
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if isinstance(record, dict) and "type" in record and isinstance(record.get("seq"), int):
            seqs.add(record["seq"])
    return seqs


def _append_missing(path: Path, rows: list[tuple[int, str]]) -> int:
    """Append each ``(seq, line)`` the file does not yet hold; return how many were written.

    Targets are append-only and keyed by ledger seq, so a retry after an
    interrupted export finds the lines that landed and writes only the rest.
    A trailing fragment from an interrupted write is cut back to the last
    newline first, as ``tools.journal.append`` does, so new lines start clean.
    """
    if not rows:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as fh:
        fh.seek(0)
        data = fh.read()
        complete = data[: data.rfind(b"\n") + 1]
        present = _exported_seqs(complete)
        fresh = [line for seq, line in rows if seq not in present]
        if not fresh:
            return 0
        if len(complete) != len(data):
            fh.truncate(len(complete))
        fh.seek(0, os.SEEK_END)
        fh.write("".join(line + "\n" for line in fresh).encode("utf-8"))
        fh.flush()
        os.fsync(fh.fileno())
    return len(fresh)


def _journal_batches(events: list[dict[str, Any]]) -> dict[str, list[tuple[int, str]]]:
    by_day: dict[str, list[tuple[int, str]]] = {}
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
        by_day.setdefault(day, []).append((int(event["seq"]), line))
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
        "size_sol": _sol_str(payload.get("filled_lamports", 0)),
        "entry_price": _price_str(payload.get("price_avg", "0")),
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
        "entry_price": "0",
        "exit_price": _price_str(payload.get("price_exit", "0")),
        "pnl_sol": _sol_str(payload.get("realized_pnl_lamports", 0)),
        "pnl_pct": float(payload.get("pnl_pct", "0")),
        "hold_seconds": int(payload.get("hold_seconds", 0)),
        "reason": str(payload.get("reason", "")),
        # Bare tx_hash keeps the evidence tooling matching; the unique paper
        # ref rides alongside per paper-engine 964.
        "tx_hash": DRY_RUN_TX,
        "venue_tx_ref": str(payload.get("venue_tx_ref", "")),
        "score": 0,
    }


def _trade_lines(events: list[dict[str, Any]]) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for event in events:
        seq = int(event["seq"])
        if event.get("type") == "FillRecorded" and event["payload"].get("side") == "buy":
            lines.append((seq, json.dumps(_buy_line(event), ensure_ascii=False)))
        elif event.get("type") == "OrderRejected":
            lines.append((seq, json.dumps(_skip_line(event), ensure_ascii=False)))
        elif event.get("type") == "PositionClosed":
            lines.append((seq, json.dumps(_close_line(event), ensure_ascii=False)))
    return lines


def export_ledger(
    store: LedgerStore, *, journal_dir: str | Path, trades_path: str | Path
) -> dict[str, Any]:
    """Export both targets under the single export_seq cursor.

    Every target line is keyed by ledger seq and written at most once, so a
    retry after a failed write or a crash before the cursor update completes
    the export without duplicate rows. Counts are the lines this call wrote;
    a second run with no new rows writes nothing and keeps the cursor.
    """
    export_seq = int(store.get_meta(EXPORT_SEQ_KEY) or "0")
    events = store.read(since_seq=export_seq + 1, limit=None)
    journal_lines = 0
    for day, rows in sorted(_journal_batches(events).items()):
        journal_lines += _append_missing(Path(journal_dir) / f"{day}.jsonl", rows)
    trade_lines = _append_missing(Path(trades_path), _trade_lines(events))
    if events:
        store.set_meta(EXPORT_SEQ_KEY, str(events[-1]["seq"]))
        export_seq = int(events[-1]["seq"])
    return {
        "journal_lines": journal_lines,
        "trade_lines": trade_lines,
        "export_seq": export_seq,
    }
