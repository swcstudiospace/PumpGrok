"""Active parameter-set record (UPG-01, UPG-03).

The active set lives in the ledger, never in config: ``record_active_set``
appends a ``ConfigChanged`` row (``keys_changed=["active_param_set"]``, prior
hash in ``old_hash``, new hash in ``new_hash``, ``by`` a human or the gate)
plus a ``JournalNote`` (seat ``desk``, ``note_kind="note"``, text naming the
new hash and its source) so the journal records every activation. The reader
scans ``ConfigChanged`` rows in ledger order; the last valid row wins, ``None``
when never set. JournalNote text is never read as policy. Live mode callers
keep the existing forced manual-ticket path untouched.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore
    from pumpgrok.upgrade.params import ParamSet

__all__ = [
    "ACTIVE_SET_KEY",
    "active_set_note_text",
    "active_set_rows",
    "read_active_set",
    "record_active_set",
]

ACTIVE_SET_KEY = "active_param_set"

_HASH_RE = re.compile(r"[0-9a-f]{64}")


def active_set_note_text(new_hash: str, source: str) -> str:
    """Journal text for an activation (names the new hash and its source)."""
    return f"active_param_set {new_hash} from {source}"


def _is_writer(by: object) -> bool:
    """Only human or gate-written rows count, mirroring the autonomy by rule."""
    return isinstance(by, str) and (by.startswith("human:") or by.startswith("gate:"))


def read_active_set(store: LedgerStore) -> str | None:
    """Latest valid ``ConfigChanged`` active-set hash; ``None`` when never set.

    Only rows with ``active_param_set`` in ``keys_changed``, a 64-hex hash in
    ``new_hash`` and a human or gate ``by`` count. JournalNote text is
    free-form seat output and is never read as policy.
    """
    active: str | None = None
    for event in store.read(types=["ConfigChanged"], limit=None):
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        keys = payload.get("keys_changed")
        new_hash = payload.get("new_hash")
        by = payload.get("by")
        if not isinstance(keys, list) or ACTIVE_SET_KEY not in keys:
            continue
        if not isinstance(new_hash, str) or not _HASH_RE.fullmatch(new_hash):
            continue
        if not _is_writer(by):
            continue
        active = new_hash
    return active


def active_set_rows(
    param_set: ParamSet,
    by: str,
    *,
    previous: str,
    ts_utc: str,
    source: str,
    correlation_id: str,
) -> list[dict[str, Any]]:
    """Build the ``ConfigChanged`` + ``JournalNote`` pair for an activation."""
    new_hash = param_set.content_hash
    return [
        {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": f"active-param-set|{new_hash}|{ts_utc}",
            "type": "ConfigChanged",
            "payload": {
                "source": source,
                "by": by,
                "keys_changed": [ACTIVE_SET_KEY],
                "old_hash": previous,
                "new_hash": new_hash,
            },
        },
        {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": f"active-param-set-note|{new_hash}|{ts_utc}",
            "type": "JournalNote",
            "payload": {
                "source": source,
                "seat": "desk",
                "note_kind": "note",
                "text": active_set_note_text(new_hash, source),
                "refs": [],
            },
        },
    ]


def record_active_set(
    store: LedgerStore,
    param_set: ParamSet,
    by: str,
    *,
    ts_utc: str,
    source: str,
    correlation_id: str,
) -> str:
    """Append the activation pair for ``param_set``; return its content hash."""
    previous = read_active_set(store)
    store.append_batch(
        active_set_rows(
            param_set,
            by,
            previous=previous or "",
            ts_utc=ts_utc,
            source=source,
            correlation_id=correlation_id,
        )
    )
    return param_set.content_hash
