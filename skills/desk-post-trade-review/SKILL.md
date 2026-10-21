---
name: desk-post-trade-review
description: Append-only journaling and structured review of every completed ticket. Separates process grade from outcome grade.
bots:
  - bot-09-journal
  - bot-06-exit
  - bot-00-chief
gates:
  - G-2
---

# Desk Post-Trade Review

## L1 - Summary
Structured review of every completed ticket, owned by JOURNAL with EXIT and CHIEF contributing. Grades the process independently of the outcome so the desk improves its decisions, not just its luck.

## L2 - Method
1. Log every completed ticket with the journal entry schema:
```
TICKET: SOL-YYYYMMDD-NNN
Mint: ...
Entry / Exit Time: ...
Size: ...
Realised P&L: ...
Process Grade: A / B / C / F
Outcome Grade: Win / Scratch / Loss
What Went Well: ...
What Broke: ...
Action Items: ...
```
2. Rules: append only, never delete or overwrite. Process grade is independent of outcome.
3. JOURNAL renders the daily and weekly reports from the ledger; CHIEF routes action items back into risk limits and strategy rules.

## Failure modes
- Missing entry data: mark fields `unavailable`, never invent fills or prices.
- Grading the outcome instead of the process: re-grade. A good process with a loss outranks a lucky win.
- Late or skipped reviews: the ticket stays open in the journal until reviewed.

## References
- CLI: `pumpgrok journal rollup`, `pumpgrok report --daily`, `pumpgrok report --weekly`
- Companion skills: `desk-folders-and-journal` (layout), `position-monitoring` (exit rules)
