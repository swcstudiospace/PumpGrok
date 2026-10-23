---
phase: 04-paper-trading-and-autonomy
plan: 04
subsystem: execution
tags: [paper-trading, curve-math, fees, latency, graduation, blind-flatten, r65, fail-closed]
requires:
  - phase: 04-01
    provides: append_batch transaction primitive the OrderPlaced batch uses
  - phase: 04-05
    provides: 19-step RiskEngine.check with bound RiskDecision rows
provides:
  - Pure integer curve math with fee and seeded-latency models
  - PaperAdapter with risk-in-process, shared OrderPlaced batch, CONFIRMING re-checks
  - Graduation and blind-flatten force-closes with frozen marks and Escalations
  - R65 probe record (ASSUMED) with fail-closed data_unavailable entry gate
affects: [04-06, 04-07]
actuals:
  tokens: 22417
  tasks: 3
  commits: 3
tech-stack:
  added: []
  patterns: [curve-derived fills, confirm-recompute slippage, in-flight barrier, frozen-mark force-close]
key-files:
  created:
    - src/pumpgrok/execution/curve_math.py
    - src/pumpgrok/execution/fees.py
    - src/pumpgrok/execution/latency.py
    - src/pumpgrok/execution/paper_adapter.py
    - tests/execution/test_curve_math.py
    - tests/execution/test_paper_adapter.py
    - tests/execution/test_graduation_blind.py
    - tests/fixtures/rpc/bonding_curve/layout.json
  modified:
    - src/pumpgrok/execution/__init__.py
    - src/pumpgrok/ledger/events.py
    - src/pumpgrok/tools/onchain/curve_layout.py
key-decisions:
  - "Fill carries curve_before/curve_after reserve pairs; rejections carry quote_out/threshold/confirm_out for slippage explainability"
  - "Simulate is a pure-math preview with no ledger writes; risk stays out so a read-only call cannot append halt rows"
  - "Force-close proceeds net of venue fee only; no network cost since nothing is broadcast"
  - "RPC-origin entries refuse data_unavailable via an OrderRejected row; the read path still decodes"
  - "Probe failure recorded verbatim; fixture stays ASSUMED, never VERIFIED without decoded bytes"
requirements-completed: [PAPER-001, PAPER-005]
coverage:
  - id: D1
    description: "One BUY flows through risk, ledger batch, latency, CONFIRMING to a curve-priced fill"
    requirement: "PAPER-001"
    verification:
      - kind: unit
        ref: "tests/execution/test_paper_adapter.py::test_one_buy_flows_to_curve_priced_fill"
        status: pass
    human_judgment: false
  - id: D2
    description: "Liquidity floor, partial fills, slippage, tx_dropped, and sell mirror behave per R6 with seeded determinism"
    requirement: "PAPER-001"
    verification:
      - kind: unit
        ref: "tests/execution/test_paper_adapter.py"
        status: pass
      - kind: unit
        ref: "tests/execution/test_curve_math.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Graduation rejects buys and force-closes at last sell_out; blind timeout closes at last_good"
    requirement: "PAPER-005"
    verification:
      - kind: unit
        ref: "tests/execution/test_graduation_blind.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "R65 probe honestly recorded ASSUMED; RPC entries fail closed while ASSUMED"
    requirement: "PAPER-005"
    verification:
      - kind: unit
        ref: "tests/execution/test_graduation_blind.py::test_layout_fixture_matches_code_status"
        status: pass
    human_judgment: false
duration: 21min
completed: 2026-10-21
status: complete
---

# Phase 04 Plan 04: Curve-Faithful Paper Fills Summary

**Pure integer curve fills with venue/base/priority fees, seeded latency, risk-bound CONFIRMING re-checks, graduation and blind force-closes, and an ASSUMED R65 probe record gating RPC entries to data_unavailable**

## Performance

- **Duration:** 21 min
- **Started:** 2026-10-21T20:09:37Z
- **Completed:** 2026-10-21T20:30:47Z
- **Tasks:** 3
- **Files modified:** 15

## Accomplishments

