"""R62 durability: a quarantined reputation book stays degraded in later processes.

A corrupt book is moved aside, and a degraded marker beside it keeps that state durable. A
later load from a missing path, as a restarted process sees it, still comes back degraded.
Only a human removing the marker clears the state.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pumpgrok.engine.reputation import ReputationBook
from pumpgrok.replay.clock import FixtureClock, format_ts_utc

START = datetime(2026, 10, 21, 0, 0, 0, tzinfo=UTC).timestamp()
MARKER = "reputation.degraded.json"


def _corrupt(path: Path) -> None:
    path.write_text("{not json", encoding="utf-8")


def test_corrupt_book_loaded_once_is_still_degraded_when_loaded_from_a_missing_path(
    tmp_path: Path,
) -> None:
    clock = FixtureClock(start=START)
    path = tmp_path / "reputation.json"
    _corrupt(path)

    first = ReputationBook.load(path, clock=clock)
    assert first.degraded is True
    assert not path.exists()

    # A fresh process finds no book at the path; the marker alone keeps the book degraded.
    second = ReputationBook.load(path, clock=clock)
    assert second.degraded is True
    assert second.creators == {}


def test_marker_records_the_quarantine_path_and_the_detection_time(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    path = tmp_path / "reputation.json"
    _corrupt(path)

    ReputationBook.load(path, clock=clock)

    quarantined = list(tmp_path.glob("reputation.json.corrupt-*"))
    assert len(quarantined) == 1
    marker = json.loads((tmp_path / MARKER).read_text(encoding="utf-8"))
    assert marker["quarantine"] == str(quarantined[0])
    assert marker["detected_at"] == format_ts_utc(START)


def test_marker_keeps_a_readable_book_degraded(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    path = tmp_path / "reputation.json"
    payload = {"version": 1, "creators": {}, "updated_at": 0.0}
    path.write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / MARKER).write_text("{}", encoding="utf-8")

    assert ReputationBook.load(path, clock=clock).degraded is True


def test_removing_the_marker_is_the_human_clear(tmp_path: Path) -> None:
    clock = FixtureClock(start=START)
    path = tmp_path / "reputation.json"
    _corrupt(path)
    ReputationBook.load(path, clock=clock)

    (tmp_path / MARKER).unlink()

    assert ReputationBook.load(path, clock=clock).degraded is False
