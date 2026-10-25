"""Escalation for ineligible candidates (UPG-04; CONTEXT D-06, G-10, G-08).

escalate_candidate takes a blocked gate verdict and appends an Escalation
event plus a JournalNote decision request, both naming the candidate hash
and the single blocking reason from the gate order. Nothing is promoted
and no active-set row is written.

It follows the existing escalation channel in docs/RISK_POLICY.md
section 5: the supervisor relays Escalation rows to notify.alert, whose
destinations are the configured allowlist.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from pumpgrok.upgrade.gate import REASON_PASS, GateReason, GateVerdict

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

__all__ = [
    "ESCALATION_KIND",
    "ESCALATION_SEAT",
    "escalate_candidate",
    "escalation_detail_text",
    "escalation_note_text",
]

#: Escalation kind for a gate-blocked upgrade candidate.
ESCALATION_KIND = "upgrade_blocked"

#: Seat credited with the escalation row and the decision-request note.
ESCALATION_SEAT = "desk"

_HASH_RE = re.compile(r"[0-9a-f]{64}")


def escalation_detail_text(candidate_hash: str, reason: GateReason, detail: str) -> str:
    """Escalation detail naming the candidate hash and its blocking reason."""
    return f"candidate {candidate_hash} blocked: {reason} ({detail})"


def escalation_note_text(candidate_hash: str, reason: GateReason, detail: str) -> str:
    """Decision-request note naming the candidate hash and its blocking reason."""
    return f"upgrade decision requested for {candidate_hash}: blocked by {reason} ({detail})"


def escalate_candidate(
    store: LedgerStore,
    verdict: GateVerdict,
    *,
    candidate_hash: str,
    ts_utc: str,
    source: str,
    correlation_id: str,
) -> GateReason:
    """Escalate a blocked candidate; return its blocking reason.

    Appends one Escalation row (kind upgrade_blocked) plus one desk
    JournalNote decision request, both naming the candidate hash and the
    single blocking reason. Writes no active-set row and promotes nothing.
    Fails closed when the verdict is eligible or the hash is malformed,
    writing nothing in either case.
    """
    if not isinstance(candidate_hash, str) or not _HASH_RE.fullmatch(candidate_hash):
        raise ValueError("candidate_hash must be a 64-hex content hash")
    if verdict.promotion_eligible or verdict.reason == REASON_PASS:
        raise ValueError("verdict is eligible: nothing to escalate")
    rows: list[dict[str, Any]] = [
        {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": f"upgrade-escalation|{candidate_hash}|{ts_utc}",
            "type": "Escalation",
            "payload": {
                "source": source,
                "kind": ESCALATION_KIND,
                "seat": ESCALATION_SEAT,
                "detail": escalation_detail_text(candidate_hash, verdict.reason, verdict.detail),
            },
        },
        {
            "ts_utc": ts_utc,
            "source": source,
            "correlation_id": correlation_id,
            "idempotency_key": f"upgrade-escalation-note|{candidate_hash}|{ts_utc}",
            "type": "JournalNote",
            "payload": {
                "source": source,
                "seat": ESCALATION_SEAT,
                "note_kind": "note",
                "text": escalation_note_text(candidate_hash, verdict.reason, verdict.detail),
                "refs": [],
            },
        },
    ]
    store.append_batch(rows)
    return verdict.reason
