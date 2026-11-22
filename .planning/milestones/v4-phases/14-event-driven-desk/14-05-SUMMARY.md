---
phase: 14-event-driven-desk
plan: "05"
status: complete
commit: b3295c8
---

# Phase 14 Plan 05: Hermes cutover + doctor refusal — Summary

The five jobs duplicated by bus events (scout-discover, scout-pipeline,
risk-audit-open-leads, rug-watch-paper, chief-journal-rollup) are disabled,
not deleted, in `hermes/cron/jobs.yaml`; `chief-pickup` stays enabled
(chief has no `SEAT_WAKES` entry). `docs/runbooks/events.md` documents the
cutover, re-enable path, and single-writer rule. `doctor_report(wake_mode=
"event")` and `doctor --wake-mode event` refuse while a superseded job is
enabled, naming it; an unparsable jobs file refuses fail-closed. The
time-sync probe is read-only. `--wake-mode` defaults to cadence.

## Gates

- `uv run pytest -q tests/desk/test_hermes_jobs_superseded.py` — exit 0 (3 passed)
- `uv run pytest -q tests/test_doctor_event_mode.py tests/cli/test_wake_mode.py tests/test_doctor_time_sync.py` — exit 0 (10 passed)
- Plan `<verification>` — exit 0 (13 passed)
