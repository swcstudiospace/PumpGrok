"""Exact one-operation rollback (UPG-03; CONTEXT D-05, G-07).

restore_active_set writes the prior content hash as a new ConfigChanged
active-set row plus a ledger JournalNote, so the ledger keeps the full
promotion history while the live value is exactly the prior content.
No path in this module alters bounds, trials, or autonomy: it reads only
the current active hash and appends only the active-set pair.

Hashes are identity only: they name exact sets and never act as a score,
a metric, or a verdict.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from pumpgrok.ledger.active_set import (
    ACTIVE_SET_KEY,
    is_writer,
    read_active_set,
    verify_stored_content,
)

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

__all__ = [
    "restore_active_set",
    "rollback_note_text",
]

_HASH_RE = re.compile(r"[0-9a-f]{64}")


def rollback_note_text(prior_hash: str, source: str) -> str:
    """Journal text for a rollback (names the restored hash and its source)."""
    return f"rollback active_param_set {prior_hash} from {source}"


def restore_active_set(
    store: LedgerStore,
    prior_hash: str,
    by: str,
    *,
    ts_utc: str,
    source: str,
    correlation_id: str,
) -> str:
    """Restore the prior active set in one operation; return its content hash.

    Appends a ConfigChanged row (keys_changed holding active_param_set,
    old_hash the current live hash, new_hash the exact prior hash) plus a
    desk JournalNote, so the restore is itself ledger history. Fails closed
    before any append, and writes nothing, on a malformed prior hash, on a
    caller that is not a human: or gate: writer, and on a prior hash with no
    valid stored content.
    """
    if not isinstance(prior_hash, str) or not _HASH_RE.fullmatch(prior_hash):
        raise ValueError("prior_hash must be a 64-hex content hash")
    if not is_writer(by):
        raise ValueError("restore needs a human: or gate: writer")
    verify_stored_content(store, prior_hash)
    previous = read_active_set(store)
    rows: list[dict[str, Any]] = [
        {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": f"rollback-active-param-set|{prior_hash}|{ts_utc}",
            "type": "ConfigChanged",
            "payload": {
                "source": source,
                "by": by,
                "keys_changed": [ACTIVE_SET_KEY],
                "old_hash": previous or "",
                "new_hash": prior_hash,
            },
        },
        {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": f"rollback-active-param-set-note|{prior_hash}|{ts_utc}",
            "type": "JournalNote",
            "payload": {
                "source": source,
                "seat": "desk",
                "note_kind": "note",
                "text": rollback_note_text(prior_hash, source),
                "refs": [],
            },
        },
    ]
    store.append_batch(rows)
    return prior_hash
