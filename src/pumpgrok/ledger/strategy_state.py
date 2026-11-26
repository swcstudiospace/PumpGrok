<<<<<<< HEAD
"""Ledger-backed per-strategy state and ticket attribution (STR-03).

Two row shapes, both JournalNote rows so the hash chain covers them like
every other ledger fact:

- Ticket attribution refs (note_kind="ticket", refs=[ticket_id]) name
  ``strategy <id> ticket <ticket> mint <mint>`` in the text. New
  strategies write one ref per placed order; legacy_screening writes
  none (returns None instead of a row), because the legacy path has no
  strategy identity of its own.
- Open positions (note_kind="note") name
  ``strategy-state <id> open <mint> <entry_price_lamports>`` or
  ``... close <mint>``; the reader folds opens and closes in ledger order.

Reads fail closed on corrupt rows: a malformed marker raises ValueError
rather than guessing. Money is integer lamports.
=======
"""Per-strategy state snapshots in the strategy_state sidecar table (STR-03).

One row per strategy id, replaced on each write. A snapshot is serialised as sorted JSON.
It allows floats, since tape timestamps are epoch seconds, and refuses NaN and infinity.
state_hash is the SHA-256 of those exact bytes; a row whose body no longer matches its
hash is refused on read. Snapshots sit outside the hash chain: no event type or field.
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
"""

from __future__ import annotations

<<<<<<< HEAD
import re
=======
import hashlib
import json
from collections.abc import Mapping
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
from typing import Any

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.ledger.store import LedgerStore

<<<<<<< HEAD
__all__ = [
    "CorruptStrategyState",
    "read_attribution_refs",
    "read_open_positions",
    "record_attribution_ref",
    "record_close",
    "record_open",
]

LEGACY_STRATEGY_ID = "legacy_screening"

_STATE_RE = re.compile(r"^strategy-state (\S+) (open|close) (\S+)(?: (-?\d+))?$")
_REF_RE = re.compile(r"^strategy (\S+) ticket (\S+) mint (\S+)$")


class CorruptStrategyState(PumpgrokError):
    """A strategy-state row does not match the marker shape."""

    code = "corrupt_strategy_state"


def _read_journal(store: LedgerStore) -> list[dict[str, Any]]:
    return store.read(types=["JournalNote"], limit=None)


def record_attribution_ref(
    store: LedgerStore,
    *,
    strategy_id: str,
    ticket_id: str,
    mint: str,
    ts_utc: str,
    source: str,
    correlation_id: str,
) -> str | None:
    """Write one ticket attribution ref; legacy_screening writes none.

    Returns the ticket id for new strategies, None for legacy (the
    caller sees the absence instead of a row).
    """
    if strategy_id == LEGACY_STRATEGY_ID:
        return None
    if not ticket_id or not mint:
        raise ValueError("an attribution ref names a ticket and a mint")
    store.append_batch(
        [
            {
                "ts_utc": ts_utc,
                "source": source,
                "correlation_id": correlation_id,
                "idempotency_key": f"strategy-ref|{strategy_id}|{ticket_id}|{ts_utc}",
                "type": "JournalNote",
                "payload": {
                    "source": source,
                    "seat": "desk",
                    "note_kind": "ticket",
                    "text": f"strategy {strategy_id} ticket {ticket_id} mint {mint}",
                    "refs": [ticket_id],
                },
            }
        ]
    )
    return ticket_id


def read_attribution_refs(store: LedgerStore, strategy_id: str) -> list[dict[str, str]]:
    """Every attribution ref for one strategy in ledger order."""
    refs: list[dict[str, str]] = []
    for row in _read_journal(store):
        payload = row.get("payload", {})
        if not isinstance(payload, dict) or payload.get("note_kind") != "ticket":
            continue
        text = str(payload.get("text", ""))
        match = _REF_RE.match(text)
        if match is None:
            continue
        ref_strategy, ticket_id, mint = match.groups()
        if ref_strategy != strategy_id:
            continue
        stored_refs = payload.get("refs") or []
        if not stored_refs or str(stored_refs[0]) != ticket_id:
            raise CorruptStrategyState(
                f"attribution ref for {strategy_id!r} carries mismatched refs"
            )
        refs.append({"ticket_id": ticket_id, "mint": mint})
    return refs


def record_open(
    store: LedgerStore,
    *,
    strategy_id: str,
    mint: str,
    entry_price_lamports: int,
    ts_utc: str,
    source: str,
    correlation_id: str,
) -> None:
    """Record one open position for a strategy."""
    if isinstance(entry_price_lamports, bool) or not isinstance(entry_price_lamports, int):
        raise ValueError("entry_price_lamports must be integer lamports")
    store.append_batch(
        [
            {
                "ts_utc": ts_utc,
                "source": source,
                "correlation_id": correlation_id,
                "idempotency_key": f"strategy-open|{strategy_id}|{mint}|{ts_utc}",
                "type": "JournalNote",
                "payload": {
                    "source": source,
                    "seat": "desk",
                    "note_kind": "note",
                    "text": f"strategy-state {strategy_id} open {mint} {entry_price_lamports}",
                    "refs": [],
                },
            }
        ]
    )


def record_close(
    store: LedgerStore,
    *,
    strategy_id: str,
    mint: str,
    ts_utc: str,
    source: str,
    correlation_id: str,
) -> None:
    """Close one open position for a strategy."""
    store.append_batch(
        [
            {
                "ts_utc": ts_utc,
                "source": source,
                "correlation_id": correlation_id,
                "idempotency_key": f"strategy-close|{strategy_id}|{mint}|{ts_utc}",
                "type": "JournalNote",
                "payload": {
                    "source": source,
                    "seat": "desk",
                    "note_kind": "note",
                    "text": f"strategy-state {strategy_id} close {mint}",
                    "refs": [],
                },
            }
        ]
    )


def read_open_positions(store: LedgerStore, strategy_id: str) -> list[dict[str, Any]]:
    """Open positions for one strategy in ledger order (fail closed).

    Every row whose text starts with ``strategy-state <id>`` must match
    the marker shape; anything else raises CorruptStrategyState.
    """
    open_positions: dict[str, int] = {}
    for row in _read_journal(store):
        payload = row.get("payload", {})
        if not isinstance(payload, dict):
            continue
        text = str(payload.get("text", ""))
        if not text.startswith("strategy-state "):
            continue
        parts = text.split(" ")
        if len(parts) < 3 or parts[1] != strategy_id:
            continue
        match = _STATE_RE.match(text)
        if match is None:
            raise CorruptStrategyState(f"malformed strategy-state row: {text!r}")
        _, action, mint, entry = match.groups()
        if action == "open":
            if entry is None:
                raise CorruptStrategyState(f"open row without entry price: {text!r}")
            open_positions[mint] = int(entry)
        else:
            open_positions.pop(mint, None)
    return [
        {"strategy_id": strategy_id, "mint": mint, "entry_price_lamports": price}
        for mint, price in open_positions.items()
    ]
=======
__all__ = ["StrategyStateError", "read_state", "state_hash", "write_state"]


class StrategyStateError(PumpgrokError):
    """A stored strategy snapshot does not match the hash recorded with it."""

    code = "strategy_state_error"


def _serialise(state: Mapping[str, Any]) -> str:
    return json.dumps(dict(state), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def write_state(store: LedgerStore, strategy_id: str, state: Mapping[str, Any]) -> str:
    """Store the strategy's snapshot, replacing any earlier one; returns its state hash."""
    if not strategy_id:
        raise ValueError("a strategy snapshot needs a strategy id")
    body = _serialise(state)
    digest = _digest(body)
    store._db.execute(
        "INSERT INTO strategy_state (strategy_id, state_json, state_hash) VALUES (?, ?, ?)"
        " ON CONFLICT(strategy_id) DO UPDATE SET"
        " state_json = excluded.state_json, state_hash = excluded.state_hash;",
        (strategy_id, body, digest),
    )
    return digest


def read_state(store: LedgerStore, strategy_id: str) -> dict[str, Any] | None:
    """The strategy's snapshot, or None when none was written. Refuses an altered row."""
    row = store._db.execute(
        "SELECT state_json, state_hash FROM strategy_state WHERE strategy_id = ?;",
        (strategy_id,),
    ).fetchone()
    if row is None:
        return None
    body, recorded = str(row[0]), str(row[1])
    if _digest(body) != recorded:
        raise StrategyStateError(f"strategy {strategy_id} snapshot does not match its hash")
    loaded: dict[str, Any] = json.loads(body)
    return loaded


def state_hash(store: LedgerStore, strategy_id: str) -> str | None:
    """The recorded hash of the strategy's snapshot, or None when none was written."""
    row = store._db.execute(
        "SELECT state_hash FROM strategy_state WHERE strategy_id = ?;", (strategy_id,)
    ).fetchone()
    return None if row is None else str(row[0])
>>>>>>> 02a755d6b17b7752d8a56fd3cfe0beb35def2687
