"""Active parameter-set record (UPG-01, UPG-03).

The active set lives in the ledger, never in config: ``record_active_set``
appends a ``ConfigChanged`` row (``keys_changed=["active_param_set"]``, prior
hash in ``old_hash``, new hash in ``new_hash``, ``by`` a human or the gate)
plus a ``JournalNote`` (seat ``desk``, ``note_kind="note"``, text naming the
new hash and its source) so the journal records every activation. The reader
scans ``ConfigChanged`` rows in ledger order; the last valid row wins, ``None``
when never set. JournalNote text is never read as policy. Live mode callers
keep the existing forced manual-ticket path untouched.

Each recorded set's canonical JSON is stored in the ledger meta table under
``active_param_set_content:<content_hash>``, written before its ConfigChanged
row. ``read_active_param_set`` loads and verifies that content, so a restored
hash runs the exact overrides it names. Missing, undecodable, or mismatched
content raises CorruptState instead of falling back to the desk defaults.
The first promotion also stores ``GENESIS_PARAM_SET`` (the desk defaults, no
overrides) under its own hash, so the genesis set stays restorable; a ledger
without that content refuses a rollback to it.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from pumpgrok.core.errors import CorruptState
from pumpgrok.upgrade.params import ParamSet

if TYPE_CHECKING:
    from pumpgrok.ledger.store import LedgerStore

__all__ = [
    "ACTIVE_SET_KEY",
    "GENESIS_PARAM_SET",
    "active_set_note_text",
    "active_set_rows",
    "is_writer",
    "load_verified_param_set",
    "read_active_param_set",
    "read_active_set",
    "record_active_set",
    "verify_stored_content",
]

ACTIVE_SET_KEY = "active_param_set"
_CONTENT_KEY_PREFIX = "active_param_set_content:"

# Desk defaults: the set the desk runs before any promotion (no overrides).
GENESIS_PARAM_SET = ParamSet()

_HASH_RE = re.compile(r"[0-9a-f]{64}")


def active_set_note_text(new_hash: str, source: str) -> str:
    """Journal text for an activation (names the new hash and its source)."""
    return f"active_param_set {new_hash} from {source}"


def is_writer(by: object) -> bool:
    """Only human or gate-written rows count, mirroring the autonomy by rule."""
    return isinstance(by, str) and (by.startswith("human:") or by.startswith("gate:"))


def _content_key(content_hash: str) -> str:
    """Meta key holding the canonical JSON of one recorded set."""
    return f"{_CONTENT_KEY_PREFIX}{content_hash}"


def _decode_param_set(raw: str) -> ParamSet:
    """Decode canonical JSON into a validated ParamSet; bad input raises ValueError."""
    return ParamSet.model_validate(json.loads(raw))


def _canonical_param_set(param_set: ParamSet) -> str:
    """Canonical JSON of one set, refused unless it decodes back to the same hash."""
    text = json.dumps(param_set.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    if _decode_param_set(text).content_hash != param_set.content_hash:
        raise ValueError("param set does not round-trip through canonical JSON")
    return text


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
        if not is_writer(by):
            continue
        active = new_hash
    return active


def read_active_param_set(store: LedgerStore) -> ParamSet | None:
    """Content of the latest recorded active set, or ``None`` when never set.

    Verifies the recorded content through ``load_verified_param_set``. A
    recorded set whose content is missing, undecodable, or different from its
    hash raises CorruptState, so the desk never runs overrides it cannot verify.
    """
    active = read_active_set(store)
    if active is None:
        return None
    return load_verified_param_set(store, active)


def load_verified_param_set(store: LedgerStore, content_hash: str) -> ParamSet:
    """Load one recorded set; its content must decode to exactly that hash.

    Missing, undecodable, or mismatched content raises CorruptState. Shared by
    the startup reader and rollback, so both refuse the same bad content.
    """
    raw = store.get_meta(_content_key(content_hash))
    if raw is None:
        raise CorruptState(f"param set {content_hash} is recorded without its content")
    try:
        param_set = _decode_param_set(raw)
        matches = param_set.content_hash == content_hash
    except (TypeError, ValueError) as exc:
        raise CorruptState(f"param set {content_hash} content is undecodable: {exc}") from exc
    if not matches:
        raise CorruptState(f"param set {content_hash} content does not match its hash")
    return param_set


def verify_stored_content(store: LedgerStore, content_hash: str) -> None:
    """Refuse unless the canonical JSON stored under content_hash decodes to that hash.

    Raises ValueError when nothing is stored, when the stored text does not
    decode into a ParamSet, or when the decoded set hashes to something else.
    """
    raw = store.get_meta(_content_key(content_hash))
    if raw is None:
        raise ValueError(f"active param set {content_hash} has no stored content")
    try:
        matches = _decode_param_set(raw).content_hash == content_hash
    except (TypeError, ValueError) as exc:
        raise ValueError(f"active param set {content_hash} content is undecodable") from exc
    if not matches:
        raise ValueError(f"active param set {content_hash} content does not match its hash")


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
    """Store the content under its hash, then append the activation pair.

    The canonical JSON is written before the ConfigChanged row, so every
    recorded activation has its content on file; the first promotion also stores the
    genesis content it can roll back to. Return the content hash.
    """
    new_hash = param_set.content_hash
    store.set_meta(_content_key(new_hash), _canonical_param_set(param_set))
    previous = read_active_set(store)
    if previous is None:
        # The desk runs GENESIS_PARAM_SET before any promotion: store its content
        # so the first promotion can be rolled back to it. old_hash stays "" here.
        store.set_meta(
            _content_key(GENESIS_PARAM_SET.content_hash),
            _canonical_param_set(GENESIS_PARAM_SET),
        )
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
    return new_hash
