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

## References

- Switch implementation: `src/pumpgrok/risk/killswitch.py`
- Outage containment: `docs/runbooks/outage.md`
- Human approval format: `rules/pumpgrok-team.mdc`
