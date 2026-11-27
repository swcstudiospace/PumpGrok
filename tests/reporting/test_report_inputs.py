"""Report inputs: the ledger is read once, read-only, and bad input is refused, not defaulted.

Regressions for the events sweep findings on the reporting readers: a ledger path with
a ``?`` opened the wrong file, a corrupt ledger rendered as an empty desk, calendar
dates were not checked, the weekly report read the ledger several times, a row with no
timestamp folded silently, and the gate read the whole process environment.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import pumpgrok.reporting.weekly as weekly_mod
from pumpgrok.core.errors import CorruptState
from pumpgrok.execution.live.live_gate import LiveGate
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.reporting.daily import DailyReport, day_next
from pumpgrok.reporting.weekly import WeeklyReport

DAY = "2026-10-20"
MINT = "So11111111111111111111111111111111111111112"
CID = "01J0000000000000000000000"


def _store_fill(ledger: Path) -> None:
    store = LedgerStore(ledger)
    try:
        store.append(
            ts_utc=DAY + "T10:00:00Z",
            source="paper",
            correlation_id=CID,
            idempotency_key="fill-buy",
            type="FillRecorded",
            payload={
                "source": "paper",
                "order_id": "ord-buy",
                "decision_id": "dec-buy",
                "side": "buy",
                "mint": MINT,
                "filled_lamports": 200_000_000,
                "filled_units": 1000,
                "filled_fraction": "1",
                "price_avg": "0.00005",
                "venue_fee_lamports": 2_000_000,
                "network_cost_lamports": 9_000,
                "cash_delta_lamports": -200_009_000,
            },
        )
    finally:
        store.close()


def _raw_event(ledger: Path, *, seq: int, ts: str, type: str, payload_json: str) -> None:
    """Write a row the store would refuse, as a tampered or legacy ledger would hold it."""
    db = sqlite3.connect(ledger)
    try:
        db.execute(
            "INSERT INTO events (seq, ts_utc, source, correlation_id, idempotency_key,"
            " type, payload_json, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (seq, ts, "paper", CID, f"raw-{seq}", type, payload_json, "0" * 64, f"raw-{seq}"),
        )
        db.commit()
    finally:
        db.close()


def test_ledger_path_containing_a_question_mark_is_the_file_read(tmp_path: Path) -> None:
    ledger = tmp_path / "run?x" / "ledger.sqlite"
    _store_fill(ledger)
    assert DailyReport.build(ledger, DAY).trades == 1


def test_unreadable_ledger_is_an_error_not_an_empty_desk(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    ledger.write_bytes(b"this is not a sqlite database" * 64)
    with pytest.raises(sqlite3.Error):
        DailyReport.build(ledger, DAY)


@pytest.mark.parametrize("day", ["2026-02-30", "2026-13-01", "2026-1-5", "garbage"])
def test_daily_report_refuses_a_day_that_is_not_a_calendar_date(day: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        DailyReport.build(tmp_path / "ledger.sqlite", day)


def test_weekly_report_refuses_a_day_that_is_not_a_calendar_date(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        WeeklyReport.build(tmp_path / "ledger.sqlite", "2026-02-30", root=tmp_path)
    with pytest.raises(ValueError):
        WeeklyReport.build(tmp_path / "ledger.sqlite", "2026-13-01", root=tmp_path)


def test_day_arithmetic_follows_the_calendar() -> None:
    assert day_next("2028-02-28") == "2028-02-29T00:00:00.000000Z"
    assert day_next("2027-02-28") == "2027-03-01T00:00:00.000000Z"
    assert day_next("2026-12-31") == "2027-01-01T00:00:00.000000Z"


def test_weekly_report_opens_the_ledger_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ledger = tmp_path / "desk" / "ledger.sqlite"
    _store_fill(ledger)
    opened: list[str] = []
    real_connect = sqlite3.connect

    def counting_connect(database: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        if str(ledger.resolve()) in str(database):
            opened.append(str(database))
        return real_connect(database, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sqlite3, "connect", counting_connect)
    WeeklyReport.build(ledger, DAY, root=tmp_path)
    assert len(opened) == 1


def test_event_without_a_timestamp_is_corruption(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.sqlite"
    _store_fill(ledger)
    _raw_event(ledger, seq=100, ts="", type="JournalNote", payload_json='{"note_kind": "x"}')
    with pytest.raises(CorruptState):
        DailyReport.build(ledger, DAY)


def test_weekly_report_requires_an_explicit_gate_root(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        WeeklyReport.build(tmp_path / "ledger.sqlite", DAY)  # type: ignore[call-arg]


def test_gate_receives_only_the_variables_it_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, str] = {}

    class RecordingGate(LiveGate):
        def __init__(self, **kwargs: object) -> None:
            environ = kwargs["environ"]
            assert isinstance(environ, dict)
            seen.update(environ)
            super().__init__(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(weekly_mod, "LiveGate", RecordingGate)
    monkeypatch.setenv("PUMPGROK_LIVE_ENABLE", "1")
    monkeypatch.setenv("PUMPGROK_TEST_UNRELATED_SENTINEL", "must-not-reach-the-gate")
    WeeklyReport.build(tmp_path / "ledger.sqlite", DAY, root=tmp_path)
    assert seen == {"PUMPGROK_LIVE_ENABLE": "1"}
