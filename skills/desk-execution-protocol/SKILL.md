---
name: desk-execution-protocol
description: Hard rules that SNIPER and EXIT must obey before, during, and after every transaction. Enforces single-send, exact-parameter matching, and no-auto-retry.
bots:
  - bot-04-sniper
  - bot-06-exit
gates:
  - G-2
  - G-6
required_tools:
  - exec.quote
  - exec.simulate
  - exec.place
  - onchain.priority_fee
required_data:
  - jupiter
  - solana_rpc
permissions:
  max_side_effect: paper-write
  network: true
  filesystem: var
---

# Desk Execution Protocol

## L1 - Summary
The hard gate between an APPROVED ticket and a single paper send. SNIPER (buys) and EXIT (sells) may place exactly one order per approval through `exec.quote` then `exec.place`, with parameters matching the ticket exactly. Any error means stop and reconcile, never retry.

## L2 - Method
1. Run the pre-send checklist. ALL must pass:
   - Ticket status is APPROVED.
   - RISK verdict is CLEAR (or CONDITIONAL with every condition met).
   - The human message contains the exact ticket ID, mint, size, and max slippage.
   - The daily-loss limit is not breached.
   - A live quote was obtained within the last 30-60 s.
   - The returned mint and expected size match the approved ticket.
2. Prepare the route with the `jupiter-routing` skill (quote-only `api.jup.ag/swap/v2/order`, never `/execute`, `/build`, or `/submit`).
3. Simulate with `exec.quote`, then place once with `exec.place`.
4. On any error or timeout, stop and report `UNKNOWN RESULT - reconcile by signature`.

## Failure modes
- Checklist item fails: refuse the send and say which item failed.
- Timeout or ambiguous result: single-send rule holds. Never second-send; reconcile by signature first.
- Size, mint, or slippage drift from the ticket: refuse; only a new human approval can change parameters.
- RISK KILL at any point: the ticket path ends immediately.

## References
- Companion skill: `jupiter-routing` (route preparation feeding `exec.quote` and `exec.place`)
- Gate: G-2 approval gate, G-6 execution gate
- Ticket format: `SOL-YYYYMMDD-NNN`
