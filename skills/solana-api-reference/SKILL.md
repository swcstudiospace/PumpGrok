---
name: solana-api-reference
description: Exact request shapes, response fields, and unit traps for every Solana surface the desk touches (JSON-RPC, Jupiter v2 order, pump.fun REST, PumpPortal WS). Read before writing any new call.
bots:
  - bot-04-sniper
  - bot-02-risk
gates: []
---

# Solana API Reference

## L1 - Summary
The exact request shapes, response fields, and unit traps for every Solana surface the desk touches. Read this before writing any new call; never guess an endpoint.

## L2 - Method
1. Jupiter: quote-only `GET https://api.jup.ag/swap/v2/order` with `inputMint`, `outputMint`, `amount`, `slippageBps` and `x-api-key` from `JUPITER_API_KEY`. Never send `taker`. Never call `/execute`, `/build`, or `/submit`. Unit trap: v2 `priceImpact` is percentage points; divide by 100 for a ratio. The quote is informational, never the fill.
2. Solana RPC (common): `getBalance`, `getTokenAccountsByOwner`, `getAccountInfo` (mint / freeze authority), `getRecentPrioritizationFees`, `getTokenLargestAccounts`, `getTransaction` / `getSignaturesForAddress`.
3. Usage rule: when in doubt about an endpoint, re-read this skill or the live documentation rather than guessing.

## Failure modes
- Deprecated v1 swap endpoints: do not use them; v2 order is the only Jupiter path.
- Guessed parameters: rejected. Every field above is exact.
- Quote treated as fill: the fill comes only from `exec.place`.

## References
- Port: `src/pumpgrok/tools/market/jupiter.py`, `src/pumpgrok/tools/onchain/`
- Companion skill: `jupiter-routing` (route preparation), `solana-rpc-and-wallet` (wallet rules)
