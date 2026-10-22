"""Autonomy level persistence (paper-engine.md 7.5, R17, R40).

The level lives in the ledger, never in config: ``state autonomy`` appends
a ``ConfigChanged`` row (``keys_changed=["autonomy_level"]``, old policy in
``old_hash``, new policy in ``new_hash``, ``by`` a human) plus a ``JournalNote``
(seat ``desk``, ``note_kind="note"``, text ``autonomy <policy> by <by>``) so the
journal records every level change. Seats cannot append ``ConfigChanged``
(journal.append accepts only journal_note and escalation), so that row is the
operator-only record. The reader scans ``ConfigChanged`` rows in ledger order;
the last valid one wins, default ``manual-ticket``. Journal text is never read
as policy. Live mode always forces ``manual-ticket`` at registry build,
regardless of the ledger.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

AUTONOMY_LEVELS: tuple[str, str] = ("manual-ticket", "autonomous-paper")


def autonomy_note_text(policy: str, by: str) -> str:
    """Journal text for a level change (the ``^autonomy <policy>`` convention)."""
    return f"autonomy {policy} by {by}"


def read_autonomy(store: LedgerStore) -> str:
    """Latest operator ``ConfigChanged`` autonomy level; ``manual-ticket`` when never set.

    Only ``ConfigChanged`` rows with ``autonomy_level`` in ``keys_changed``, a
    valid policy in ``new_hash`` and a human ``by`` count. JournalNote text is
    free-form seat output and is never read as policy.
    """
    level = "manual-ticket"
    for event in store.read(types=["ConfigChanged"], limit=None):
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        keys = payload.get("keys_changed")
        policy = payload.get("new_hash")
        by = payload.get("by")
        if not isinstance(keys, list) or "autonomy_level" not in keys:
            continue
        if policy not in AUTONOMY_LEVELS or not str(by or "").startswith("human:"):
            continue
        level = str(policy)
    return level


def autonomy_rows(
    policy: str,
    by: str,
    *,
    previous: str,
    ts_utc: str,
    source: str,
    correlation_id: str,
) -> list[dict[str, Any]]:
    return [
        {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": f"autonomy|{policy}|{ts_utc}",
            "type": "ConfigChanged",
            "payload": {
                "source": source,
                "by": by,
                "keys_changed": ["autonomy_level"],
                "old_hash": previous,
                "new_hash": policy,
            },
        },
        {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": f"autonomy-note|{policy}|{ts_utc}",
            "type": "JournalNote",
            "payload": {
                "source": source,
                "seat": "desk",
                "note_kind": "note",
                "text": autonomy_note_text(policy, by),
                "refs": [],
            },
        },
    ]