- One BUY flows risk check, shared OrderPlaced batch, seeded latency, CONFIRMING re-read, and lands as a curve-priced fill with reserve pairs on the Fill event
- Liquidity floor, fill cap partials, slippage-exceeded network-cost-only rejects, seeded tx_dropped, and the sell mirror all behave per R6 with same-seed replay equality
- Graduated buys reject; graduation force-closes at last pre-graduation sell_out; 300 s blind silence closes at last_good; both freeze the mark and escalate
- R65 probe ran against mainnet: getHealth ok, program scan timed out twice, fixture stays ASSUMED with verbatim errors; RPC-origin entries refuse data_unavailable

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer: one curve BUY from reserves to FillRecorded** - `3957019` (feat)
2. **Task 2: Liquidity gates, partials, slippage, tx_dropped, sells** - `26305df` (feat)
3. **Task 3: Graduation, blind flatten, R65 probe, fail-closed gate** - `aa08e68` (feat)

**Plan metadata:** pending (docs: complete plan commit below)

## Verify runs (exit codes)

- `uv run pytest -q tests/execution/test_paper_adapter.py` exit 0, 4 passed (Task 1)
- `uv run pytest -q tests/execution/` exit 0, 21 passed (Task 2)
- `uv run pytest -q tests/execution/` exit 0, 29 passed (Task 3)
- `uv run pytest -q` exit 0, 1099 passed, 2 skipped (closing gate)
- `uv run ruff check .` exit 0, no issues (closing gate)
- `uv run ruff format --check .` exit 0, 435 files formatted (closing gate)
- `uv run mypy src/` exit 0, no issues in 143 files (closing gate)

## R65 probe result

- **Endpoint:** `https://api.mainnet-beta.solana.com` (no key sent)
- **Exact outcome:** `getHealth` returned HTTP 200 `{"result":"ok"}` in 0.07 s. `getProgramAccounts` on program `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` with filter `dataSize 49` failed twice: `TimeoutError: read timed out` at a 20 s timeout, then the retry hit the 90 s command timeout with no response. No account bytes were observed, no decode was attempted, and no discriminator was observed.
- **Fixture status:** `tests/fixtures/rpc/bonding_curve/layout.json` records `layout_status: ASSUMED` with the verbatim probe error. Never marked VERIFIED. The `test_layout_fixture_matches_code_status` test asserts fixture status equals `LAYOUT_STATUS` and that RPC prices are refused while ASSUMED.

## Files Created/Modified

- `src/pumpgrok/execution/curve_math.py` - spot, buy_out, sell_out, impacts, post states; integers in, Decimal out only
- `src/pumpgrok/execution/fees.py` - FeeModel: venue 100 bps, base 5000, priority micro*CU//1e6, network cost
- `src/pumpgrok/execution/latency.py` - seeded lognormal latency plus p_drop draw from one rng
- `src/pumpgrok/execution/paper_adapter.py` - place/quote/simulate/cancel/positions, CONFIRMING helper, graduation, blind, MTM, frozen marks, repeat-returns-first-fill
- `src/pumpgrok/execution/__init__.py` - build_adapter factory (registry swap stays in 04-07)
- `src/pumpgrok/ledger/events.py` - FillRecorded gains curve_before/after pairs, route, realised slippage; OrderRejected gains quote_out/threshold/confirm_out
- `contracts/events/fill_recorded.schema.json`, `order_rejected.schema.json` - regenerated; `journal_note.schema.json` drift fixed
- `src/pumpgrok/tools/onchain/curve_layout.py` - LAYOUT_STATUS ASSUMED plus rpc_curve_price_allowed gate
- `tests/execution/test_curve_math.py` - 8 golden-vector, invariant, fee, and determinism tests
- `tests/execution/test_paper_adapter.py` - 13 tracer, repeat, gate, slippage, drop, determinism, and sell tests
- `tests/execution/test_graduation_blind.py` - 8 graduation, blind, MTM, gate, and fixture tests
- `tests/fixtures/rpc/bonding_curve/layout.json` - ASSUMED probe record with verbatim errors

## Decisions Made

