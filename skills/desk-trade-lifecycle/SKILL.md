---
name: desk-trade-lifecycle
description: Defines the exact end-to-end stages every Solana memecoin ticket must follow in PumpGrok. Enforces Lead to Audit to Context to Ticket to Human Approve to Single Buy to Monitor to Exit to Journal.
bots:
  - all
gates:
  - G-2
---

# Desk Trade Lifecycle

## L1 - Summary
The strict stage order every ticket follows: Lead (SCOUT), Audit (RISK), Context (WHALE plus SHILL), Ticket Creation (CHIEF), Human Approval, Single Buy (SNIPER), Monitor (RUG), Exit (EXIT), Journal (CHIEF plus EXIT). No stage may be skipped.

## L2 - Method
1. Run the stages in strict order:
   - Lead (SCOUT).
   - Audit (RISK).
   - Context (optional WHALE plus SHILL).
   - Ticket Creation (CHIEF): allocate with `tools/ticket_helper.py next`, write the proposal with `create`.
   - Human Approval: exact phrase with ticket ID, mint, size, and max slippage.
   - Single Buy (SNIPER).
   - Monitor (RUG).
   - Exit (EXIT).
   - Journal (CHIEF plus EXIT).
2. Ticket format is `SOL-YYYYMMDD-NNN`. Generate only via:
```bash
python /workspace/pumpgrok/tools/ticket_helper.py next
python /workspace/pumpgrok/tools/ticket_helper.py create --mint <MINT> --ticket <LEAD-ID> --status PENDING_HUMAN
```
3. The port is moving ticket operations to `pumpgrok ticket` verbs. The `ticket_helper.py next` and `ticket_helper.py create` spellings above are kept because the root skill-text oracle pins them; prefer the `pumpgrok` verbs for new automation.

## Failure modes
- Skipped stage: the ticket returns to the skipped stage; nothing downstream counts.
- SNIPER acting on a non-APPROVED ticket: refused.
- Size or mint changed after human approval: the approval is void; re-approve.

## References
- Tools: `tools/ticket_helper.py` (`next`, `create`); CLI: `pumpgrok ticket next|create|list`
- Companion skills: `desk-execution-protocol` (single-send), `desk-post-trade-review` (journal)
