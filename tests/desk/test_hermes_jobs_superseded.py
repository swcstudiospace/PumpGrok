"""Superseded Hermes cron jobs are disabled (not deleted)."""

import pathlib


def _jobs() -> list[dict[str, object]]:
    import yaml  # type: ignore[import-untyped]

    data = yaml.safe_load(pathlib.Path("hermes/cron/jobs.yaml").read_text(encoding="utf-8"))
    return list(data["jobs"])


def test_superseded_jobs_disabled() -> None:
    from pumpgrok.cli.wake_mode import SUPERSEDED_JOB_IDS

    jobs = _jobs()
    for job in jobs:
        if str(job["id"]) in SUPERSEDED_JOB_IDS:
            assert job["enabled"] is False, job["id"]


def test_superseded_jobs_still_present() -> None:
    from pumpgrok.cli.wake_mode import SUPERSEDED_JOB_IDS

    ids = {str(job["id"]) for job in _jobs()}
    assert SUPERSEDED_JOB_IDS <= ids


def test_non_superseded_job_unchanged() -> None:
    jobs = {str(job["id"]): job for job in _jobs()}
    assert jobs["chief-pickup"]["enabled"] is True
