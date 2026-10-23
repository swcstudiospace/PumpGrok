# Kill switch runbook

Engaging, inspecting, and clearing the desk kill switch. Setting the switch stops new paper flow immediately; flattening asks every open paper position to flatten first.

## Quick start

```bash
pumpgrok killswitch status
pumpgrok killswitch set --reason "data feed stale, investigating"
pumpgrok killswitch flatten --reason "halt open paper positions before restart"
pumpgrok killswitch clear --by human:operator --reason "feed recovered, doctor green"
```

`status` reports the current switch state. `set` engages it with a mandatory reason. `flatten` requests flattening of every open paper position with a mandatory reason. `clear` releases it and is human-only.

## What the kill switch does

- `set` flips the desk to halted: no new paper orders are emitted while the switch is engaged.
- `flatten` records a flatten request against every open paper position; fills are paper-only and land in the ledger.
- `clear` appends a `KillSwitchCleared` record plus a human approval, and releases the halt.
- Every transition carries the operator reason into the ledger, so the halt history is auditable.

## Rules that apply to the kill switch

- `set` and `flatten` are two separate verbs. There is no `set --flatten` flag; never write one.
- Every `set`, `flatten`, and `clear` needs `--reason`. An empty or missing reason is refused.
- `clear` needs `--by human:<name>`. A seat id is never accepted as the clearer.
- When in doubt, set first and investigate second. Clearing requires a green `pumpgrok doctor` and a stated reason.

## Flatten outcomes and exit codes

`flatten` sets the switch first, then closes every open paper position with reason `kill_flatten`. A position is closed only when the adapter values it: from the live curve, or from the last ledger mark. A position with neither (no ledger mark and no reserves) is left open.

- Exit 0: every open position closed, or none was open. The stdout JSON lists each outcome with `status` `closed`.
- Exit 6 (`EXIT_UNFLATTENED`): at least one position is still open, or the flatten did not finish (`flatten_status` `blocked` or `unavailable`). One stderr line per position names its mint, ticket, status and detail, for example `UNFLATTENED mint=... status=not_flattened detail=status=no_mark`. Exit 6 is used for this case only. The stdout JSON reports `flatten_status` `incomplete` whenever a position is left open, and `completed` only when every position closed.
- The switch stays set in every case. Exit 6 does not clear it, and the desk stays halted to new buys.

When the flatten leaves a position open, do not treat the book as flat. Find the mint in the stderr line, decide how to close it (for example, by restoring a ledger mark and running `flatten` again), and confirm `status` is `closed` before you rely on the book. The gateway and the alert-channel poll log the same positions at ERROR and retry them on each poll.

## References

- Switch implementation: `src/pumpgrok/risk/killswitch.py`
- Outage containment: `docs/runbooks/outage.md`
- Human approval format: `rules/pumpgrok-team.mdc`
