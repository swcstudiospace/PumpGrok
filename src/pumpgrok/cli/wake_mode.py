"""--wake-mode flag helpers and event-mode readiness (EVT-13).

The flag defaults to cadence and is validated against the allowed set.
Event mode refuses while any superseded Hermes cron job is still enabled;
an unparsable jobs file refuses fail-closed (T-14-05-01).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from pumpgrok.supervisor.scheduler.wake import ALLOWED_TIMERS, assert_allowed_timers

WAKE_MODES: tuple[str, ...] = ("cadence", "event")
DEFAULT_WAKE_MODE = "cadence"

#: Jobs whose work is taken over by a bus event (owners with a SEAT_WAKES
#: entry). `chief-pickup` stays enabled: the chief seat has no SEAT_WAKES
#: entry, so cron remains its only driver.
SUPERSEDED_JOB_IDS: frozenset[str] = frozenset(
    {
        "scout-discover",
        "scout-pipeline",
        "risk-audit-open-leads",
        "rug-watch-paper",
        "chief-journal-rollup",
    }
)


def parse_wake_mode(value: str) -> str:
    """Validate against the allowed set. Cadence stays the default."""
    if value not in WAKE_MODES:
        raise ValueError(f"unknown wake mode: {value}")
    assert_allowed_timers(frozenset({"wake"}))
    assert frozenset({"wake"}) == ALLOWED_TIMERS
    return value


def default_wake_mode() -> str:
    return DEFAULT_WAKE_MODE


def superseded_jobs_enabled(jobs_path: Path) -> list[str] | None:
    """Job ids that are superseded yet still enabled.

    None means the jobs file could not be read or parsed; callers refuse.
    """
    try:
        text = jobs_path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return _parse_jobs_text(text) if False else None
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
        return None
    enabled: list[str] = []
    for job in data["jobs"]:
        if isinstance(job, dict) and job.get("id") in SUPERSEDED_JOB_IDS and job.get("enabled"):
            enabled.append(str(job["id"]))
    return sorted(enabled)


def _parse_jobs_text(text: str) -> list[str]:
    enabled: list[str] = []
    current_id: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("- id:"):
            current_id = line.split(":", 1)[1].strip()
        elif line.startswith("enabled:") and current_id in SUPERSEDED_JOB_IDS:
            if line.split(":", 1)[1].strip().lower() == "true":
                enabled.append(current_id)
            current_id = None
    return sorted(enabled)


def event_mode_refusal(wake_mode: str, jobs_path: Path) -> list[str]:
    """Refusal lines for event mode. Empty means event mode may start."""
    if wake_mode != "event":
        return []
    enabled = superseded_jobs_enabled(jobs_path)
    if enabled is None:
        return ["event mode refused: hermes/cron/jobs.yaml is unreadable"]
    if enabled:
        return [f"event mode refused: superseded job still enabled: {name}" for name in enabled]
    return []
