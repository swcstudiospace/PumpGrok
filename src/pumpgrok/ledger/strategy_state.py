"""Per-strategy state snapshots in the strategy_state sidecar table (STR-03).

One row per strategy id, replaced on each write. A snapshot is serialised as sorted JSON.
It allows floats, since tape timestamps are epoch seconds, and refuses NaN and infinity.
state_hash is the SHA-256 of those exact bytes; a row whose body no longer matches its
hash is refused on read. Snapshots sit outside the hash chain: no event type or field.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from pumpgrok.core.errors import PumpgrokError
from pumpgrok.ledger.store import LedgerStore

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
