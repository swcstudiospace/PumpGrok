"""EVT-13: superseded Hermes cron jobs are disabled and each maps to a real wake row or timer.

Every job in ``hermes/cron/jobs.yaml`` is classified here, once, as superseded or kept.
A superseded job names the seat that covers it, and that coverage must exist in the real
``SEAT_WAKES`` (an event kind row) or ``EVENT_TIMERS`` (a timer). Nothing from the wake table
is copied: the test imports it. The yaml flag is the recorded decision; it does not change
installed Hermes state (see docs/runbooks/events.md).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pumpgrok.core.manifests import EXPECTED_SEAT_IDS
from pumpgrok.events.models import EventKind
from pumpgrok.supervisor.scheduler.wake import EVENT_TIMERS, SEAT_WAKES

REPO_ROOT = Path(__file__).resolve().parents[2]
JOBS = REPO_ROOT / "hermes" / "cron" / "jobs.yaml"

JOURNAL = "bot-09-journal"

# (job id, coverage kind, coverage key). Coverage kind "timer" keys EVENT_TIMERS by seat;
# "wake" keys SEAT_WAKES by EventKind value and must name the seat in that row.
COVERAGE: tuple[tuple[str, str, str, str], ...] = (
    # Daily rollup renders from the journal seat on its 300 s timer (and on position_closed).
    ("chief-journal-rollup", "timer", JOURNAL, JOURNAL),
)

SUPERSEDED: frozenset[str] = frozenset(job for job, _, _, _ in COVERAGE)

# Kept with the reason the reviewed wake table does not cover the job's core work.
KEPT: dict[str, str] = {
    "scout-discover": "lead files feed the cron-driven risk audit; event scout writes no leads",
    "risk-audit-open-leads": (
        "brief verdicts CLEAR/CONDITIONAL/KILL/BLIND are not produced in event risk"
    ),
    "chief-pickup": "brief-to-ticket routing and ticket Telegram path have no event row",
    "rug-watch-paper": "red-flag and incident duties; event rug body is not a rug determination",
    "scout-pipeline": "reads recorded pipeline evidence; no wake row or timer consumes recordings",
}


def _jobs_doc() -> dict:
    return yaml.safe_load(JOBS.read_text(encoding="utf-8"))


def _jobs_by_id() -> dict[str, dict]:
    return {job["id"]: job for job in _jobs_doc()["jobs"]}


def _job_block(job_id: str) -> str:
    """Raw yaml text of one job, from its ``- id:`` line to the next job."""
    text = JOBS.read_text(encoding="utf-8")
    for chunk in text.split("  - id: ")[1:]:
        if chunk.split("\n", 1)[0].strip() == job_id:
            return chunk
    raise AssertionError(f"job {job_id} has no block in jobs.yaml")


def test_every_job_is_classified_exactly_once() -> None:
    job_ids = list(_jobs_by_id())
    assert len(job_ids) == len(set(job_ids)), "duplicate job id in jobs.yaml"
    assert SUPERSEDED.isdisjoint(KEPT), "a job is both superseded and kept"
    assert set(job_ids) == SUPERSEDED | set(KEPT), (
        f"unclassified or stale jobs: {sorted(set(job_ids) ^ (SUPERSEDED | set(KEPT)))}"
    )


def test_no_job_is_mapped_twice() -> None:
    mapped = [job for job, _, _, _ in COVERAGE]
    assert len(mapped) == len(set(mapped)), f"job mapped more than once: {mapped}"


@pytest.mark.parametrize(("job", "kind", "key", "seat"), COVERAGE)
def test_superseded_job_maps_to_real_wake_row_or_timer(
    job: str, kind: str, key: str, seat: str
) -> None:
    assert seat in EXPECTED_SEAT_IDS, f"{job}: {seat} is not a roster seat"
    if kind == "timer":
        assert key == seat, f"{job}: timer key must be the covering seat"
        assert seat in EVENT_TIMERS, f"{job}: {seat} has no EVENT_TIMERS entry"
        assert EVENT_TIMERS[seat] > 0
    elif kind == "wake":
        event_kind = EventKind(key)
        assert seat in SEAT_WAKES[event_kind], f"{job}: {seat} not woken by {key}"
    else:
        raise AssertionError(f"{job}: unknown coverage kind {kind!r}")


@pytest.mark.parametrize("job", sorted(SUPERSEDED))
def test_superseded_job_is_disabled(job: str) -> None:
    assert _jobs_by_id()[job]["enabled"] is False, f"{job} must be enabled: false"


@pytest.mark.parametrize("job", sorted(KEPT))
def test_unrelated_job_stays_enabled(job: str) -> None:
    assert _jobs_by_id()[job]["enabled"] is True, f"{job} is not superseded and must stay enabled"


@pytest.mark.parametrize(("job", "kind", "key", "seat"), COVERAGE)
def test_superseded_job_block_names_its_covering_seat(
    job: str, kind: str, key: str, seat: str
) -> None:
    block = _job_block(job)
    assert seat in block, f"{job}: jobs.yaml block does not name covering seat {seat}"
    assert "enabled: false" in block
