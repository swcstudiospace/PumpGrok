"""Doctor refuses event mode while a superseded Hermes cron job is enabled (EVT-13).

The installed-state probe reads `<HERMES_HOME>/cron/jobs.json` and each
`<HERMES_HOME>/profiles/<name>/cron/jobs.json`. A missing store is a pass ("no installed jobs
found"), not a skip. Refusals name the superseded job id only, never a prompt or a value.
Cadence mode is never refused: the cutover happens in event mode, so the enabled jobs are
reported as info.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pumpgrok import doctor
from pumpgrok.config.sections.v4 import EventsSettings
from pumpgrok.config.settings import ConfigError, Settings

SENTINEL = "SENTINEL-PROMPT-VALUE-14-07"


@pytest.fixture
def hermes_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def _write_store(path: Path, jobs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")


def _job(job_id: str, name: str, **extra: object) -> dict:
    return {"id": job_id, "name": name, "enabled": True, "prompt": SENTINEL, **extra}


def _event_settings() -> Settings:
    return Settings(mode="paper", events=EventsSettings(wake_mode="event"))


def test_missing_store_is_a_pass_in_event_mode(hermes_home: Path) -> None:
    lines = doctor.doctor_report(_event_settings())
    assert "ok    hermes-jobs: no installed jobs found (default profile)" in lines
    assert lines[-1].startswith("doctor:")


def test_missing_store_is_a_pass_in_cadence_mode(hermes_home: Path) -> None:
    lines = doctor.doctor_report(Settings(mode="paper"))
    assert "ok    hermes-jobs: no installed jobs found (default profile)" in lines


def test_enabled_superseded_job_refuses_event_mode(hermes_home: Path) -> None:
    _write_store(
        hermes_home / "cron" / "jobs.json",
        [_job("a1b2c3", "[bot:scout] discover")],
    )
    with pytest.raises(ConfigError) as refused:
        doctor.doctor_report(_event_settings())
    message = str(refused.value)
    assert "scout-discover" in message
    assert SENTINEL not in message
    assert "[bot:scout] discover" not in message


def test_superseded_job_matches_by_stable_id(hermes_home: Path) -> None:
    _write_store(hermes_home / "cron" / "jobs.json", [_job("chief-pickup", "anything")])
    with pytest.raises(ConfigError, match="chief-pickup"):
        doctor.doctor_report(_event_settings())


def test_superseded_job_in_profile_store_refuses_event_mode(hermes_home: Path) -> None:
    _write_store(
        hermes_home / "profiles" / "scout" / "cron" / "jobs.json",
        [_job("zz9", "[bot:scout] pipeline")],
    )
    with pytest.raises(ConfigError, match="scout-pipeline"):
        doctor.doctor_report(_event_settings())


def test_disabled_superseded_job_passes(hermes_home: Path) -> None:
    _write_store(
        hermes_home / "cron" / "jobs.json",
        [_job("a1", "[bot:risk] audit-open-leads", enabled=False)],
    )
    lines = doctor.doctor_report(_event_settings())
    assert "ok    hermes-jobs: 1 installed, no superseded job enabled" in lines


def test_paused_superseded_job_passes(hermes_home: Path) -> None:
    _write_store(
        hermes_home / "cron" / "jobs.json",
        [_job("a2", "[bot:rug] watch-paper", state="paused")],
    )
    doctor.doctor_report(_event_settings())


def test_unrelated_enabled_job_passes(hermes_home: Path) -> None:
    _write_store(
        hermes_home / "cron" / "jobs.json",
        [_job("u1", "[bot:desk] something-else")],
    )
    lines = doctor.doctor_report(_event_settings())
    assert "ok    hermes-jobs: 1 installed, no superseded job enabled" in lines


def test_cadence_mode_reports_superseded_job_without_refusing(hermes_home: Path) -> None:
    _write_store(
        hermes_home / "cron" / "jobs.json",
        [_job("a3", "[bot:scout] discover")],
    )
    lines = doctor.doctor_report(Settings(mode="paper"))
    info = [line for line in lines if "hermes-jobs" in line]
    assert info == [
        "info  hermes-jobs: superseded enabled: scout-discover "
        "(cadence; event mode refused)"
    ]


def test_wake_mode_argument_overrides_settings(hermes_home: Path) -> None:
    _write_store(
        hermes_home / "cron" / "jobs.json",
        [_job("a4", "[bot:chief] pickup")],
    )
    with pytest.raises(ConfigError, match="chief-pickup"):
        doctor.doctor_report(Settings(mode="paper"), wake_mode="event")


def test_unreadable_store_refuses_event_mode(hermes_home: Path) -> None:
    store = hermes_home / "cron" / "jobs.json"
    store.parent.mkdir(parents=True)
    store.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="unreadable"):
        doctor.doctor_report(_event_settings())


def test_superseded_list_matches_cutover_yaml() -> None:
    import yaml

    root = Path(__file__).resolve().parents[1]
    spec = yaml.safe_load((root / "hermes" / "cron" / "jobs.yaml").read_text(encoding="utf-8"))
    yaml_jobs = {job["id"]: job["name"] for job in spec["jobs"]}
    assert dict(doctor.SUPERSEDED_HERMES_JOBS) == yaml_jobs
