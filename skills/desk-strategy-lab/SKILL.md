---
name: desk-strategy-lab
description: Lightweight rules and paper-trading support for entry filters, position sizing, and exit logic. Allows the desk to experiment without touching live capital until rules are proven.
bots:
  - bot-06-exit
  - bot-08-signal
gates:
  - G-2
required_tools: []
required_data: []
permissions:
  max_side_effect: read
  network: true
  filesystem: var
---

# Desk Strategy Lab

## L1 - Summary
The sandbox for entry filters, position sizing, and exit logic. Experiments run against paper fills only, so ideas succeed or fail on evidence without risking capital.

## L2 - Method
1. Paper mode is the default; rule changes go through `replay-and-backtest` first:
```bash
pumpgrok run --mode paper --replay tests/fixtures/replay/<dataset>
```
2. Changing rules: write any change into a dated file under `research/` and get explicit human approval before promotion to paper trading. Each seat uses its own granted `exec.simulate` or `journal.append` for lab fills.
3. SIGNAL owns the scoring inputs (momentum, filters); EXIT validates that lab rules stay compatible with exit discipline and single-send.

## Failure modes
- Unproven rule promoted to tickets: refuse; evidence from paper runs is required first.
- Lab fill mistaken for a real fill: paper fills are simulation only and never enter the ledger as fills.
- Missing human approval for a rule change: the old rule stands.

## References
- Tools: `pumpgrok run --mode paper --replay`, `exec.simulate`, `tools/pipeline_evidence.py`
- Companion skills: `desk-trade-lifecycle` (ticket path), `position-monitoring` (exit rules)
