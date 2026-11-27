# Events runbook: Hermes cron cutover (EVT-10, EVT-13)

With `wake_mode=event`, the bus drives seat wakes and Hermes cron jobs that
duplicate bus events are **disabled, not deleted**, in
`hermes/cron/jobs.yaml`:

- `scout-discover`, `scout-pipeline` (superseded by scout wakes)
- `risk-audit-open-leads` (superseded by risk wakes)
- `rug-watch-paper` (superseded by rug wakes)
- `chief-journal-rollup` (superseded by journal wakes)
- `chief-pickup` stays enabled: the chief seat has no `SEAT_WAKES` entry, so
  cron remains its only driver.

## Wake table and timers

Source of truth: `src/pumpgrok/supervisor/scheduler/wake.py` (`SEAT_WAKES`, `EVENT_TIMERS`). Owner-confirmed; do not edit casually. Superseded-job refusal is enforced by `doctor --wake-mode event` via `src/pumpgrok/cli/wake_mode.py` (`SUPERSEDED_JOB_IDS`); mapping test: `tests/desk/test_hermes_jobs_superseded.py`.

- `EVENT_TIMERS` (the only timers in event mode):
  - `bot-02-risk`: 5 s staleness.
  - `bot-06-exit`: 15 s watchdog.
  - `bot-09-journal`: 300 s flush. The daily rollup renders on this timer and on a `position_closed` event.

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

## Event mode after onboarding

Onboarding is not part of the wake table. The paper start gate in `run` runs before any supervisor starts, whichever wake mode is configured. A missing operator input refuses the start: the gate prints `paper start refused`, one line per missing input, and exits 1.

Check the inputs before a serving start:

```bash
uv run pumpgrok onboarding list
uv run pumpgrok doctor --json
```

Serve the replay dataset. `PUMPGROK_HEALTH__PORT` must be nonzero:

```bash
uv run pumpgrok run --mode paper --serve --replay tests/fixtures/replay/smoke
```

- The gate needs every roster tool of every seat to hold a bound decision. One missing decision refuses the whole start; it does not disable one seat.
- A tool without an allow decision is not granted to its seat.
- The gate counts a bound revoke as a recorded decision. After `uv run pumpgrok onboarding revoke --seat <seat> --tool <tool>`, check `onboarding list`; the gate alone does not catch a revoke.
- The wake table, the timers and the superseded-job decisions above are unchanged by onboarding.
