---
name: desk-risk-limits
description: Interview the user, write, and enforce the capital and loss rules for the PumpGrok desk. Produces risk-limits.md. Used primarily by RISK and CHIEF.
bots:
  - bot-02-risk
  - bot-00-chief
gates:
  - G-4
  - G-6
---

# Desk Risk Limits

## L1 - Summary
The capital and loss rules that bound every ticket. RISK interviews the user, writes `risk-limits.md`, and enforces it with an absolute veto. CHIEF checks the daily-loss state before allowing new tickets.

## L2 - Method
1. Run the initial interview. Ask the user:
   - Maximum throwaway capital (recommended at most $200 USDC).
   - Maximum size per trade.
   - Maximum concurrent open positions.
   - Daily loss halt percentage (default 5 %).
   - Forbidden criteria.
   - Preferred engagement level (`research` or `paper`).
2. Write `/workspace/trading-desk/risk-limits.md` with the agreed numbers.
3. Enforce: RISK refuses any ticket that violates these limits. CHIEF checks daily loss before allowing new tickets. Any change requires new human confirmation.

## Failure modes
- No agreed limits on file: the desk stays in `research`; nothing advances to tickets.
- Ticket breaches a limit: refused, no exceptions, no partial fills to fit.
- Stale limits after equity changes: re-interview before new entries.

## References
- Policy: `docs/RISK_POLICY.md`; settings overlay `[risk]` block
- CLI: `pumpgrok risk audit`, `pumpgrok state status`
- Companion skills: `risk-audit` (per-ticket gate), `desk-monitoring` (breaker status)
