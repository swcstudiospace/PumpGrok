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

`flatten` sets the switch first, then closes every open paper position with reason `kill_flatten`. A position is closed only when the adapter values it: from the live curve, or from the last ledger mark. A position with neither (no ledger mark and no reserves) is left open. A position that another caller (an overlapping `flatten`, or the gateway poll) closed first counts as closed.

- Exit 0: every open position is closed, or none was open. `flatten_status` is `completed`, and each outcome in `flatten_outcomes` is `closed`.
- Exit 6 (`EXIT_UNFLATTENED`): the book is not flat. The stderr output depends on which of two cases happened.

Position-level (the flatten ran, and some positions were not closed): `flatten_status` is `incomplete`. `flatten_outcomes` has one row per open position with its `mint`, `ticket_id`, `status` `not_flattened` and `detail`. Stderr has one line per open position, with the full mint and ticket, for example `UNFLATTENED mint=... ticket=... status=not_flattened detail=status=no_mark`.

Run-level (the barrier did not clear, or no position closer was wired): `flatten_status` is `blocked` or `unavailable`, and `flatten_outcomes` is empty. Nothing was closed. Stderr has one line, `UNFLATTENED flatten_status=blocked detail=...` (or `unavailable`). That line names no mint and no ticket, because the run produced no position rows.

The switch stays set in every case. Exit 6 does not clear it, and the desk stays halted to new buys.

After a position-level exit 6, the stderr line gives the mint, so you know what is open. After a run-level exit 6, find the open positions with `pumpgrok report --daily`. Its "Open positions" section lists one row per open position, and shows the first eight characters of each mint. It does not print tickets. When the flatten has closed everything, that section reads `none open`. Once `report --daily` shows the positions you expect, run `pumpgrok killswitch flatten --reason "..."` again. A run-level `blocked` result closed nothing, so repeating the flatten does not double-close.

Do not treat the book as flat until `pumpgrok report --daily` shows `none open`.

The gateway and the alert-channel poll log each position left open at ERROR, with the mint and detail, and log a run that did not complete at ERROR, for example `kill flatten did not complete: status=blocked detail=...`. They retry the open positions on every poll.

## References

- Switch implementation: `src/pumpgrok/risk/killswitch.py`
- Outage containment: `docs/runbooks/outage.md`
- Human approval format: `rules/pumpgrok-team.mdc`
