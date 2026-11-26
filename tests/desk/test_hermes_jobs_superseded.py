"""Superseded Hermes cron jobs are disabled (not deleted)."""

import pathlib

import yaml  # type: ignore[import-untyped]

from pumpgrok.cli.wake_mode import SUPERSEDED_JOB_IDS


def _jobs() -> list[dict[str, object]]:
    data = yaml.safe_load(pathlib.Path("hermes/cron/jobs.yaml").read_text(encoding="utf-8"))
    return list(data["jobs"])


def test_superseded_jobs_disabled() -> None:
    jobs = _jobs()
    for job in jobs:
        if str(job["id"]) in SUPERSEDED_JOB_IDS:
            assert job["enabled"] is False, job["id"]


def test_superseded_jobs_still_present() -> None:
    ids = {str(job["id"]) for job in _jobs()}
    assert ids >= SUPERSEDED_JOB_IDS


def test_non_superseded_job_unchanged() -> None:
    jobs = {str(job["id"]): job for job in _jobs()}
    assert jobs["chief-pickup"]["enabled"] is True
