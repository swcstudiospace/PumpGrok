---
phase: 03-tools-and-skills
plan: "02"
subsystem: typed-tools
tags: [pydantic-v2, solana-rpc, bonding-curve, safety-scoring, httpx, mocktransport]

# Dependency graph
requires:
  - phase: 02-restructure
    provides: [RpcClient with policy retry and ordered failover, ported read functions, characterization pins]
  - phase: 03-tools-and-skills plan 01
    provides: [build_registry composition root, ToolSpec retry/rate-limit wiring, R23 keys, Decimal boundary, UpstreamModel]
provides:
  - 12 RPC-backed READ ToolSpecs (market.* + onchain.*) with freshness/source and extra-forbid inputs
  - ASSUMED bonding-curve decode shared by market.price and onchain.lp_status
  - safety.score_report with BLIND semantics and config-driven thresholds
  - GET-only social enrichment client with the non-vacuous SC4 guard
affects: [03-03, 03-04, 03-05, 03-06, 03-07]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
# Same estimateTokens scale (chars/4 over the realized diff), never a harness token count.
actuals:
  tokens: 36411
  tasks: 4
  commits: 6
  plan_head_before: d0667c4

# Tech tracking
tech-stack:
  added: []
  patterns: ["wrap-don't-edit ported oracles with Decimal-boundary converters", "build_*_tool(rpc) factories bound to one injected RpcClient", "BLIND CheckResult instead of exceptions for missing data"]

key-files:
  created: [src/pumpgrok/tools/onchain/curve_layout.py, src/pumpgrok/tools/market/price.py, src/pumpgrok/tools/market/ohlcv.py, src/pumpgrok/tools/market/liquidity.py, src/pumpgrok/tools/market/trades.py, src/pumpgrok/tools/market/holders_snapshot.py, src/pumpgrok/tools/onchain/token_metadata.py, src/pumpgrok/tools/onchain/authorities_tool.py, src/pumpgrok/tools/onchain/lp_status.py, src/pumpgrok/tools/onchain/top_holders.py, src/pumpgrok/tools/onchain/deployer_history.py, src/pumpgrok/tools/onchain/large_transfers.py, src/pumpgrok/tools/onchain/priority_fee_tool.py, src/pumpgrok/tools/safety/score_report.py, src/pumpgrok/tools/safety/checks/, src/pumpgrok/tools/social/client.py, src/pumpgrok/tools/_common.py, tests/tools/market/test_price.py, tests/tools/market/test_market_reads.py, tests/tools/onchain/test_onchain_reads.py, tests/tools/safety/test_score_report.py, tests/tools/safety/test_safety_settings.py, tests/tools/social/test_social_client.py, tests/safety/test_no_manipulation_tools.py]
  modified: [src/pumpgrok/tools/__init__.py, src/pumpgrok/config/settings.py, src/pumpgrok/config/overlays/paper.toml, src/pumpgrok/config/overlays/dev.toml, src/pumpgrok/config/overlays/live.toml]

key-decisions:
  - "Typed tools for the pinned authorities/priority_fee oracles live in authorities_tool.py/priority_fee_tool.py so the pinned files stay byte-identical"
  - "All envelope stamps and window cutoffs go through the replay Clock (utcnow); datetime.now trips the static guard"
  - "transfer_tax/honeypot/bundler_cluster are advisory blind; every runnable check that blinds forces KILL"
  - "ScoreReport gains a caller-supplied creator (mint account carries none); creator-share veto armed but dormant"
  - "Social enrichment stays unwired: token_metadata socials are null and market reads are RPC-only under strict B9"

patterns-established:
  - "run_<name>(input, rpc) returns a model-validated dict; build_<name>_tool(rpc) binds it behind @tool(SPEC)"
  - "Upstream failure or malformed payload raises DataStale; safety maps DataStale to blind, never an exception"
  - "Fixture clocks plus httpx.MockTransport; no live network in any test"

