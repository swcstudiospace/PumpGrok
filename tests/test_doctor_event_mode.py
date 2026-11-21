"""Doctor refuses event mode while a superseded job is enabled."""

from pathlib import Path

from pumpgrok.doctor import event_mode_refusal, time_sync_probe


def test_cadence_never_refuses() -> None:
    assert event_mode_refusal("cadence", Path("hermes/cron/jobs.yaml")) == []


def test_event_passes_when_cutover_applied() -> None:
    refusals = event_mode_refusal("event", Path("hermes/cron/jobs.yaml"))
    assert refusals == [], refusals


def test_event_refuses_with_enabled_superseded_job(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs.yaml"
    jobs.write_text(
        "jobs:\n  - id: scout-discover\n    enabled: true\n",
        encoding="utf-8",
    )
    refusals = event_mode_refusal("event", jobs)
    assert any("scout-discover" in line for line in refusals)


def test_event_refuses_on_unparsable_jobs_file(tmp_path: Path) -> None:
    jobs = tmp_path / "jobs.yaml"
    jobs.write_text("jobs: [", encoding="utf-8")
    assert event_mode_refusal("event", jobs) != []


def test_time_sync_probe_is_read_only() -> None:
    line = time_sync_probe()
    assert "read-only" in line
    assert "not adjusted" in line
