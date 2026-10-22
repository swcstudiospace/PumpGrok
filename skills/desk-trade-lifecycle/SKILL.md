---
name: desk-trade-lifecycle
description: Defines the exact end-to-end stages every Solana memecoin ticket must follow in PumpGrok. Enforces Lead to Audit to Context to Ticket to Human Approve to Single Buy to Monitor to Exit to Journal.
bots:
  - bot-00-chief
  - bot-01-scout
gates:
  - G-2
required_tools:
  - journal.append
required_data: []
permissions:
  max_side_effect: paper-write
  network: true
  filesystem: var
---

# Desk Trade Lifecycle

## L1 - Summary
The strict stage order every ticket follows: Lead (SCOUT), Audit (RISK), Context (WHALE plus SHILL), Ticket Creation (CHIEF), Human Approval, Single Buy (SNIPER), Monitor (RUG), Exit (EXIT), Journal (CHIEF plus EXIT). No stage may be skipped.

## L2 - Method
1. Run the stages in strict order:
   - Lead (SCOUT).
   - Audit (RISK).
   - Context (optional WHALE plus SHILL).
   - Ticket Creation (CHIEF): allocate with `pumpgrok ticket next`, write the proposal with `create`.
   - Human Approval: exact phrase with ticket ID, mint, size, and max slippage.
   - Single Buy (SNIPER).
   - Monitor (RUG).
   - Exit (EXIT).
   - Journal (CHIEF plus EXIT).
2. Ticket format is `SOL-YYYYMMDD-NNN`. Generate only via:
```bash
pumpgrok ticket next
pumpgrok ticket create --mint <MINT> --ticket <LEAD-ID> --status PENDING_HUMAN
```
3. Ticket operations run through the `pumpgrok ticket` verbs; the retired root-oracle `ticket_helper.py` spellings are gone with `tools/` (05-08).

## Failure modes
- Skipped stage: the ticket returns to the skipped stage; nothing downstream counts.
- SNIPER acting on a non-APPROVED ticket: refused.
- Size or mint changed after human approval: the approval is void; re-approve.

## References
- Tools: `pumpgrok ticket` (`next`, `create`, `list`)
- Companion skills: `desk-execution-protocol` (single-send), `desk-post-trade-review` (journal)
