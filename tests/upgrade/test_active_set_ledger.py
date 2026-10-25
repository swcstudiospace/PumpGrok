"""UPG-01, UPG-03: the ledger records the active parameter set.

Recording two distinct parameter sets writes two active-set ConfigChanged
rows (plus one desk JournalNote each); read_active_set returns the second
hash; each stored hash equals param_set_hash of the set bytes; a fresh
ledger reads as no active set. Seat-written rows and JournalNote text never
count as policy. Offline only: temp ledger, no network.
"""

from __future__ import annotations

from pumpgrok.backtest.manifest import param_set_hash
from pumpgrok.core.idempotency import canonical_json
from pumpgrok.ledger.active_set import read_active_set, record_active_set
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.upgrade.params import ParamSet


def _set_bytes(param_set: ParamSet) -> bytes:
    """The exact bytes the identity hash covers (int leaves need no mapping)."""
    payload = {
        "exits": dict(param_set.exits or {}),
        "filter": dict(param_set.filter or {}),
    }
    return canonical_json(payload).encode("utf-8")


def test_two_records_second_wins(tmp_path) -> None:
    """Two activations leave two ConfigChanged rows; the reader takes the last."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        first = ParamSet(filter={"min_unique_buyers": 5})
        second = ParamSet(filter={"min_unique_buyers": 6})

        record_active_set(
            store,
            first,
            "human:UPGRADE-TEST",
            ts_utc="2026-01-01T00:00:00Z",
            source="paper",
            correlation_id="upgrade-test-1",
        )
        record_active_set(
            store,
            second,
            "gate:UPGRADE-GATE",
            ts_utc="2026-01-01T00:01:00Z",
            source="paper",
            correlation_id="upgrade-test-2",
        )

        changes = [
            row
            for row in store.read(types=["ConfigChanged"], limit=None)
            if "active_param_set" in row["payload"].get("keys_changed", [])
        ]
        assert len(changes) == 2
        assert store.count() == 4

        assert read_active_set(store) == second.content_hash
        assert changes[0]["payload"]["new_hash"] == param_set_hash(_set_bytes(first))
        assert changes[1]["payload"]["new_hash"] == param_set_hash(_set_bytes(second))
        assert changes[1]["payload"]["old_hash"] == first.content_hash

        notes = store.read(types=["JournalNote"], limit=None)
        assert len(notes) == 2
        assert all(note["payload"]["seat"] == "desk" for note in notes)
        assert second.content_hash in notes[1]["payload"]["text"]
    finally:
        store.close()


def test_fresh_ledger_has_no_active_set(tmp_path) -> None:
    """An empty ledger reads as no active set."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        assert read_active_set(store) is None
    finally:
        store.close()


def test_seat_row_and_note_text_are_not_policy(tmp_path) -> None:
    """A seat-written ConfigChanged row is ignored; notes never read as policy."""
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        params = ParamSet(filter={"min_unique_buyers": 5})
        store.append_batch(
            [
                {
                    "ts_utc": "2026-01-01T00:00:00Z",
                    "source": "paper",
                    "correlation_id": "upgrade-test-seat",
                    "idempotency_key": "seat-row",
                    "type": "ConfigChanged",
                    "payload": {
                        "source": "paper",
                        "by": "desk",
                        "keys_changed": ["active_param_set"],
                        "old_hash": "",
                        "new_hash": params.content_hash,
                    },
                },
                {
                    "ts_utc": "2026-01-01T00:00:00Z",
                    "source": "paper",
                    "correlation_id": "upgrade-test-seat",
                    "idempotency_key": "seat-note",
                    "type": "JournalNote",
                    "payload": {
                        "source": "paper",
                        "seat": "desk",
                        "note_kind": "note",
                        "text": f"active_param_set {params.content_hash} from paper",
                        "refs": [],
                    },
                },
            ]
        )
        assert read_active_set(store) is None
    finally:
        store.close()