requirements-completed: [TOOL-001, TOOL-002, TOOL-003, TOOL-009]

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Tracer: market.price over the RPC curve layout with typed output, freshness/source, malformed-account DataStale"
    requirement: "TOOL-001"
    verification:
      - kind: unit
        ref: "tests/tools/market/test_price.py (5 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Market + onchain READ tools: 12 specs registered with dotted ids, freshness/source, extra-forbid, MockTransport only"
    requirement: "TOOL-001"
    verification:
      - kind: unit
        ref: "tests/tools/market/test_market_reads.py + tests/tools/onchain/test_onchain_reads.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "TOOL-002 onchain discipline: single RpcClient, ordered failover, header-only key, Decimal boundary, ported modules unedited"
    requirement: "TOOL-002"
    verification:
      - kind: unit
        ref: "tests/tools/onchain/test_onchain_reads.py::test_all_twelve_specs_register_with_dotted_ids"
        status: pass
    human_judgment: false
  - id: D4
    description: "safety.score_report: CLEAR/CONDITIONAL/KILL ladder, BLIND on missing data, config thresholds with override, 45s no-retry spec"
    requirement: "TOOL-003"
    verification:
      - kind: unit
        ref: "tests/tools/safety/test_score_report.py + tests/tools/safety/test_safety_settings.py (13 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Social GET-only client: SC4 grep prints nothing non-vacuously, AST write-verb scan, manipulation-stem guard"
    requirement: "TOOL-009"
    verification:
      - kind: unit
        ref: "tests/tools/social/test_social_client.py + tests/safety/test_no_manipulation_tools.py; ! grep -rnE ... src/pumpgrok/tools/social/"
        status: pass
    human_judgment: false
  - id: D6
    description: "ASSUMED bonding-curve layout confirmation pending with the user (B9)"
    verification: []
    human_judgment: true
    rationale: "The Anchor-style layout cannot be verified offline; only the user can confirm it against a mainnet account"

# Metrics
duration: 25min
completed: 2026-10-21
status: complete
---

# Phase 3 Plan 02: Read-Side Typed Tools Summary

**Twelve RPC-backed READ tools with freshness/source, a config-driven safety score_report with BLIND semantics, and a GET-only social client pinned by the non-vacuous SC4 guard — 58 plan tests green, full suite green.**

## Performance

- **Duration:** 25 min (first to last task commit, 11:33–11:58 UTC)
- **Started:** 2026-10-21T11:33:08Z
- **Completed:** 2026-10-21T11:58:17Z
- **Tasks:** 4
- **Files modified:** 33 (26 src, 7 tests)

## Accomplishments

- Tracer: `market.price` resolves via `build_registry` and returns typed output with `meta.source=solana_rpc` on an ASSUMED-fixture curve account; malformed accounts yield typed `DataStale`
- TOOL-001/TOOL-002: 4 market + 7 onchain ToolSpecs (R 10/15/20s, j4/j5, `solana_rpc`) wrapping — never editing — the ported oracles, Decimal conversion at the wrapper boundary, no REST fallback anywhere
- TOOL-003: `safety.score_report` (R, 45s, no retry) with 10 reasoned checks, config thresholds plus overlay values and env precedence, hard top-5 veto, KILL on blind-required
- TOOL-009 social clause: `tools/social/` GET-only enrichment client with the SC4 shell check printing nothing over a non-empty directory, plus the skeleton manipulation guard
- Static discipline held: replay-Clock-only time, header-only RPC key, no signing symbols, full `uv run pytest -q` green

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer: market.price over RPC curve layout end-to-end** - `09054c1` (feat)
2. **Task 2: Market + onchain READ tools (TOOL-001, TOOL-002)** - `1ef0eb1` (test, RED) + `b1f0bdf` (fix, GREEN)
3. **Task 3: Safety score_report with BLIND semantics (TOOL-003)** - `2c681ab` (feat)
4. **Task 4: Social GET-only client + non-vacuous guard (TOOL-009, SC4)** - `0c03bde` (feat)
5. **Clock-discipline fix (Rule 1, static guard)** - `a35bc63` (fix)

**Plan metadata:** n/a (sequential executor; no separate docs commit for the plan file)

_TDD task 2 carries RED then GREEN commits per the tdd execution flow._

## Files Created/Modified

