"""Replay-only operator grants (Phase 14 owner decision).

The replay sandbox is hermetic: it has no operator key and reads no production authority
(``var/operator`` and the live ledger are never touched). Before the replay registry is built,
every roster tool of every seat gets one ``ConfigChanged`` row in the replay ledger. The row is
labelled ``by=replay:seed``, never a ``human:`` label, and carries no protected record. The
replay gate, :class:`ReplayGrants`, admits a ``(seat, tool)`` only when the replay ledger holds
that seeded ``allow`` row. Seeding is deterministic: the timestamp is the fixture's first stamp
and the idempotency keys are fixed per seat and tool.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from pumpgrok.core.idempotency import canonical_json
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.ledger.store import LedgerStore

__all__ = ["REPLAY_GRANT_BY", "REPLAY_GRANT_PREFIX", "ReplayGrants", "seed_replay_grants"]

REPLAY_GRANT_BY = "replay:seed"
REPLAY_GRANT_PREFIX = "replay_grant:tool:"
_CORRELATION = "replay-grant"


def _grant_key(seat: str, tool: str) -> str:
    return f"{REPLAY_GRANT_PREFIX}{seat}:{tool}"


def _seeded_pairs(rows: Iterable[Mapping[str, Any]]) -> frozenset[tuple[str, str]]:
    """The (seat, tool) pairs that carry a replay-seed grant row in the ledger."""
    pairs: set[tuple[str, str]] = set()
    for row in rows:
        payload = row.get("payload")
        if not isinstance(payload, Mapping) or payload.get("by") != REPLAY_GRANT_BY:
            continue
        keys = payload.get("keys_changed")
        if not isinstance(keys, list) or len(keys) != 1 or not isinstance(keys[0], str):
            continue
        if not keys[0].startswith(REPLAY_GRANT_PREFIX):
            continue
        seat, _, tool = keys[0].removeprefix(REPLAY_GRANT_PREFIX).partition(":")
        if seat and tool:
            pairs.add((seat, tool))
    return frozenset(pairs)


def seed_replay_grants(store: LedgerStore, *, ts_utc: str, contracts_dir: Path) -> int:
    """Append one replay ``allow`` row per (seat, roster tool) not already in the ledger.

    Returns the number of rows appended. Re-running over a ledger that already holds the
    seeded rows appends nothing, so the seeded chain stays the same.
    """
    existing = {
        row.get("idempotency_key")
        for row in store.read(types=["ConfigChanged"], limit=None)
    }
    rows: list[dict[str, Any]] = []
    for seat in sorted(EXPECTED_SEAT_IDS):
        for tool in sorted(roster_tool_names(contracts_dir, seat)):
            body = {
                "v": 1,
                "kind": "replay_grant",
                "seat": seat,
                "tool": tool,
                "by": REPLAY_GRANT_BY,
                "at": ts_utc,
            }
            digest = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
            idempotency_key = f"{_CORRELATION}|{seat}|{tool}"
            if idempotency_key in existing:
                continue
            rows.append(
                {
                    "ts_utc": ts_utc,
                    "source": "replay",
                    "correlation_id": _CORRELATION,
                    "idempotency_key": idempotency_key,
                    "type": "ConfigChanged",
                    "payload": {
                        "source": "replay",
                        "by": REPLAY_GRANT_BY,
                        "keys_changed": [_grant_key(seat, tool)],
                        "old_hash": "",
                        "new_hash": digest,
                    },
                }
            )
    if rows:
        store.append_batch(rows)
    return len(rows)


class ReplayGrants:
    """Replay gate: admits a (seat, tool) only when the replay ledger holds its seeded allow row."""

    def __init__(self, store: LedgerStore) -> None:
        rows = store.read(types=["ConfigChanged"], limit=None)
        self._allowed = _seeded_pairs(rows)

    def allows(self, seat: str, tool: str) -> bool:
        return (seat, tool) in self._allowed
