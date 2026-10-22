# Outage runbook

Containing an upstream outage (RPC failover, WebSocket silence, LLM down). The desk degrades to blind on bad data; the operator contains first and diagnoses second.

## Quick start

```bash
pumpgrok doctor
pumpgrok killswitch set --reason "upstream outage, containing paper flow"
docker compose logs pumpgrok
docker compose restart pumpgrok
pumpgrok doctor
pumpgrok killswitch clear --by human:operator --reason "upstream recovered, doctor green"
```

`doctor` identifies the failed source. `set` contains paper flow while the cause is unknown. `logs` shows the failure window. `restart` recovers the service after the upstream is back. The second `doctor` plus `clear` reopens flow with a recorded reason.

## What an outage does to the desk

- WebSocket silence trips data-stale; malformed upstream payloads parse to `DataStale` or `BLIND`.
- `BLIND` is treated as `KILL`: blind market data refuses new paper flow instead of guessing.
- The ledger keeps appending through the outage, so the failure window stays replayable after recovery.

## Rules that apply during an outage

- Contain before diagnosing. Set the kill switch while the blast radius is unknown.
- Never substitute a guess for a dead source. A missing quote is `data_unavailable`, not a reason to widen limits or reuse a stale price.
- Probe health with `pumpgrok doctor` and the `/healthz` endpoint only.
- Record the outage window (first bad timestamp, first good timestamp) in the incident note so the next replay can cover it.

## References

- Kill switch: `docs/runbooks/kill_switch.md`
- Breaker behavior while blind: `docs/runbooks/breaker_reset.md`
- Rollback after a bad deploy: `docs/runbooks/rollback.md`
