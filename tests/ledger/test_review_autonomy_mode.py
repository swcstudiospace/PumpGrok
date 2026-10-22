"""Autonomy mode comes only from operator ConfigChanged rows (review finding 2).

A seat can append journal text through journal.append. Text such as
``autonomy autonomous-paper by human:x`` must not enable autonomous approvals.
"""

from __future__ import annotations

from pathlib import Path

from pumpgrok.ledger.autonomy import autonomy_rows, read_autonomy
from pumpgrok.ledger.store import LedgerStore

_TS = "2026-01-01T00:00:00.000001Z"
_CORR = "01J0000000000000000000000"


def _seat_journal_note(text: str, idem: str) -> dict[str, object]:
    return {
        "ts_utc": _TS,
        "source": "paper",
        "correlation_id": _CORR,
        "idempotency_key": idem,
        "type": "JournalNote",
        "payload": {
            "source": "paper",
            "seat": "bot-04-sniper",
            "note_kind": "note",
            "text": text,
            "refs": [],
        },
    }


def _store(tmp_path: Path) -> LedgerStore:
    return LedgerStore(tmp_path / "ledger.sqlite")


def _operator_change(policy: str, ts_utc: str) -> list[dict[str, object]]:
    return autonomy_rows(
        policy,
        "human:alice",
        previous="manual-ticket",
        ts_utc=ts_utc,
        source="paper",
        correlation_id="desk",
    )


def test_unset_ledger_defaults_to_manual_ticket(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        assert read_autonomy(store) == "manual-ticket"
    finally:
        store.close()


def test_seat_journal_text_cannot_enable_autonomous_paper(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.append(**_seat_journal_note("autonomy autonomous-paper by human:alice", "seat-1"))
        assert read_autonomy(store) == "manual-ticket"
    finally:
        store.close()


def test_seat_journal_text_cannot_override_operator_level(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.append_batch(_operator_change("autonomous-paper", _TS))
        assert read_autonomy(store) == "autonomous-paper"
        store.append(**_seat_journal_note("autonomy manual-ticket by human:bob", "seat-2"))
        assert read_autonomy(store) == "autonomous-paper"
    finally:
        store.close()


def test_operator_change_is_honoured_and_last_wins(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.append_batch(_operator_change("autonomous-paper", "2026-01-01T00:00:01.000001Z"))
        store.append_batch(_operator_change("manual-ticket", "2026-01-01T00:00:02.000001Z"))
        assert read_autonomy(store) == "manual-ticket"
    finally:
        store.close()


def test_config_changed_without_human_signer_is_ignored(tmp_path: Path) -> None:
    store = _store(tmp_path)
    try:
        store.append(
            ts_utc=_TS,
            source="paper",
            correlation_id=_CORR,
            idempotency_key="forged-1",
            type="ConfigChanged",
            payload={
                "source": "paper",
                "by": "bot-04-sniper",
                "keys_changed": ["autonomy_level"],
                "old_hash": "manual-ticket",
                "new_hash": "autonomous-paper",
            },
        )
        assert read_autonomy(store) == "manual-ticket"
    finally:
        store.close()
