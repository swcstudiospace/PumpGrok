---
name: holder-and-flow-analysis
description: Analyse early buyers, top-holder concentration, wallet clusters, and smart-money flows. Used by WHALE after RISK CLEAR or CONDITIONAL.
bots:
  - bot-03-whale
gates: []
required_tools:
  - onchain.top_holders
  - onchain.large_transfers
  - market.holders_snapshot
required_data:
  - solana_rpc
permissions:
  max_side_effect: read
  network: true
  filesystem: none
---

# Holder and Flow Analysis

## L1 - Summary
Smart-money and concentration analysis after RISK CLEAR or CONDITIONAL. Maps who holds the token, how concentrated it is, and whether flows look organic or coordinated. Informs sizing and risk; never authorises a buy.

## L2 - Method
1. Snapshot concentration with the preferred tool path:
```bash
python /workspace/pumpgrok/tools/holder_check.py --mint <TOKEN_MINT> --limit 20
```
2. Analyse early buyers, top-holder concentration, wallet clusters, and smart-money flows. Correlate with deployer history and large transfers where available.
3. Emit the output schema:
```
LEAD / TICKET-ID: ...
Smart-Money Signal: High | Medium | Low | None
Supporting Addresses: ...
Clusters Detected: yes/no plus description
UTC Timestamp: ...
Hand-off: CHIEF plus RISK
```

## Failure modes
- Sampled-only data: say so (the holder snapshot is sampled); never present it as a full census.
- Thin or missing flow evidence: signal `None`, not a guess.
- Social-only velocity with no holder evidence: not smart-money evidence.

## References
- Tools: `tools/holder_check.py`; port: `src/pumpgrok/tools/onchain/holders.py`
- Handoff: CHIEF plus RISK; companion skill: `risk-audit` (the gate this informs)
