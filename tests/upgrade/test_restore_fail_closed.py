"""UPG-03: restore_active_set fails closed before it writes any ledger row.

A restore by a caller that is not a human: or gate: writer, and a restore to a
prior hash with no valid stored content, both raise ValueError and append
nothing, so the live active set keeps its value. A writer restore to a recorded
set is applied and reads back. Offline only: temp ledger, no network.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pumpgrok.ledger.active_set import (
    ACTIVE_SET_KEY,
    read_active_param_set,
    read_active_set,
    record_active_set,
)
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.upgrade.params import ParamSet
from pumpgrok.upgrade.rollback import restore_active_set

SET_A = ParamSet(filter={"min_unique_buyers": 5})
SET_B = ParamSet(filter={"min_unique_buyers": 6})
OPERATOR = "human:RESTORE-TEST"
GATE = "gate:UPGRADE-GATE"
CORRELATION = "restore-fail-closed-test"
UNSTORED = hashlib.sha256(b"never recorded").hexdigest()
CONTENT_PREFIX = "active_param_set_content:"


def _record(store: LedgerStore, param_set: ParamSet, by: str, ts_utc: str) -> None:
    record_active_set(
        store,
        param_set,
        by,
        ts_utc=ts_utc,
        source="paper",
        correlation_id=CORRELATION,
    )


def _restore(store: LedgerStore, prior_hash: str, by: str, ts_utc: str) -> str:
    return restore_active_set(
        store,
        prior_hash,
        by,
        ts_utc=ts_utc,
        source="paper",
        correlation_id=CORRELATION,
    )


def test_non_writer_restore_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    """A caller that is not a human or gate writer appends no rows and changes nothing."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        _record(store, SET_A, OPERATOR, "2026-01-01T00:01:00Z")
        _record(store, SET_B, OPERATOR, "2026-01-01T00:02:00Z")
        before = store.count()
        with pytest.raises(ValueError):
            _restore(store, SET_A.content_hash, "bot-00-chief", "2026-01-01T00:03:00Z")
        assert store.count() == before
        assert read_active_set(store) == SET_B.content_hash
    finally:
        store.close()


def test_restore_to_unstored_hash_is_refused_and_writes_nothing(tmp_path: Path) -> None:
    """A well-formed hash with no stored content is refused before any row is written."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        _record(store, SET_A, OPERATOR, "2026-01-01T00:01:00Z")
        before = store.count()
        with pytest.raises(ValueError):
            _restore(store, UNSTORED, OPERATOR, "2026-01-01T00:02:00Z")
        assert store.count() == before
        assert read_active_set(store) == SET_A.content_hash
    finally:
        store.close()


@pytest.mark.parametrize(
    "stored",
    [
        "{not json",
        json.dumps({"filter": {"min_unique_buyers": "many"}}),
        json.dumps(SET_B.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
    ],
    ids=["invalid_json", "fails_paramset_checks", "valid_content_wrong_hash"],
)
def test_restore_to_corrupt_stored_content_is_refused_and_writes_nothing(
    tmp_path: Path, stored: str
) -> None:
    """Undecodable, ParamSet-invalid, or wrong-hash stored content is refused before any row."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        _record(store, SET_A, OPERATOR, "2026-01-01T00:01:00Z")
        _record(store, SET_B, OPERATOR, "2026-01-01T00:02:00Z")
        store.set_meta(f"{CONTENT_PREFIX}{SET_A.content_hash}", stored)
        before = store.count()
        with pytest.raises(ValueError):
            _restore(store, SET_A.content_hash, OPERATOR, "2026-01-01T00:03:00Z")
        assert store.count() == before
        assert read_active_set(store) == SET_B.content_hash
    finally:
        store.close()


def test_writer_restore_to_recorded_set_is_applied(tmp_path: Path) -> None:
    """A human writer restoring a recorded set appends the pair and reads back."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        _record(store, SET_A, OPERATOR, "2026-01-01T00:01:00Z")
        _record(store, SET_B, OPERATOR, "2026-01-01T00:02:00Z")
        before = store.count()
        restored = _restore(store, SET_A.content_hash, OPERATOR, "2026-01-01T00:03:00Z")
        assert restored == SET_A.content_hash
        assert store.count() == before + 2
        assert read_active_set(store) == SET_A.content_hash
    finally:
        store.close()


def test_restore_round_trips_a_b_a_order(tmp_path: Path) -> None:
    """Record A, record B, restore A by a gate writer: live reads back A in A, B, A order."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        _record(store, SET_A, OPERATOR, "2026-01-01T00:01:00Z")
        _record(store, SET_B, GATE, "2026-01-01T00:02:00Z")
        _restore(store, SET_A.content_hash, GATE, "2026-01-01T00:03:00Z")
        assert read_active_set(store) == SET_A.content_hash
        assert read_active_param_set(store) == SET_A
        hashes = [
            row["payload"]["new_hash"]
            for row in store.read(types=["ConfigChanged"], limit=None)
            if ACTIVE_SET_KEY in row["payload"].get("keys_changed", [])
        ]
        assert hashes == [SET_A.content_hash, SET_B.content_hash, SET_A.content_hash]
    finally:
        store.close()
