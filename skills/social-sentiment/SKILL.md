---
name: social-sentiment
description: Score social and narrative velocity and quality for a lead or open position. Used by SHILL. Never clears risk or recommends size.
bots:
  - bot-07-shill
  - bot-01-scout
gates: []
required_tools:
  - onchain.token_metadata
  - market.trades
required_data:
  - solana_rpc
permissions:
  max_side_effect: read
  network: true
  filesystem: none
---

# Social Sentiment

## L1 - Summary
Detection-only scoring of social and narrative velocity and quality. SHILL measures how fast a story spreads and whether it looks organic; it never clears risk and never recommends size.

## L2 - Method
1. Collect velocity and quality signals from public posts, listings, and charts (browser observation only, per `browser-ops`).
2. Emit the output schema:
```
LEAD / POSITION-ID: ...
Velocity Score: High | Medium | Low
Quality: Organic | Mixed | Coordinated / Paid
Sources: <list>
Notes: <any distribution-risk flags>
Hand-off: CHIEF plus RISK
```

## Failure modes
- Coordinated or paid activity: flag it; never launder it as organic interest.
- Pure velocity with no quality: velocity alone is never a buy signal.
- Missing sources: the score is inadmissible without them.

## References
- Companion skills: `browser-ops` (observation rules), `discovery-tools` (lead surfaces)
- Handoff: CHIEF plus RISK; never a clearance
