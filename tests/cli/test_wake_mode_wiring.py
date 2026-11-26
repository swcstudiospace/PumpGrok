"""`--wake-mode` reaches doctor, run and the supervisor entry points (EVT-10, EVT-13).

Event mode refuses a superseded or unreadable Hermes job before any supervisor starts. Cadence
(no flag, no settings value) runs unchanged. Hermes state is isolated with HERMES_HOME.
"""

import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from pumpgrok.cli import EXIT_CONFIG, EXIT_OK, main
from pumpgrok.config import settings as settings_mod
from pumpgrok.core.manifests import EXPECTED_SEAT_IDS, roster_tool_names
from pumpgrok.ledger import operator_choices as oc
from pumpgrok.ledger.paths import PAPER_LEDGER_PATH
from pumpgrok.ledger.store import LedgerStore
from pumpgrok.supervisor.scheduler import serve
from pumpgrok.tools import ensure_paper_genesis

REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE = str(REPO_ROOT / "tests" / "fixtures" / "replay" / "smoke")
AUTHORITY_AT = "2026-11-13T12:00:00+00:00"


@pytest.fixture
def hermes_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def _write_jobs(home: Path, jobs: list[dict[str, Any]]) -> None:
    store = home / "cron" / "jobs.json"
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text(json.dumps(jobs), encoding="utf-8")


def _chief_pickup_enabled(home: Path) -> None:
    _write_jobs(home, [{"id": "a4", "name": "[bot:chief] pickup", "enabled": True}])


@pytest.fixture
def supervisor_calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, Any]]]:
    """Record the keyword arguments of every Supervisor built by the replay entry points."""
    calls: list[dict[str, Any]] = []
    real = serve.Supervisor

    def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(dict(kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(serve, "Supervisor", spy)
    yield calls


def _record_paper_authority() -> None:
    """Paper genesis and an allow per roster tool, as the onboarding verbs record them."""
    oc.init_key(oc.OPERATOR_DIR)
    store = LedgerStore(PAPER_LEDGER_PATH)
    try:
        ensure_paper_genesis(store, settings_mod.load_settings(mode="paper").risk)
        for seat in EXPECTED_SEAT_IDS:
            for tool in sorted(roster_tool_names(oc.DEFAULT_CONTRACTS_DIR, seat)):
                oc.record_tool_choice(
                    store,
                    seat=seat,
                    tool=tool,
                    decision="allow",
                    now=datetime.fromisoformat(AUTHORITY_AT),
                    operator_dir=oc.OPERATOR_DIR,
                )
    finally:
        store.close()


# doctor -------------------------------------------------------------------------------------


def test_doctor_event_flag_refuses_superseded_job(
    hermes_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _chief_pickup_enabled(hermes_home)
    assert main(["doctor", "--mode", "paper", "--wake-mode", "event"]) == EXIT_CONFIG
    captured = capsys.readouterr()
    assert "chief-pickup" in captured.err
    assert "event mode" in captured.err


def test_doctor_json_event_flag_refuses_superseded_job(
    hermes_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _chief_pickup_enabled(hermes_home)
    assert main(["doctor", "--json", "--mode", "paper", "--wake-mode", "event"]) == EXIT_CONFIG
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "chief-pickup" in captured.err


def test_doctor_json_default_cadence_does_not_refuse(
    hermes_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _chief_pickup_enabled(hermes_home)
    main(["doctor", "--json", "--mode", "paper"])
    captured = capsys.readouterr()
    assert "superseded Hermes job" not in captured.err
    assert isinstance(json.loads(captured.out), list)


def test_doctor_default_cadence_reports_without_refusing(
    hermes_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _chief_pickup_enabled(hermes_home)
    assert main(["doctor", "--mode", "paper"]) == EXIT_OK
    out = capsys.readouterr().out
    assert (
        "info  hermes-jobs: superseded enabled: chief-pickup (cadence; event mode refused)" in out
    )


def test_doctor_settings_event_mode_refuses_without_flag(
    hermes_home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _chief_pickup_enabled(hermes_home)
    monkeypatch.setenv("PUMPGROK_EVENTS__WAKE_MODE", "event")
    assert main(["doctor", "--mode", "paper"]) == EXIT_CONFIG
    assert "chief-pickup" in capsys.readouterr().err


# run ----------------------------------------------------------------------------------------


def test_run_event_flag_refuses_superseded_job_before_supervisor(
    hermes_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    supervisor_calls: list[dict[str, Any]],
) -> None:
    monkeypatch.chdir(tmp_path)
    _chief_pickup_enabled(hermes_home)
    code = main(["run", "--mode", "paper", "--once", "--replay", SMOKE, "--wake-mode", "event"])
    assert code == EXIT_CONFIG
    captured = capsys.readouterr()
    assert "chief-pickup" in captured.err
    assert supervisor_calls == []


def test_run_settings_event_mode_refuses_superseded_job(
    hermes_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    supervisor_calls: list[dict[str, Any]],
) -> None:
    monkeypatch.chdir(tmp_path)
    _chief_pickup_enabled(hermes_home)
    monkeypatch.setenv("PUMPGROK_EVENTS__WAKE_MODE", "event")
    assert main(["run", "--mode", "paper", "--once", "--replay", SMOKE]) == EXIT_CONFIG
    assert "chief-pickup" in capsys.readouterr().err
    assert supervisor_calls == []


def test_run_event_path_builds_event_supervisor(
    hermes_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    supervisor_calls: list[dict[str, Any]],
) -> None:
    """Event mode builds the Supervisor with wake_mode event."""
    monkeypatch.chdir(tmp_path)
    _record_paper_authority()
    assert (
        main(["run", "--mode", "paper", "--once", "--replay", SMOKE, "--wake-mode", "event"])
        == EXIT_OK
    )
    assert supervisor_calls
    assert supervisor_calls[0].get("wake_mode") == "event"


def test_run_default_stays_cadence(
    hermes_home: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    supervisor_calls: list[dict[str, Any]],
) -> None:
    monkeypatch.chdir(tmp_path)
    _record_paper_authority()
    assert main(["run", "--mode", "paper", "--once", "--replay", SMOKE]) == EXIT_OK
    assert supervisor_calls
    assert supervisor_calls[0].get("wake_mode", "cadence") == "cadence"
