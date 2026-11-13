# Event mode runbook

Event mode wakes a seat only when a bus event on its row arrives, or when it is one of the timers below. Cadence mode is unchanged. This runbook covers the wake table, the timers, and the Hermes cron cutover (EVT-10, EVT-13).

## Wake table and timers

Source of truth: `src/pumpgrok/supervisor/scheduler/wake.py` (`SEAT_WAKES`, `EVENT_TIMERS`). Owner-confirmed; do not edit casually.

- `EVENT_TIMERS` (the only timers in event mode):
  - `bot-02-risk`: 5 s staleness.
  - `bot-06-exit`: 15 s watchdog.
  - `bot-09-journal`: 300 s flush. The daily rollup renders on this timer and on a `position_closed` event.

## Hermes cron cutover

Owner decision for plan 14-07: a job is superseded only when the reviewed wake table, through the seat's event-mode body, performs that job's core work. A job whose core work has no event path stays enabled. Only the `enabled` flag in `hermes/cron/jobs.yaml` changed. Schedules and prompts are unchanged.

| Job id | enabled | Decision | Covering row or timer | Evidence |
|---|---|---|---|---|
| `chief-journal-rollup` | false | superseded | `EVENT_TIMERS` `bot-09-journal` (300 s); also `SEAT_WAKES` `position_closed` -> `bot-09-journal` | `_journal` in `src/pumpgrok/supervisor/scheduler/event_cycles_aux.py:179-215` renders the daily report via `run_render_report`; `tests/desk/test_journal_rollup_event.py` |
| `scout-discover` | true | kept | `token_created`, `migration` -> `bot-01-scout` cover admission only | `_scout` in `event_cycles.py:75-109` returns a decision and writes no lead file; the kept risk audit reads leads this job writes |
| `risk-audit-open-leads` | true | kept | `strategy_intent` -> `bot-02-risk`; timer `bot-02-risk` cover halt evaluation only | `_risk` in `event_cycles.py:112-116` evaluates daily-loss and drawdown halts; it writes no `briefs/` verdict |
| `chief-pickup` | true | kept | none | `_chief` in `event_cycles.py:66-72` is read-only; no brief-to-ticket routing and no ticket Telegram path |
| `rug-watch-paper` | true | kept | `curve_tick`, `mark` -> `bot-05-rug` wake the seat | `_rug` in `event_cycles.py:166-182` returns UNREAD, BLIND or READABLE and states READABLE is not a rug determination; red-flag and incident duties are not replaced |
| `scout-pipeline` | true | kept | none | reads recorded pipeline evidence (`pumpgrok scout pipeline`); no wake row or timer consumes recordings |

Mapping test: `tests/desk/test_hermes_jobs_superseded.py`. It imports the real `SEAT_WAKES` and `EVENT_TIMERS`, classifies every job once, and checks that each superseded job names its covering seat in `jobs.yaml`.

## Host state

This host has no PumpGrok cron jobs installed. The default Hermes profile has zero scheduled jobs, and the owner confirmed the cutover is a no-op here. The `enabled` flags record the decision for any install. Editing `jobs.yaml` did not change any scheduler, installed job, or host state.

## Detection

1. Flags match the mapping: `.venv/bin/python -m pytest -o addopts= -q tests/desk/test_hermes_jobs_superseded.py` (a regression here means a flag drifted from the table above).
2. Installed state, per owner: `hermes -p <owner> cron list` for `scout`, `risk`, `chief`, `rug`, the same listing `scripts/hermes-install-cron.sh` prints. In event mode `[bot:chief] journal-rollup` must not be listed as active. Any superseded job still active is enabled on that host.

`scripts/hermes-install-cron.sh` creates jobs with `hermes -p <owner> cron create` and does not read `enabled`. Flipping the flag in `jobs.yaml` therefore does not change an installed job. Remove an installed superseded job by hand: `hermes -p <owner> cron remove <id>`.

## Rollback

Use this if the daily rollup stops reaching the journal, or the owner wants the 12:00 job back.

1. Revert the 14-07 `jobs.yaml` change and its test together. The test asserts the mapping, so the flag must not be reverted alone. Or set `enabled: true` on `chief-journal-rollup` and drop its entry from `COVERAGE` in the test.
2. If the job was installed on this host, recreate it on the `chief` profile. The prompt body is the header from `prompt_body` in `scripts/hermes-install-cron.sh` (the `REPO=` and `DESK=` lines, then the text of `hermes/cron/prompts/chief-journal.md`):

   ```bash
   hermes -p chief cron create "0 12 * * *" "<prompt body>" \
     --name "[bot:chief] journal-rollup" --deliver telegram \
     --profile chief --workdir "$DESK" \
     --skill desk-folders-and-journal --skill hermes-cron-desk
   ```

Do not recreate the other five jobs; they are kept and still run.

## Open owner items

- Design record conflict. `.planning/phases/14-event-driven-desk-and-grok-gateway/14-DESIGN-A-DECISIONS.md` (OD-13) says "disable all six superseded jobs". The 14-07 criterion above disables one. The owner must confirm which governs.
- Telegram heartbeat. Event-mode `journal rollup` renders the report with `deliver=False`. The 12:00 Telegram heartbeat from `chief-journal-rollup` has no event-mode path. Disabling that job removes it.
- Installer. `scripts/hermes-install-cron.sh` ignores `enabled` (see Detection). Making the installer honor the flag is a separate change.
- Doctor. Refusing event mode while a superseded job is enabled (EVT-13) is a separate change. This runbook does not claim it exists.

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
