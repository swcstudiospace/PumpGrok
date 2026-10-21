"""Replay engine cycle through the CLI: exit-code map and ledger effects (FOUND-013, R37)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from pumpgrok.cli import main
from pumpgrok.config.settings import FORBIDDEN_SUBSTRINGS

SMOKE = Path(__file__).resolve().parent / "fixtures" / "replay" / "smoke"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip PUMPGROK_* and secret-shaped names so each test sets exactly what it needs."""
    for name in list(os.environ):
        upper = name.upper()
        if upper.startswith("PUMPGROK_") or any(f in upper for f in FORBIDDEN_SUBSTRINGS):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def root_handlers() -> Iterator[None]:
    """main() installs a handler bound to the test's stderr; remove it afterwards."""
    root = logging.getLogger()
    saved = list(root.handlers)
    level = root.level
    yield
    for handler in list(root.handlers):
        if handler not in saved:
            root.removeHandler(handler)
    root.setLevel(level)


def _ledger(base: Path) -> Path:
    return base / "var" / "replay" / "smoke" / "ledger.sqlite"


def _rows(path: Path, sql: str) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(path)
    try:
        return [tuple(row) for row in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def test_skip_cycle_writes_one_replay_journal_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "paper", "--once", "--replay", str(SMOKE)]) == 0

    ledger = _ledger(tmp_path)
    assert _rows(
        ledger, "SELECT COUNT(*) FROM events WHERE type='JournalNote' AND source='replay'"
    ) == [(1,)]
    (row,) = _rows(
        ledger, "SELECT correlation_id, payload_json FROM events WHERE type='JournalNote'"
    )
    payload = json.loads(str(row[1]))
    assert payload["source"] == "replay"
    assert payload["seat"] == "desk"
    assert payload["note_kind"] == "verdict"
    assert "engine decision=skip reason=data_unavailable" in payload["text"]
    assert "model resolution skipped (replay)" in payload["text"]

    captured = capsys.readouterr()
    assert "engine decision=skip reason=data_unavailable" in captured.out
    log_records = [json.loads(line) for line in captured.err.splitlines() if line]
    (cycle_end,) = [record for record in log_records if record["event"] == "cycle_end"]
    assert cycle_end["correlation_id"] == row[0]
    assert cycle_end["data"]["events_read"] == 4


def test_second_run_recreates_the_replay_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    argv = ["run", "--mode", "paper", "--once", "--replay", str(SMOKE)]
    assert main(argv) == 0
    assert main(argv) == 0
    assert _rows(_ledger(tmp_path), "SELECT COUNT(*) FROM events") == [(1,)]


def test_run_without_replay_exits_5_and_creates_no_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "paper"]) == 5
    assert main(["run", "--mode", "paper", "--once"]) == 5
    assert not (tmp_path / "var").exists()


def test_tampered_fixture_exits_4_before_any_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    dataset = tmp_path / "fixtures" / "smoke"
    shutil.copytree(SMOKE, dataset)
    with (dataset / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('{"ts_utc":"2026-01-01T00:00:04.000Z","kind":"tick"}\n')

    assert main(["run", "--mode", "paper", "--once", "--replay", str(dataset)]) == 4
    assert not (tmp_path / "var").exists()
    assert "corrupt fixture" in capsys.readouterr().err


def test_live_is_refused_with_exit_3_before_other_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "live", "--once", "--replay", str(SMOKE)]) == 3
    err = capsys.readouterr().err
    assert "[ ] 8 adapter_registered" in err
    assert "[ ] 1 " not in err  # mode_live is met in live mode
    assert "No transaction was attempted" in err
    assert not (tmp_path / "var").exists()

    # Live refusal precedes the exit-5 check for a run without --once --replay.
    assert main(["run", "--mode", "live"]) == 3
    assert not (tmp_path / "var").exists()


def test_config_errors_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PUMPGROK_BOGUS", "1")
    assert main(["run", "--mode", "paper", "--once", "--replay", str(SMOKE)]) == 1
    assert "unknown setting: PUMPGROK_BOGUS" in capsys.readouterr().err

    monkeypatch.delenv("PUMPGROK_BOGUS")
    monkeypatch.setenv("PUMPGROK_EXECUTION__MODE", "live")
    assert main(["run", "--mode", "paper", "--once", "--replay", str(SMOKE)]) == 1
    assert not (tmp_path / "var").exists()


def test_key_bearing_cli_value_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    url = "https://rpc.example.test/?api-key=abcdefghijklmnop"  # pragma: allowlist secret
    assert main(["run", "--mode", "paper", "--replay", url]) == 1
    assert not (tmp_path / "var").exists()


def test_doctor_reports_absent_subsystems_as_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "ok    ledger" in out
    assert "ok    tools (pumpgrok.tools)" in out
    assert "ok    engine (pumpgrok.engine)" in out
    for absent in ("gateway", "supervisor", "reports"):
        assert f"warn  {absent} (pumpgrok.{absent}): not-yet-implemented" in out
    assert not (tmp_path / "var").exists()
