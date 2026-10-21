---
name: jupiter-routing
description: Primary execution path for PumpGrok. Obtain the best route via Jupiter. Set slippage and priority fees, verify exact parameters against the approved ticket, and prepare a single-send transaction. Used only by SNIPER and EXIT.
bots:
  - bot-04-sniper
  - bot-06-exit
gates:
  - G-6
required_tools:
  - exec.quote
  - onchain.priority_fee
required_data:
  - jupiter
  - solana_rpc
permissions:
  max_side_effect: read
  network: true
  filesystem: none
---

# Jupiter Routing

## L1 - Summary
Quote-only route preparation for the single approved buy (SNIPER) or sell (EXIT). Resolves the best Jupiter route for the exact ticket parameters through `GET https://api.jup.ag/swap/v2/order`, then hands the route to `exec.quote` and `exec.place`. This skill never executes, never signs, and never treats the quote as the fill price.

## L2 - Method
1. Take the APPROVED ticket parameters only: input mint, output mint, amount (lamports), max slippage bps. Refuse when the ticket is not APPROVED or RISK verdict is not CLEAR (CONDITIONAL conditions met counts as CLEAR only for the listed conditions).
2. Request a quote-only route: `GET https://api.jup.ag/swap/v2/order` with `inputMint`, `outputMint`, `amount`, `slippageBps`. Send the key as `x-api-key` from `JUPITER_API_KEY`. Never send `taker`. Never call `/execute`, `/build`, or `/submit`.
3. Treat the response as informational. Map `priceImpact` (percentage points) to a ratio by dividing by 100. The quote is never the fill price (R38).
4. Estimate the priority fee with `onchain.priority_fee`, capped by the `max_micro_lamports` field so a spike cannot drain the wallet. The quote is informational (route plus priority); only `exec.place` fills.
5. Hand the prepared route to `exec.quote` (simulate) and then `exec.place` (paper fill). On any timeout or unknown result, stop and report `UNKNOWN RESULT - reconcile by signature`. Never retry without a new human approval.

## Failure modes
- Stale quote (older than 30-60 s): re-quote before `exec.place`; never send on a stale route.
- Missing `JUPITER_API_KEY`: proceed keyless only where the endpoint allows, and say so in the handoff.
- Quote/fill confusion: the Jupiter response is a route plan, not a fill. The fill comes only from `exec.place`.
- Timeout or ambiguous send result: single-send rule holds. Report `UNKNOWN RESULT - reconcile by signature`, never second-send.
- Parameter drift (mint, size, slippage differ from the ticket): refuse and escalate to CHIEF + RISK.

## References
- Port: `src/pumpgrok/tools/market/jupiter.py` (quote-only v2 order adapter, R44)
- Execution: `exec.quote`, `exec.simulate`, `exec.place` (paper only; live refuses via `LiveGateError`)
- Gate: G-6 execution gate; precondition RISK CLEAR; approval record per ticket
- Companion skill: `desk-execution-protocol` (single-send, exact-parameter rules)
