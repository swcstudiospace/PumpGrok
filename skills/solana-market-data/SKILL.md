---
name: solana-market-data
description: Fetch and structure live market data for any Solana mint - price, liquidity, volume, bonding-curve progress, and multi-DEX depth.
bots:
  - bot-01-scout
  - bot-03-whale
  - bot-04-sniper
  - bot-05-rug
  - bot-08-signal
gates: []
required_tools: []
required_data:
  - solana_rpc
  - jupiter
permissions:
  max_side_effect: read
  network: true
  filesystem: none
---

# Solana Market Data

## L1 - Summary
Live market data for any Solana mint: price, liquidity, volume, bonding-curve progress, and multi-DEX depth. Shared by six seats; every figure carries a source and a UTC timestamp.

## L2 - Method
1. Preferred sources: Solana JSON-RPC (price, liquidity, holders), Jupiter v2 order quote (route reference), pump.fun REST (launch state), PumpPortal WS (migrations). Every seat uses its own granted `market.*` subset.
2. Emit the output schema:
```
MINT: ...
UTC: ...
Price SOL / USD: ...
Liquidity: ...
Volume 1h: ...
Bonding Curve: ... % (or graduated)
Holders (approx): ...
Sources: [list]
```

## Failure modes
- Single-source figure: corroborate before it enters a ticket; one source is a hint, not evidence.
- Stale quote: timestamp everything; RISK treats undated figures as `BLIND`.
- Graduated vs bonding-curve confusion: state which regime the token is in.

## References
- Tools: `market.price`, `market.liquidity`, `market.trades`; port: `src/pumpgrok/tools/market/jupiter.py`
- Handoff: LEAD block (`discovery-tools`); gate: `risk-audit`
