---
runbook_id: RB-31
title: SLO canary for REL-T1482-be
trigger: canary step starts for REL-T1482-be
tier: 1
last_verified: "2026-11-20"
steps:
  - action: halt
    reversible: true
  - action: check_error_rate
    reversible: true
  - action: check_p95_latency
    reversible: true
  - action: check_slo_burn
    reversible: true
  - action: soak
    reversible: true
  - action: rollback
    reversible: true
rollback: halt at current step and roll back on any trigger
---

# SLO canary runbook

Canary steps 5/25/50/100 percent. Error budget 0.005. P95 limit 320ms.
Release blocked, do not promote. No step starts while quality fails.

## Quick start

```bash
pumpgrok doctor
pumpgrok killswitch status
```

`doctor` shows desk posture. `killswitch status` shows whether paper
flow is halted. While the release is blocked, hold at 0 percent.

## Trigger

Canary step starts for REL-T1482-be. A step starts only after quality
passes, review passes, security passes and provenance is registered.
The current verdicts are review pass, security pass, quality fail,
release fail. That set does not start a step.

## Steps

1. Halt at the current step. Recording the step and the start time
   keeps the window comparable.
2. Check error rate over 5m. Hold if error rate is above 0.005.
3. Check p95 latency over 5m. Hold if p95 is above 320ms.
4. Check SLO burn over 1h. Hold if burn is above 2.0x.
5. Soak for at least 15 minutes at the step before the next step.
6. Roll back on any breach and record the trigger in the incident note.

## Rollback

Halt at the current step and roll back on any trigger: error rate above
0.005 over 5m, p95 above 320ms over 5m, SLO burn above 2.0x over 1h, a
rollback-suggested telemetry verdict, a sev2 or higher incident naming
this release, or monitoring degraded. Fail closed on monitoring
degraded: halt at the current step and do not advance.

## References

- Release plan: .swarm/releases/REL-T1482-be.plan.json
- Kill switch: docs/runbooks/kill_switch.md
- Outage containment: docs/runbooks/outage.md
- Rollback: docs/runbooks/rollback.md
