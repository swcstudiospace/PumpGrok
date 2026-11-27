"""Superseded Hermes cron jobs gate event mode (EVT-13, T-14-05-01)."""

from __future__ import annotations

from pathlib import Path

from pumpgrok.cli.wake_mode import event_mode_refusal, superseded_jobs_enabled


def _jobs(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "jobs.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_jobs_file_refuses_fail_closed(tmp_path: Path) -> None:
    assert superseded_jobs_enabled(tmp_path / "missing.yaml") is None


def test_unparsable_or_wrong_shape_refuses(tmp_path: Path) -> None:
    assert superseded_jobs_enabled(_jobs(tmp_path, "jobs: [unclosed")) is None
    assert superseded_jobs_enabled(_jobs(tmp_path, "not_a_mapping: 1")) is None
    assert superseded_jobs_enabled(_jobs(tmp_path, "jobs: nope")) is None


def test_superseded_and_enabled_jobs_are_named(tmp_path: Path) -> None:
    text = (
        "jobs:\n"
        "  - id: scout-discover\n"
        "    enabled: true\n"
        "  - id: scout-pipeline\n"
        "    enabled: false\n"
        "  - id: chief-pickup\n"
        "    enabled: true\n"
        "  - id: rug-watch-paper\n"
        "    enabled: true\n"
    )
    assert superseded_jobs_enabled(_jobs(tmp_path, text)) == ["rug-watch-paper", "scout-discover"]


def test_non_superseded_jobs_are_ignored(tmp_path: Path) -> None:
    text = "jobs:\n  - id: chief-pickup\n    enabled: true\n"
    assert superseded_jobs_enabled(_jobs(tmp_path, text)) == []


def test_event_mode_refusal_branches(tmp_path: Path) -> None:
    assert event_mode_refusal("cadence", tmp_path / "missing.yaml") == []
    assert event_mode_refusal("event", tmp_path / "missing.yaml") == [
        "event mode refused: hermes/cron/jobs.yaml is unreadable"
    ]
    text = "jobs:\n  - id: scout-discover\n    enabled: true\n"
    lines = event_mode_refusal("event", _jobs(tmp_path, text))
    assert lines == ["event mode refused: superseded job still enabled: scout-discover"]
    clean = "jobs:\n  - id: scout-discover\n    enabled: false\n"
    assert event_mode_refusal("event", _jobs(tmp_path, clean)) == []