- `src/pumpgrok/tools/_common.py` - shared MintStr, meta/utcnow stamps, J4/J5 policies (new)
- `src/pumpgrok/tools/onchain/curve_layout.py` - ASSUMED Anchor decode + price/progress/cap math (new)
- `src/pumpgrok/tools/market/price.py` - market.price ToolSpec + run/build (new)
- `src/pumpgrok/tools/market/ohlcv.py` - local candle aggregation over the trade stream (new)
- `src/pumpgrok/tools/market/liquidity.py` - reserves + impact from the curve account (new)
- `src/pumpgrok/tools/market/trades.py` - signature/transaction classification buy/sell (new)
- `src/pumpgrok/tools/market/holders_snapshot.py` - sampled share view wrapping holder_snapshot (new)
- `src/pumpgrok/tools/onchain/token_metadata.py` - mint fields wrapping check_mint (new)
- `src/pumpgrok/tools/onchain/authorities_tool.py` - authority flags wrapping check_mint (new; pinned file untouched)
- `src/pumpgrok/tools/onchain/lp_status.py` - stage from the curve account (new)
- `src/pumpgrok/tools/onchain/top_holders.py` - supply-based concentration wrapping holder_snapshot (new)
- `src/pumpgrok/tools/onchain/deployer_history.py` - signature-window creator history (new)
- `src/pumpgrok/tools/onchain/large_transfers.py` - whale movement scan with sell/transfer kinds (new)
- `src/pumpgrok/tools/onchain/priority_fee_tool.py` - capped estimate wrapping the oracle (new; pinned file untouched)
- `src/pumpgrok/tools/safety/score_report.py` - 10-check scored report, BLIND semantics (new)
- `src/pumpgrok/tools/safety/checks/` - CheckResult envelope + authority/reader checks (new)
- `src/pumpgrok/tools/social/client.py` - GET-only venue enrichment (new)
- `src/pumpgrok/tools/__init__.py` - `register_read_tools()` composition helper
- `src/pumpgrok/config/settings.py` - `SafetyThresholds`/`SafetySettings` + `safety` section
- `src/pumpgrok/config/overlays/{paper,dev,live}.toml` - `[safety.thresholds]` values
- `tests/tools/market/test_price.py`, `tests/tools/market/test_market_reads.py` - market fixtures (new)
- `tests/tools/onchain/test_onchain_reads.py` - onchain fixtures incl. 12-spec registration (new)
- `tests/tools/safety/test_score_report.py`, `tests/tools/safety/test_safety_settings.py` - safety + precedence (new)
- `tests/tools/social/test_social_client.py` - GET-only pins (new)
- `tests/safety/test_no_manipulation_tools.py` - SC4 skeleton, non-vacuous (new)

## Decisions Made

- Typed tools for the pinned `authorities.py`/`priority_fee.py` oracles live in `*_tool.py` siblings so characterization pins stay byte-identical (plan's file list predates the wrap-don't-edit constraint)
- `creator` added to `ScoreReportIn` (caller-supplied; the mint account carries none, so the check is blind without it); creator-share veto armed but dormant while off-chain enrichment is unwired
- Advisory trio (`transfer_tax`, `honeypot`, `bundler_cluster`) is blind-by-construction and never forces the verdict; every runnable check that blinds forces KILL (fail-closed constitution)
- `authorities.slot` stays null (ported oracle drops `context.slot`; the wrapper does not re-fetch for one field); `token_metadata` off-chain fields stay null (RPC-only under strict B9)
- `large_transfers` gains a `limit` field (1..20, default 10) bounding the wallet fan-out; `priority_fee.accounts` is accepted but sampled globally per the ported oracle
- Social enrichment is not wired into `token_metadata`/`market.trades` yet: strict B9 keeps every market read RPC-only; a later plan composes the GET client

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Typed tools for pinned oracles live in `*_tool.py` siblings**
- **Found during:** Task 2 (GREEN implementation)
- **Issue:** Plan's file list names `authorities.py` and `priority_fee.py` for the new specs, but those files hold the characterization-pinned oracle functions; editing them violates T-03-02-03 wrap-don't-edit
- **Fix:** New specs live in `authorities_tool.py` and `priority_fee_tool.py`; ported files byte-identical
- **Files modified:** the two new modules + `tools/__init__.py` registration
- **Verification:** full suite green incl. characterization pins
- **Committed in:** b1f0bdf

**2. [Rule 2 - Missing critical] Shared `_common.py` helper plus `register_read_tools`**
- **Found during:** Task 1 (tracer setup)
- **Issue:** 12 modules need one mint validator, one meta constructor, and the j4/j5 policies; duplicating them is dead weight
- **Fix:** `src/pumpgrok/tools/_common.py` (MintStr, `meta_now`, `utcnow`, J4/J5, constants) and `register_read_tools(registry, rpc)` on the composition root
- **Files modified:** `tools/_common.py`, `tools/__init__.py`
- **Verification:** 12-spec registration test resolves every dotted id
- **Committed in:** 09054c1 (helper), b1f0bdf (registration)

