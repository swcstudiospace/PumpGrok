---
name: discovery-tools
description: How SCOUT finds, filters, and structures high-signal Solana memecoin leads from pump.fun, gmgn.ai, Photon, Axiom, and social sources. Produces the standard LEAD block.
bots:
  - bot-01-scout
  - bot-03-whale
  - bot-07-shill
gates: []
required_tools:
  - market.trades
required_data:
  - solana_rpc
permissions:
  max_side_effect: read
  network: true
  filesystem: none
---

# Discovery Tools

## L1 - Summary
How SCOUT finds, filters, and structures high-signal leads. Covers the primary surfaces, the mandatory LEAD block, and the handoff to RISK. WHALE and SHILL reuse these surfaces for flow and sentiment context.

## L2 - Method
1. Scan the primary surfaces: pump.fun, gmgn.ai, Photon / Axiom, Solscan recent deployments, high-signal X and Telegram channels.
2. Emit every candidate with the mandatory output schema:
```
LEAD-ID: SOL-YYYYMMDD-NNN
Mint: <full address>
Source: <URL or tx signature>
Age: <minutes>
Initial Liquidity: <SOL or USD>
Mint Authority (visible): <status>
Early Signals: ...
Why this lead: <1-2 precise sentences>
Hand-off to RISK: YES
UTC Timestamp: <ISO>
```
3. Never recommend buy size or urgency, never clear risk, and never surface leads without a verifiable mint and source.

## Failure modes
- Unverifiable mint or source: the lead is dropped, not surfaced with caveats.
- Stale surface data: timestamp it; RISK treats undated leads as `BLIND`.
- Flood of weak leads: prefer fewer, better-evidenced leads over volume.

## References
- Tools: `tools/pipeline_evidence.py` (vendored pipeline candidates)
- Handoff: RISK via `risk-audit`; schema: LEAD block above
