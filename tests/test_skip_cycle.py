"""Replay engine cycle over the runner: engine semantics and ledger effects (PAPER-004, R37).

The runner advances a FixtureClock through every fixture event, folds the
ticks into one engine decision, and appends one JournalNote (source=replay)
through LedgerStore.append_batch; the CLI seat-cycle tick then emits the
day-keyed DailyRollover for the fixture day (D6). These tests assert engine
semantics, not skip-only output: the fail-closed decision and its reason, the
event count, the virtual clock stamp, and the hash-chained ledger rows.
"""

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
from pumpgrok.config.settings import FORBIDDEN_SUBSTRINGS, FilterSettings
from pumpgrok.ledger.store import GENESIS_PREV_HASH, LedgerStore
from pumpgrok.replay.clock import parse_ts_utc
from pumpgrok.replay.fixtures import event_epoch, load_dataset
from pumpgrok.replay.runner import run_replay
from pumpgrok.supervisor.scheduler import rollover_key

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


def _ledger(base: Path, dataset: str = "smoke") -> Path:
    return base / "var" / "replay" / dataset / "ledger.sqlite"


def _rows(path: Path, sql: str) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(path)
    try:
        return [tuple(row) for row in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def _verdict(path: Path) -> dict[str, object]:
    (row,) = _rows(path, "SELECT correlation_id, payload_json FROM events WHERE type='JournalNote'")
    return {"correlation_id": row[0], "payload": json.loads(str(row[1]))}


def _replay_ledger_contract(path: Path) -> None:
    """CLI replay ledgers hold exactly the verdict row plus the D6 rollover row."""
    rows = _rows(path, "SELECT type, idempotency_key, payload_json FROM events ORDER BY seq")
    assert [row[0] for row in rows] == ["JournalNote", "DailyRollover"]
    payload = json.loads(str(rows[1][2]))
    day = str(load_dataset(SMOKE).events[0]["ts_utc"])[:10]
    assert payload["day_utc"] == day
    assert rows[1][1] == rollover_key(day)


def test_runner_folds_fixture_events_into_one_fail_closed_verdict(tmp_path: Path) -> None:
    result = run_replay(SMOKE, FilterSettings(), ledger_path=tmp_path / "ledger.sqlite")

    assert result.decision == "skip"
    assert result.reason == "data_unavailable"
    assert result.events_read == 4
    assert result.seq == 1
    dataset = load_dataset(SMOKE)
    assert result.ledger_path == tmp_path / "ledger.sqlite"
    store = LedgerStore(tmp_path / "ledger.sqlite")
    try:
        assert store.verify() is True
    finally:
        store.close()
    (seq, ts_utc, source, correlation_id, _, _, prev_hash, _) = _rows(
        tmp_path / "ledger.sqlite",
        "SELECT seq, ts_utc, source, correlation_id,"
        " idempotency_key, type, prev_hash, hash FROM events",
    )[0]
    assert seq == 1
    assert source == "replay"
    assert prev_hash == GENESIS_PREV_HASH
    assert parse_ts_utc(str(ts_utc)) == event_epoch(dataset.events[-1])
    assert str(correlation_id)
    verdict = _verdict(tmp_path / "ledger.sqlite")
    payload = verdict["payload"]
    assert isinstance(payload, dict)
    assert payload["seat"] == "desk"
    assert payload["note_kind"] == "verdict"
    assert "engine decision=skip reason=data_unavailable" in str(payload["text"])
    assert "read 4 fixture events from smoke" in str(payload["text"])
    assert event_epoch(dataset.events[-1]) > event_epoch(dataset.events[0])


def test_skip_cycle_cli_reports_the_runner_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["run", "--mode", "paper", "--once", "--replay", str(SMOKE)]) == 0

    verdict = _verdict(_ledger(tmp_path))
    payload = verdict["payload"]
    assert isinstance(payload, dict)
    assert "engine decision=skip reason=data_unavailable" in str(payload["text"])
    captured = capsys.readouterr()
    assert "engine decision=skip reason=data_unavailable" in captured.out
    log_records = [json.loads(line) for line in captured.err.splitlines() if line]
    (cycle_end,) = [record for record in log_records if record["event"] == "cycle_end"]
    assert cycle_end["correlation_id"] == verdict["correlation_id"]
    assert cycle_end["data"]["events_read"] == 4
    assert cycle_end["data"]["engine_decision"] == "skip"
    assert cycle_end["data"]["engine_reason"] == "data_unavailable"


def test_verify_smoke_10m_reports_a_stable_events_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["verify", "--fixture", "smoke-10m"]) == 0
    first = capsys.readouterr().out
    assert main(["verify", "--fixture", "smoke-10m"]) == 0
    second = capsys.readouterr().out
    assert first == second
    assert "events.hash=" in first
    assert "verify=CONSISTENT" in first


def test_killswitch_env_passes_settings_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PUMPGROK_KILLSWITCH", "1")
    assert main(["run", "--mode", "paper", "--once", "--replay", str(SMOKE)]) == 0
    _replay_ledger_contract(_ledger(tmp_path))


def test_second_run_recreates_the_replay_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    argv = ["run", "--mode", "paper", "--once", "--replay", str(SMOKE)]
    assert main(argv) == 0
    assert main(argv) == 0
    _replay_ledger_contract(_ledger(tmp_path))


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
    # R21/D4: precondition 1 needs [live] enabled=true; the CLI flag alone leaves it unmet.
    assert "[ ] 1 mode_live effective mode is live but [live] enabled is not true" in err
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
    assert "ok    supervisor (pumpgrok.supervisor)" in out
    for absent in ("gateway", "reports"):
        assert f"warn  {absent} (pumpgrok.{absent}): not-yet-implemented" in out
    assert not (tmp_path / "var").exists()
