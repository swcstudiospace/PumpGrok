# Future multi-venue desk note (docs only, 2026-11-22)

Owner 2026-11-22 decision: extend v4 Phase 19 docs only. No code, no new
phases. The ideas below are parked for a future milestone, not claimed
as built.

## Current truth (verified 2026-11-22)

- Paper-only desk on pump.fun/Solana. Live refuses with exit 3.
- Seat prompts in XML: `prompts/bot-*.xml` assemble to
  `prompts-assembled/*.xml`; `scripts/assemble-prompts.sh --check` clean.
  Prompt shape follows the programming-desk pattern (identity, mission,
  owned paths, skills, tools contract, body) — already XML at source.
- Sizing/limits live in `docs/RISK_POLICY.md` and the risk engine; no
  $200-cap / $20-step rule exists in code today.
- Venues today: Solana mainnet JSON-RPC, pump.fun REST, PumpPortal WS,
  Jupiter Swap V2 order, x.ai Grok (see docs/VENDOR_PIN.md). No second
  trading-venue adapter exists by design in v4.

## Parked ideas (need a new milestone to build)

- Multi-venue adapter registry (paper first, per-venue idempotency keys).
- Notional cap = $200 and step = $20 (amend RISK_POLICY + engine + tests).
- Richer XML prompt sections (long detailed instructions) via the existing
  assemble pipeline; no prompt rewrites in v4.

## Explicitly not doing here

- No venue code, no sizing change, no prompt rewrite, no new ROADMAP
  phases. A `/gsd-new-milestone` would scope these as v5.
