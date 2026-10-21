"""Autonomy level persistence (paper-engine.md 7.5, R17, R40).

The level lives in the ledger, never in config: ``state autonomy`` appends
a ``ConfigChanged`` row (``keys_changed=["autonomy_level"]``, old policy in
``old_hash``, new policy in ``new_hash``) plus a ``JournalNote`` (seat
``desk``, ``note_kind="note"``, text ``autonomy <policy> by <by>``) so the
journal records every level change. The reader scans the autonomy notes in
ledger order; the last one wins, default ``manual-ticket``. Live mode always
forces ``manual-ticket`` at registry build, regardless of the ledger.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

AUTONOMY_LEVELS: tuple[str, str] = ("manual-ticket", "autonomous-paper")

_AUTONOMY_RE = re.compile(r"^autonomy (manual-ticket|autonomous-paper)\b")


def autonomy_note_text(policy: str, by: str) -> str:
    """Journal text for a level change (the ``^autonomy <policy>`` convention)."""
    return f"autonomy {policy} by {by}"


def read_autonomy(store: LedgerStore) -> str:
    """Latest ledger autonomy level; ``manual-ticket`` when never set."""
    level = "manual-ticket"
    for event in store.read(limit=None):
        if event.get("type") != "JournalNote":
            continue
        payload = event.get("payload", {})
        if not isinstance(payload, dict):
            continue
        match = _AUTONOMY_RE.match(str(payload.get("text", "")))
        if match is not None:
            level = match.group(1)
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
