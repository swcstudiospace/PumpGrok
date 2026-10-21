---
name: position-monitoring
description: Continuous post-entry safety and performance watches for every open position. Used by RUG (safety) and EXIT (P&L and exit rules).
bots:
  - bot-05-rug
  - bot-06-exit
gates: []
---

# Position Monitoring

## L1 - Summary
Post-entry safety and performance watches for every open position. RUG owns the red-flag triggers; EXIT owns the P&L and exit rules. An alert prepares an emergency exit ticket; it never auto-sends.

## L2 - Method
1. Watch the red-flag triggers (RUG): significant LP removal or unlock, any mint event after entry, large insider or top-holder sells, freeze or tax change, suspicious program interactions.
2. Emit alerts with the schema:
```
POSITION / TICKET-ID: ...
Red Flag: <precise description>
Evidence: <links plus UTC>
Recommended Action: Emergency Exit / Watch / Escalate
```
3. EXIT rules: apply the pre-agreed take-profit, stop-loss, or trailing rules. On a RUG alert, prepare an emergency exit ticket and request human confirmation (unless auto-exit was pre-authorised).

## Failure modes
- Ambiguous trigger: Watch or Escalate, never Emergency Exit on a hunch.
- Alert without evidence links: inadmissible; re-issue with sources.
- RUG alert during a halt: the halt holds; the exit ticket waits for human reset.

## References
- CLI: `pumpgrok rug watch`, `pumpgrok paper sell`
- Companion skills: `desk-monitoring` (breaker), `desk-incident-response` (rug playbook)
