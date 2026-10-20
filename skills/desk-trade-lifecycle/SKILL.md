---
name: desk-trade-lifecycle
description: Defines the exact end-to-end stages every Solana memecoin ticket must follow in PumpGrok. Enforces Lead → Audit → Context → Ticket → Human Approve → Single Buy → Monitor → Exit → Journal.
---

# Desk Trade Lifecycle

## Stages (strict order)
1. Lead (SCOUT)
2. Audit (RISK)
3. Context (optional WHALE + SHILL)
4. Ticket Creation (CHIEF) – allocate with `tools/ticket_helper.py next`, write the proposal with `create`
5. Human Approval (exact phrase with ticket ID + mint + size + max slippage)
6. Single Buy (SNIPER)
7. Monitor (RUG)
8. Exit (EXIT)
9. Journal (CHIEF + EXIT)

## Ticket Format
`SOL-YYYYMMDD-NNN`  
Generate only via:
```bash
python /workspace/pumpgrok/tools/ticket_helper.py next
python /workspace/pumpgrok/tools/ticket_helper.py create --mint <MINT> --ticket <LEAD-ID> --status PENDING_HUMAN
```

## Never
- Skip any stage
- Allow SNIPER to act on a ticket that is not APPROVED
- Change size or mint after human approval