- Fill carries curve_before/curve_after reserve pairs; rejections carry quote_out/threshold/confirm_out for slippage explainability (design 3.3, resolution Q8)
- Simulate is a pure-math preview with no ledger writes: running the real risk check inside simulate could append halt rows, which a read-only preview must never do
- Force-close proceeds are net of venue fee only; no network cost is charged since nothing is broadcast
- RPC-origin entries refuse with an OrderRejected row carrying data_unavailable, so the refusal is auditable; the market.price read path still decodes (entry gate, not read gate)
- The probe failure is recorded verbatim in the fixture; the layout stays ASSUMED and no entry may consume an RPC-derived price until a decoded probe plus human review flips it

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Regenerated schemas fixed journal_note drift**
- **Found during:** Task 1 (schema regeneration)
- **Issue:** `contracts/events/journal_note.schema.json` carried the old skip-cycle description while the model already said replay cycle; the generator `--check` gate would fail
- **Fix:** Regenerated all 18 schemas from the models; only fill, reject, and the drifted journal note changed
- **Files modified:** contracts/events/*.schema.json
- **Verification:** generator rerun clean; `tests/ledger/test_events.py` passes
- **Committed in:** 3957019 (Task 1 commit)

**2. [Rule 1 - Bug] Sell test hit data_stale on the confirm read**
- **Found during:** Task 2 (sell mirror test)
- **Issue:** The risk step 17 `data_stale` correctly refused the sell because no MarkToMarket existed yet after the buy
- **Fix:** Test marks to market before selling, matching the production journal-seat cadence
- **Files modified:** tests/execution/test_paper_adapter.py
- **Verification:** tests/execution/ 21 passed
- **Committed in:** 26305df (Task 2 commit)

**3. [Rule 1 - Bug] Store rows return payload_json, not payload**
- **Found during:** Task 3 (graduation/blind tests)
- **Issue:** Tests read `closed["payload"]` off `append`/`append_batch` return rows, which carry `payload_json`; only `read()` rows parse to `payload`
- **Fix:** Tests parse `payload_json` for adapter-returned rows
- **Files modified:** tests/execution/test_graduation_blind.py
- **Verification:** tests/execution/ 29 passed
- **Committed in:** aa08e68 (Task 3 commit)

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking drift)
**Impact on plan:** All required for green gates or correct engine semantics. No scope creep: the ToolRegistry factory swap stays in plan 04-07, autonomous-mint persistence stays in 04-07, and no new packages were added (T-04-SC holds).

**Note:** Task 2 required no production-code changes: the Task 1 adapter already carried the sell path, floor, cap, slippage, and drop logic, so the Task 2 commit is tests-only. The commit message overstates src churn; the diff is the record.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: tampering-surface | src/pumpgrok/execution/paper_adapter.py | Fill prices derive only from curve reserves; the Jupiter quote_id is stored on OrderPlaced with source=curve and never enters fill math (T-04-08 mitigated) |
| threat_flag: spoofing-surface | tests/fixtures/rpc/bonding_curve/layout.json | Untrusted RPC bytes cannot price entries while ASSUMED; the gate refuses with data_unavailable (T-04-09 mitigated) |

No new network, auth, or package surface: the adapter is ledger-plus-clock only, and the probe ran as an operator command outside the suite (T-04-SC holds).

## Issues Encountered

- The shared-shell pytest runner prints "No tests collected" on piped output; redirecting to a file shows the true counts (same as 04-01/04-02 notes)
- `getProgramAccounts` with a `dataSize 49` filter is too heavy for the public RPC endpoint: 20 s read timeout, then a 90 s command timeout on retry. Recorded verbatim; a paid endpoint or a known mint is needed for a conclusive probe (04-07 or human follow-up)
- Edit-tool anchor drift after ruff format runs: re-read the touched region before re-issuing; no residue (format and mypy green)

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- PaperAdapter plus curve math, fees, and latency are ready for 04-07 CLI wiring (`paper buy|sell`, TOOL-004 consume-and-order persistence, ToolRegistry swap)
- Graduation and blind policies are ready for the exit-seat and supervisor integration in 04-06/04-07
- R65 stays open: the layout is ASSUMED and RPC entries fail closed until a decoded probe plus human review flips the constant
- No blockers

## Self-Check: PASSED

- All 14 created/modified files exist on disk (15 paths incl. regenerated journal_note schema)
- All 3 task commits exist: 3957019, 26305df, aa08e68 (`git rev-list --count 97ddb2c..HEAD` = 3)
- Closing gate: pytest exit 0 (1099 passed, 2 skipped), ruff check exit 0, ruff format --check exit 0, mypy exit 0

---
*Phase: 04-paper-trading-and-autonomy*
*Completed: 2026-10-21*
