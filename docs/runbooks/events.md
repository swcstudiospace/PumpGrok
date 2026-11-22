# Events runbook: Hermes cron cutover (EVT-13)

With `wake_mode=event`, the bus drives seat wakes and Hermes cron jobs that
duplicate bus events are **disabled, not deleted**, in
`hermes/cron/jobs.yaml`:

- `scout-discover`, `scout-pipeline` (superseded by scout wakes)
- `risk-audit-open-leads` (superseded by risk wakes)
- `rug-watch-paper` (superseded by rug wakes)
- `chief-journal-rollup` (superseded by journal wakes)

`chief-pickup` stays enabled: the chief seat has no `SEAT_WAKES` entry, so
cron remains its only driver.

## Single-writer rule

**Bus or cron, never both.** Event mode with a superseded job still enabled
double-fires the same seat. `doctor --wake-mode event` (and
`doctor_report(wake_mode="event")`) refuses and names the offending job; an
unparsable jobs file refuses fail-closed.

## Re-enable a job

Set `enabled: true` on the job in `hermes/cron/jobs.yaml` and keep
`wake_mode=cadence`. Re-enable is one flag flip; job definitions
(schedules, prompts, deliver targets) are unchanged.

## Time sync

The time-sync probe is read-only: it reports and never adjusts the clock.
