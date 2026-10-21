---
name: desk-strategy-lab
description: Lightweight rules and paper-trading support for entry filters, position sizing, and exit logic. Allows the desk to experiment without touching live capital until rules are proven.
bots:
  - bot-08-signal
  - bot-04-sniper
  - bot-06-exit
gates:
  - G-2
---

# Desk Strategy Lab

## L1 - Summary
The sandbox for entry filters, position sizing, and exit logic. Experiments run against paper fills only, so ideas succeed or fail on evidence without risking capital.

## L2 - Method
1. In paper mode, never call SNIPER for a real send. Log the simulated fill with:
```bash
python /workspace/pumpgrok/tools/paper_sim.py --action buy|sell --ticket <ID> \
  --mint <mint> --size-usd <usd> --price <price> ...
```
2. Changing rules: write any change into a dated file under `research/` and get explicit human approval before promotion to paper trading.
3. SIGNAL owns the scoring inputs (momentum, filters); SNIPER and EXIT validate that lab rules stay compatible with single-send and exit discipline.

## Failure modes
- Unproven rule promoted to tickets: refuse; evidence from paper runs is required first.
- Lab fill mistaken for a real fill: paper fills are simulation only and never enter the ledger as fills.
- Missing human approval for a rule change: the old rule stands.

## References
- Tools: `tools/paper_sim.py`, `tools/pipeline_evidence.py`
- Companion skills: `desk-trade-lifecycle` (ticket path), `position-monitoring` (exit rules)
