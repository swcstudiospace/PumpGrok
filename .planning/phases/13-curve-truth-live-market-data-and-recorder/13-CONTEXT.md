# Phase 13: Curve truth, live market data and recorder - Context

**Gathered:** 2026-11-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement the read-only market feed, curve truth, deterministic paper pricing and marks, selectable paper fee model v2, and self-verifying recorder described in the Phase 13 roadmap. No transaction sending or live execution.
</domain>

<decisions>
## Implementation Decisions

### Curve and source truth
- Decode token-first 49- and 166-byte account layouts, validating discriminators and refusing unverified or unknown entry sources.
- Keep layout and event status ASSUMED until a human reviews the probe evidence. Never infer verification from successful decoding.

### Feed and recovery
- Reuse the event runtime and injected Clock. Bound the watchset, pin held mints, obey provider rate limits, deduplicate signatures and record reconnect gaps.
- Prices fail closed on disconnection or stale data; graduation refuses entry, and held positions follow the specified gap and timeout behavior.

### Recorder and paper execution
- Seal replay-compatible, digest-verified datasets with monotonic ticks and recorded gaps; recover torn tails without hiding corruption.
- Keep fee model v1 as the default; expose v2 as an explicit selection. Paper factories and entry hooks must not import live execution.
- Preserve both replay pins and document before and after hashes.

### Safety and process
- Research and paper only; no keys, signing, real-fund movement or automatic live promotion. Live mode remains refused.
- Follow path ownership and cross-seat protocol; use seat-owned branches, independent receipts and TDD RED/GREEN commits with plan-specific subjects.
- Phase 12 PRs 61-63 are merged, but its verification owner reports stale and its TDD review remains unresolved; do not assert Phase 12 verification was refreshed.

### Claude's Discretion
- Choose implementation details using existing patterns and the Phase 13 acceptance criteria; avoid new external providers.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/pumpgrok/events/` supplies the bounded event bus and source supervisor.
- `src/pumpgrok/tools/onchain/pump_events.py` decodes five event types; existing curve probe and replay loader provide starting points.
- `src/pumpgrok/execution/paper_adapter/` supplies existing paper execution.

### Established Patterns
- Monetary values use integer base units; timing uses the injected Clock; read-only network operations fail closed.
- Replay manifests validate dataset digests; path ownership is defined by `ownership.yaml`.

### Integration Points
- Bridge market events into the Phase 12 event catalog; integrate marks and pricing with paper execution without enabling live writes.
</code_context>

<specifics>
## Specific Ideas

Phase 14 onboarding depends on Phase 13 pricing and marks. Paper onboarding must not read or require a wallet.
</specifics>

<deferred>
## Deferred Ideas

Phase 14 onboarding, broader asset support, and any real-money trading remain outside Phase 13.
</deferred>