**3. [Rule 1 - Bug] Replay-clock discipline for envelope stamps**
- **Found during:** Task 3 verification (full suite, not the plan's scoped selector)
- **Issue:** `datetime.now` in `_common.meta_now`, `deployer_history` cutoff, and two `score_report` evidence stamps trips `test_src_pumpgrok_has_no_forbidden_primitives`
- **Fix:** `utcnow()` helper via `WallClock().now()`; identical stamp values, no behavior change
- **Files modified:** `tools/_common.py`, `tools/onchain/deployer_history.py`, `tools/safety/score_report.py`
- **Verification:** full `uv run pytest -q` exit 0
- **Committed in:** a35bc63

**4. [Rule 2 - Missing critical] Catalog-shape adjustments with documented reasons**
- **Found during:** Tasks 2–3 (implementation)
- **Issue:** Catalog inputs assume data Phase 3 cannot produce (curve account for RPC reads, creator for deployer history, wallet fan-out bound)
- **Fix:** `curve_account` on price/liquidity/lp_status; `creator` on score_report; `limit` on large_transfers; slot/off-chain/social fields null with reasons
- **Files modified:** the respective tool modules
- **Verification:** pinned by fixture tests asserting the nulls and bounds
- **Committed in:** b1f0bdf, 2c681ab

---

**Total deviations:** 4 auto-fixed (1 blocking, 2 missing-critical, 1 bug)
**Impact on plan:** All required for correctness or guard compliance; no scope creep. No architectural changes (Rule 4 never triggered).

## Issues Encountered

- Bash live output mis-renders pytest runs (known runner quirk, also noted in 03-01): every verify below comes from output redirected to files with recorded exit codes
- `find()` requires a bound correlation id (registry I4): test helpers bind `CorrelationId.new(IdFactory(...))` around resolve/call, matching the 03-01 tracer pattern
- Edit-tool range friction on long files: two patches landed mid-function and were repaired by re-read plus targeted CUT/PUT; final files parse and the suite is green
- Over-strict self-test markers (`dict.get(` flagged as REST, docstrings naming forbidden hosts) tripped the tracer's own no-fallback scan; reworded to hostname-free prose and dict-access-safe markers

## Verification evidence (all exit codes recorded)

- `uv run pytest -q tests/tools/market/test_price.py` → exit 0 (5 tests, task 1 gate)
- `uv run pytest -q tests/tools/market tests/tools/onchain` → exit 0 (task 2 gate)
- `uv run pytest -q tests/tools/safety` → exit 0 (13 tests, task 3 gate)
- `! grep -rnE "\b(post|put|patch|delete)\b|method=['\"](POST|PUT|PATCH|DELETE)" src/pumpgrok/tools/social/` → prints nothing (SC4 social half, non-vacuous: dir holds 2 modules); `uv run pytest -q tests/tools/social tests/safety/test_no_manipulation_tools.py` → exit 0 (9 tests, task 4 gate)
- Plan-level: `uv run pytest -q tests/tools/market tests/tools/onchain tests/tools/safety tests/tools/social tests/safety/test_no_manipulation_tools.py` → exit 0 (58 tests)
- Full `uv run pytest -q` → exit 0 (no regressions; static guards, characterization, and the SC5-scoped greps hold)

## Known Stubs

None - no stubs, placeholders, or TODOs introduced. `blind` is a first-class check status with a reason string, not a stub; null LP/off-chain/social fields are documented unwired-data, each with a named future composer.

## Threat Flags

None beyond the plan's register: T-03-02-01 (ASSUMED layout, fixture-marked, D6 user-confirmation pending), T-03-02-02 (social GET, no key in URL/log, UpstreamModel extra-ignore), T-03-02-03 (wrap-don't-edit, pins green), T-03-02-SC (MockTransport only, no new packages).

## Auth Gates

None - no authentication was required.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Later plans can register catalog tools through `register_read_tools()` and compose the seven safety readers; `build_score_report_tool(rpc, thresholds)` accepts config or override thresholds
- Blockers for the orchestrator: (a) ASSUMED curve layout still needs user confirmation (D6); (b) ROADMAP Phase 3 `Plans:` is still `TBD` with no per-plan rows, so no roadmap plan-progress update was possible (same as 03-01); (c) social enrichment wiring into `token_metadata`/trades awaits a composer plan; (d) creator-share veto stays dormant until off-chain enrichment lands

---
*Phase: 03-tools-and-skills*
*Completed: 2026-10-21*

## Self-Check: PASSED

- All 33 created/modified files present on disk (26 src + 7 tests; verified via `git diff d0667c4..HEAD --stat`).
- All 6 task commits present (`09054c1`, `1ef0eb1`, `b1f0bdf`, `2c681ab`, `0c03bde`, `a35bc63`).
- Plan-level pytest exit 0 (58 tests); full suite exit 0; SC4 social grep prints nothing.
