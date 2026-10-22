# Breaker reset runbook

What to do when a risk breaker opens. There is no manual reset verb: breakers re-probe on their own half-open schedule, and the operator observes rather than forces.

## Quick start

```bash
pumpgrok doctor
pumpgrok state status --seat desk
pumpgrok killswitch status
```

`doctor` shows which breaker tripped and why. `state status --seat desk` (the operator seat; it resolves to `bot-00-chief`, which holds the `risk.halt_status` grant) shows desk posture while the breaker is open. `killswitch status` confirms whether the halt flag is also set.

## What a breaker trip means

- A breaker moves `closed` to `open` when its limit is hit (loss floor, data staleness, error budget). While open, the guarded flow stays halted.
- From `open` the breaker moves to `half-open` on its own schedule and lets one probe through. A clean probe closes it; a dirty probe re-opens it.
- Every transition is recorded in the ledger with its reason, so the trip history survives restarts.

## Rules that apply to breaker trips

- No manual reset verb exists. Do not invent one, and do not restart the desk just to clear a breaker; a restart does not change what the ledger already recorded.
- While a breaker is open, treat the guarded flow as halted. New paper orders on that path stay refused until the breaker closes itself.
- If the trip reason is upstream data (stale feed, blind market), follow `outage.md` instead of waiting on the breaker alone.
- A 5% daily-loss floor halt clears human-only, like the kill switch. Record the clearer and the reason.

## References

- Breaker set: `src/pumpgrok/risk/breakers.py`
- Outage containment: `docs/runbooks/outage.md`
- Kill switch: `docs/runbooks/kill_switch.md`
