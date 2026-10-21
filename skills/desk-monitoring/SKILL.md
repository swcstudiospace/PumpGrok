---
name: desk-monitoring
description: Continuous oversight of desk health, open positions, daily P&L, and circuit-breaker status. Used primarily by CHIEF.
bots:
  - bot-00-chief
  - bot-05-rug
gates: []
---

# Desk Monitoring

## L1 - Summary
Continuous oversight of desk health: open positions, exposure, daily P&L, and the circuit breaker. CHIEF owns the status picture; RUG feeds it post-entry safety state.

## L2 - Method
1. Publish the status block on every cycle:
```
DESK STATUS
UTC: ...
Engagement: research | paper
Open Positions: N
Total Exposure: $X
Daily P&L: ...
Circuit Breaker: OK | APPROACHING | HALTED
Active Alerts: ...
```
2. Engagement is `research` (no money, observation only) or `paper` (simulated fills via `tools/paper_sim.py`). There is no higher level on this desk.
3. Circuit breaker: when daily loss reaches 5 % of wallet equity, CHIEF posts `FLOOR HALTED - DAILY LOSS LIMIT` and refuses all new tickets until a human resets the halt.

## Failure modes
- Stale or missing position data: report the block with `stale` marked, never present guesses as live.
- Breaker approaching: warn early; halt is automatic at the threshold, not discretionary.
- Halt set: all new entries refuse; monitoring continues but nothing new opens.

## References
- CLI: `pumpgrok state status`, `pumpgrok rug watch`, `pumpgrok killswitch status`
- Companion skills: `desk-risk-limits` (thresholds), `position-monitoring` (position state)
