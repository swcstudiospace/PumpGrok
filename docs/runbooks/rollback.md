# Rollback runbook

Returning the desk to the last known-good build. Rollback is a redeploy of a previous commit, verified by the same one-shot cycle that proves a fresh start.

## Quick start

```bash
docker compose down
docker compose up --build pumpgrok
pumpgrok doctor
pumpgrok verify --fixture smoke
pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
```

`down` stops the bad build. Checking out the previous commit happens outside the container (see Rules). `up --build` redeploys it. `doctor`, `verify`, and the one-shot replay prove the rolled-back desk is healthy before it takes any flow.

## What a rollback preserves

- The ledger under `./var/` is never rolled back with the code. History stays append-only across deploys; only the image changes.
- Replay ledgers under `var/replay/` are derived artifacts. They can be rebuilt from fixtures with `pumpgrok verify` at any time.
- The previous commit is identified by the gate receipt history and the release log, not by memory.

## Rules that apply to a rollback

- Check out the previous commit in the checkout first, then `up --build`. Never edit code during a rollback to "fix forward"; that is a new change, not a rollback.
- Keep `./var/` mounted through the rollback. A rollback that wipes the ledger destroys the audit trail it was meant to protect.
- The rolled-back build must pass the same proof as a fresh start: green `doctor`, consistent `verify`, and an exit-0 replay cycle. If any of the three fails, keep the kill switch set and escalate.
- Record the rollback (from commit, to commit, reason) in the incident note.

## References

- Start and stop: `docs/runbooks/start_stop.md`
- Release history: `CHANGELOG.md`
- Gate receipts: `.receipts/`
