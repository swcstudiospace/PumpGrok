"""Restart reconcile: snapshot plus tail replay plus verify (paper-engine.md 3.5, R26).

The tracer path replays the tail after the latest snapshot and verifies the
hash chain. The full fold through the reducer and the integrity checks land in
the batch task; the status contract (CONSISTENT / INCONSISTENT) is fixed here.
"""

from __future__ import annotations

from typing import Any

from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore

CONSISTENT = "CONSISTENT"
INCONSISTENT = "INCONSISTENT"


def reconcile(store: LedgerStore) -> dict[str, Any]:
    """Replay snapshot-plus-tail and verify; never repairs, only reports.

    Returns ``status`` CONSISTENT with the snapshot seq and tail size, or
    INCONSISTENT with the check detail. Callers decide the halt response;
    only RiskEngine appends ``HaltSet`` (plan 04-05).
    """
    snapshot = store.latest_snapshot()
    snapshot_seq = int(snapshot["seq"]) if snapshot is not None else 0
    tail = store.read(since_seq=snapshot_seq + 1, limit=None)
    try:
        store.verify()
    except LedgerInconsistent as exc:
        return {
            "status": INCONSISTENT,
            "snapshot_seq": snapshot_seq,
            "tail_events": len(tail),
            "detail": str(exc),
        }
    head_seq = tail[-1]["seq"] if tail else snapshot_seq
    return {
        "status": CONSISTENT,
        "snapshot_seq": snapshot_seq,
        "tail_events": len(tail),
        "head_seq": head_seq,
    }
