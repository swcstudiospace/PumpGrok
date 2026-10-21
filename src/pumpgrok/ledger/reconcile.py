"""Restart reconcile: snapshot plus tail replay plus verify (paper-engine.md 3.5, R26).

Restart order: latest snapshot (or genesis) -> tail replay through the
reducer fold -> chain verify -> integrity checks. Any failure reports
INCONSISTENT with the failing check; nothing is auto-repaired. Only
RiskEngine appends the ``HaltSet`` row (plan 04-05); its shape is defined
here so RiskEngine halts on exactly this shape.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pumpgrok.ledger.reducer import LedgerState, dump_state, initial_state, load_state, reduce
from pumpgrok.ledger.store import LedgerInconsistent, LedgerStore

CONSISTENT = "CONSISTENT"
INCONSISTENT = "INCONSISTENT"

HALT_REASON = "ledger_inconsistent"


def ledger_inconsistent_halt(
    *,
    ts_utc: str,
    source: str,
    correlation_id: str,
    detail: str,
    equity_lamports: int,
    day_start_equity_lamports: int,
) -> dict[str, Any]:
    """HaltSet row shape for a failed reconcile; appended by RiskEngine.

    Idempotency is per (reason, utc_day), so repeated observers of the same
    breach collapse onto one row (paper-engine.md 5.2).
    """
    day_utc = ts_utc[:10]
    key = hashlib.sha256(f"HaltSet|{HALT_REASON}|{day_utc}".encode()).hexdigest()
    return {
        "ts_utc": ts_utc,
        "source": source,
        "correlation_id": correlation_id,
        "idempotency_key": key,
        "type": "HaltSet",
        "payload": {
            "source": source,
            "reason": HALT_REASON,
            "detail": detail,
            "equity_lamports": equity_lamports,
            "day_start_equity_lamports": day_start_equity_lamports,
            "set_by": "risk_engine",
        },
    }


def _genesis(store: LedgerStore, events: list[dict[str, Any]]) -> LedgerState:
    meta_source = store.get_meta("source")
    meta_equity = store.get_meta("initial_equity_lamports")
    if events:
        first = events[0]
        source = meta_source or str(first.get("source", "paper"))
        day_utc = str(first.get("ts_utc", ""))[:10]
    else:
        source = meta_source or "paper"
        day_utc = ""
    return initial_state(
        source=source,
        initial_equity_lamports=int(meta_equity) if meta_equity is not None else 0,
        day_utc=day_utc,
    )


def reconcile(store: LedgerStore) -> dict[str, Any]:
    """Replay snapshot-plus-tail and verify; never repairs, only reports."""
    try:
        store.verify()
    except LedgerInconsistent as exc:
        return {
            "status": INCONSISTENT,
            "snapshot_seq": None,
            "tail_events": None,
            "head_seq": None,
            "detail": f"chain: {exc}",
        }
    snapshot = store.latest_snapshot()
    snapshot_seq = int(snapshot["seq"]) if snapshot is not None else 0
    base: LedgerState
    if snapshot is not None:
        base = load_state(snapshot["state"])
    else:
        base = _genesis(store, store.read(since_seq=1, limit=1))
    tail = store.read(since_seq=snapshot_seq + 1, limit=None)
    tail_state = base
    for event in tail:
        tail_state = reduce(tail_state, event)

    full_events = store.read(since_seq=1, limit=None)
    if not full_events:
        return {
            "status": CONSISTENT,
            "snapshot_seq": snapshot_seq,
            "tail_events": 0,
            "head_seq": 0,
            "state": dump_state(tail_state),
        }
    genesis = _genesis(store, full_events)
    full_state = genesis
    for event in full_events:
        full_state = reduce(full_state, event)

    check = _integrity_checks(store, snapshot, tail_state, full_state, full_events)
    if check is not None:
        return {
            "status": INCONSISTENT,
            "snapshot_seq": snapshot_seq,
            "tail_events": len(tail),
            "head_seq": full_events[-1]["seq"],
            "detail": check,
        }
    return {
        "status": CONSISTENT,
        "snapshot_seq": snapshot_seq,
        "tail_events": len(tail),
        "head_seq": full_events[-1]["seq"],
        "state": dump_state(tail_state),
    }


def _payload_int(event: dict[str, Any], key: str) -> int:
    """Integer payload field, defaulting to 0 for missing or unshaped rows."""
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return 0
    return int(payload.get(key, 0))


def _check_full_replay(tail_state: LedgerState, full_state: LedgerState) -> str | None:
    """6d: the snapshot-plus-tail fold equals the fold over all events."""
    tail_body = {k: v for k, v in dump_state(tail_state).items() if k != "meta"}
    full_body = {k: v for k, v in dump_state(full_state).items() if k != "meta"}
    if tail_body != full_body:
        return "tail replay state differs from full replay state"
    return None


def _check_cash(
    store: LedgerStore, tail_state: LedgerState, events: list[dict[str, Any]]
) -> str | None:
    """6a: cash equals initial equity plus fill deltas minus rejected fees."""
    meta_equity = store.get_meta("initial_equity_lamports")
    initial = int(meta_equity) if meta_equity is not None else 0
    cash_delta = sum(
        _payload_int(e, "cash_delta_lamports") for e in events if e.get("type") == "FillRecorded"
    )
    rejected_fees = sum(
        _payload_int(e, "fees_lamports") for e in events if e.get("type") == "OrderRejected"
    )
    if int(tail_state.cash_lamports) != initial + cash_delta - rejected_fees:
        return "cash equation failed: cash != initial + fills - rejected fees"
    return None


def _check_snapshot(store: LedgerStore, snapshot: dict[str, Any] | None) -> str | None:
    """6e: snapshot meta chain_hash matches events.hash at the snapshot seq."""
    if snapshot is None:
        return None
    snap_state = snapshot["state"]
    if not isinstance(snap_state, dict):
        return None
    chain_hash = snap_state.get("meta", {}).get("chain_hash")
    if chain_hash is None:
        return None
    row = store.read(since_seq=int(snapshot["seq"]), limit=1)
    head = next((e for e in row if e["seq"] == int(snapshot["seq"])), None)
    if head is None or head["hash"] != chain_hash:
        return "snapshot chain_hash does not match events.hash at snapshot seq"
    return None


def _check_source(store: LedgerStore, events: list[dict[str, Any]]) -> str | None:
    """6f: every event source matches the ledger meta source when set."""
    meta_source = store.get_meta("source")
    if meta_source is None:
        return None
    for event in events:
        if event.get("source") != meta_source:
            return f"event seq {event['seq']} source mixes ledger source {meta_source}"
    return None


def _check_positions(tail_state: LedgerState, events: list[dict[str, Any]]) -> str | None:
    """6b/6c: open units match summed fills; no close-then-hold anomaly."""
    units: dict[str, int] = {}
    last_open: dict[str, int] = {}
    last_close: dict[str, int] = {}
    for event in events:
        payload = event.get("payload")
        row = dict(payload) if isinstance(payload, dict) else {}
        if event.get("type") == "FillRecorded":
            key = str(row.get("mint", ""))
            delta = int(row.get("filled_units", 0))
            if str(row.get("side", "")) != "buy":
                delta = -delta
            units[key] = units.get(key, 0) + delta
        seq = int(event.get("seq", 0))
        if event.get("type") == "PositionOpened":
            last_open[str(row.get("mint", ""))] = seq
        elif event.get("type") == "PositionClosed":
            last_close[str(row.get("mint", ""))] = seq
    for mint, pos in tail_state.positions.items():
        if pos.token_units != units.get(mint, 0):
            return f"position {mint} units do not match summed fills"
    for mint in tail_state.positions:
        if mint in last_close and last_open.get(mint, 0) < last_close[mint]:
            return f"position {mint} closed with no newer open yet still held"
    return None


def _integrity_checks(
    store: LedgerStore,
    snapshot: dict[str, Any] | None,
    tail_state: LedgerState,
    full_state: LedgerState,
    full_events: list[dict[str, Any]],
) -> str | None:
    """Return the first failing check detail, or None when all hold."""
    for check in (
        _check_full_replay(tail_state, full_state),
        _check_cash(store, tail_state, full_events),
        _check_snapshot(store, snapshot),
        _check_source(store, full_events),
        _check_positions(tail_state, full_events),
    ):
        if check is not None:
            return check
    return None
