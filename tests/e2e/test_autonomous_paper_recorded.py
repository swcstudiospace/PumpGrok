"""PAP-03: autonomous paper end to end on recorded datasets.

The human sets the autonomous-paper level through the ledger autonomy path
(ConfigChanged row with a human author, never journal text). Both recorded
datasets then run end to end with ``run --mode paper --once --replay``:
the smoke set places risk-engine-approved fills with no presented human
approval, and the smoke-10m set completes its cycle. Offline only: recorded
fixtures, no network, no wall clock.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pumpgrok.cli import main
from pumpgrok.ledger.autonomy import autonomy_rows, read_autonomy
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.replay.clock import FixtureClock, format_ts_utc

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")
SMOKE_10M = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke-10m")

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()


def _set_level(store: LedgerStore, policy: str, clock: FixtureClock) -> None:
    previous = read_autonomy(store)
    store.append_batch(
        autonomy_rows(
            policy,
            "human:alice",
            previous=previous,
            ts_utc=format_ts_utc(clock.now()),
            source="paper",
            correlation_id="pap03-e2e",
        )
    )


def _paper_store(tmp_path: Path) -> LedgerStore:
    var_dir = tmp_path / "var"
    var_dir.mkdir(parents=True, exist_ok=True)
    return LedgerStore(str(var_dir / "ledger.sqlite"))


def test_autonomous_paper_runs_on_smoke(tmp_path, monkeypatch, capsys) -> None:
    """PAP-03: human-set autonomous-paper fills on the smoke dataset."""
    monkeypatch.chdir(tmp_path)
    clock = FixtureClock(start=START)
    store = _paper_store(tmp_path)
    try:
        assert read_autonomy(store) == "manual-ticket"
        _set_level(store, "autonomous-paper", clock)
        assert read_autonomy(store) == "autonomous-paper"
    finally:
        store.close()

    assert main(["run", "--mode", "paper", "--once", "--replay", SMOKE]) == 0
    out = capsys.readouterr().out
    assert "engine decision=buy" in out
    assert "trades filled=2 not_filled=1" in out

    ledger = LedgerStore(str(tmp_path / "var" / "replay" / "smoke" / "ledger.sqlite"))
    try:
        rows = ledger.read(limit=None)
        kinds = [row["type"] for row in rows]
        assert "JournalNote" in kinds
        assert "FillRecorded" in kinds
        approvals = [row for row in rows if row["type"] == "ApprovalRecorded"]
        assert approvals, "autonomous-paper mints its own approvals"
        assert all(row["payload"].get("approved_by") == "risk_engine" for row in approvals)
        assert ledger.verify()
    finally:
        ledger.close()

    check = _paper_store(tmp_path)
    try:
        assert read_autonomy(check) == "autonomous-paper"
    finally:
        check.close()


def test_autonomous_paper_runs_on_smoke_10m(tmp_path, monkeypatch, capsys) -> None:
    """PAP-03: human-set autonomous-paper completes the smoke-10m dataset."""
    monkeypatch.chdir(tmp_path)
    clock = FixtureClock(start=START)
    store = _paper_store(tmp_path)
    try:
        _set_level(store, "autonomous-paper", clock)
        assert read_autonomy(store) == "autonomous-paper"
    finally:
        store.close()

    assert main(["run", "--mode", "paper", "--once", "--replay", SMOKE_10M]) == 0
    out = capsys.readouterr().out
    assert "engine decision=" in out
    assert "trades filled=" in out

    ledger = LedgerStore(str(tmp_path / "var" / "replay" / "smoke-10m" / "ledger.sqlite"))
    try:
        kinds = [row["type"] for row in ledger.read(limit=None)]
        assert "JournalNote" in kinds
        assert ledger.verify()
    finally:
        ledger.close()


def test_autonomy_level_ignores_journal_text(tmp_path: Path) -> None:
    """PAP-03: editing journal text never sets the level; only a human ConfigChanged does."""
    clock = FixtureClock(start=START)
    store = LedgerStore(str(tmp_path / "ledger.sqlite"))
    try:
        assert read_autonomy(store) == "manual-ticket"
        store.append_batch(
            [
                {
                    "ts_utc": format_ts_utc(clock.now()),
                    "source": "paper",
                    "correlation_id": "pap03-spoof",
                    "idempotency_key": "spoof-note",
                    "type": "JournalNote",
                    "payload": {
                        "source": "paper",
                        "seat": "desk",
                        "note_kind": "note",
                        "text": "autonomy autonomous-paper by human:alice",
                        "refs": [],
                    },
                }
            ]
        )
        assert read_autonomy(store) == "manual-ticket"
        store.append_batch(
            autonomy_rows(
                "autonomous-paper",
                "bot-04-sniper",
                previous="manual-ticket",
                ts_utc=format_ts_utc(clock.now()),
                source="paper",
                correlation_id="pap03-spoof",
            )
        )
        assert read_autonomy(store) == "manual-ticket"
    finally:
        store.close()
