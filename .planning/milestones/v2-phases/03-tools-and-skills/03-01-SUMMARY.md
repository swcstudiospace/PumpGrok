---
phase: 03-tools-and-skills
plan: "01"
subsystem: tool-contracts
tags: [pydantic-v2, typed-tools, registry, retry, idempotency, money-typing, decimal, httpx, tenacity]

# Dependency graph
requires:
  - phase: 02-restructure
    provides: [RpcClient, ported read functions, characterization pins]
provides:
  - build_registry() composition root with fail-closed limits checker
  - Registry prefix skip, READ-only retry gate, per-key rate limiting, R23 keys
  - Decimal-only money boundary in tools/core/cli plus UpstreamModel
  - RPC retry/decode/redaction discipline for TOOL-002
affects: [03-02, 03-03, 03-04, 03-05, 03-06, 03-07]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
# Same estimateTokens scale (chars/4 over the realized diff), never a harness token count.
actuals:
  tokens: 10738
  tasks: 4
  commits: 5
  plan_head_before: d5111f1af2e9df31e11157e93a500f19cea1be0c

# Tech tracking
tech-stack:
  added: []
  patterns: ["composition-root build_registry", "per-rate_limit_key lazy limiters", "R23 digest keys", "UpstreamModel extra-ignore parsing"]

key-files:
  created: [tests/tools/test_money_types.py, tests/tools/onchain/test_rpc.py]
  modified: [src/pumpgrok/core/registry.py, src/pumpgrok/core/tool.py, src/pumpgrok/core/idempotency.py, src/pumpgrok/tools/__init__.py, src/pumpgrok/cli.py, src/pumpgrok/tools/onchain/rpc.py, tests/core/test_registry.py]

key-decisions:
  - "Probe tool lives in the tracer test, not in build_registry/src (no scaffolding ships)"
  - "UpstreamModel placed in core/tool.py per the plan file list"
  - "Malformed RPC body fails over per endpoint, DataStale only when every endpoint is malformed"
  - "settings.py intentionally unchanged (no money-typed floats); engine/ floats stay per B1"

patterns-established:
  - "RetryPolicy drives both layers: registry retries timeouts, rpc.py retries 5xx/429, both read the same policy object"
  - "Money crosses the CLI boundary as Decimal once (--size-sol), everything downstream is int lamports/units"

requirements-completed: []

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Tracer: one READ probe resolves and runs end-to-end (registry, clock timeout, fail-closed checker, audit row)"
    requirement: "TOOL-008"
    verification:
      - kind: unit
        ref: "tests/tools/test_money_types.py#test_tracer_read_probe_resolves_and_runs + test_tracer_limits_checker_refuses_by_default + test_tracer_wrap_applies_clock_timeout"
        status: pass
    human_judgment: false
  - id: D2
    description: "Registry defects: prefix skip, READ-only retry, per-key rate limiting, R23 keys, duplicate registration refused"
    requirement: "TOOL-008"
    verification:
      - kind: unit
        ref: "tests/core/test_registry.py#test_prefix_find_skips_tools_above_requested_max + test_read_retry_policy_validates + test_write_retry_is_refused + test_exec_place_key_excludes_tool_and_bot + test_wrap_retries_read_timeouts_per_policy"
        status: pass
    human_judgment: false
  - id: D3
    description: "TOOL-008 boundary: Decimal-only money in tools/core/cli, UpstreamModel extra-ignore with typed error mapping, CLI half-up rounding"
    requirement: "TOOL-008"
    verification:
      - kind: unit
        ref: "tests/tools/test_money_types.py#test_canonical_json_rejects_float_leaves + test_upstream_model_ignores_extra_and_maps_errors + test_cli_size_sol_conversions"
        status: pass
    human_judgment: false
  - id: D4
    description: "RPC discipline: 4xx no-retry failover, timeout/5xx/429 retried per policy, malformed body typed, key header-only"
    requirement: "TOOL-008"
    verification:
      - kind: unit
        ref: "tests/tools/onchain/test_rpc.py (11 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "SC5 full-src literal (`src/pumpgrok/` grep) still matches 7 engine/ float lines; scope-change approval pending with the user"
    verification: []
    human_judgment: true
    rationale: "B1 binding keeps vendor-parity engine/ floats; only the user can approve re-scoping or rewriting the ROADMAP SC5 text"

# Metrics
duration: 10min
completed: 2026-10-21
status: complete
---

# Phase 3 Plan 01: Registry Contract and Money Typing Summary

**Fail-closed registry composition root with READ-only retry, R23 idempotency keys, Decimal-only money boundary in tools/core/cli, and typed RPC retry/failover — all pinned by 32 passing tests.**

## Performance

- **Duration:** 10 min (first to last task commit, 11:17–11:27 UTC)
- **Started:** 2026-10-21T11:17:43Z
- **Completed:** 2026-10-21T11:27:10Z
- **Tasks:** 4
- **Files modified:** 9 (6 src, 3 tests)

## Accomplishments

- `build_registry()` composition root: injected clock, list-backed audit sink, fail-closed limits checker (refuses), lazy per-`rate_limit_key` `RateLimiter` map
- Registry `find()` prefix skip on `exceeds_grant`/`exceeds_requested_max` (exact names still refuse; LIVE_WRITE still `LiveGateError` + audit)
- `ToolSpec` retry gate: `attempts > 1` READ-only; `_wrap` retries timeouts via `AsyncRetrying(sleep=clock.sleep)` with seeded jitter wait and per-call limiter acquire inside the clock timeout
- `exec_place_key`/`exec_cancel_key` R23 digests excluding tool/bot; `derive_idempotency_key` untouched
- CLI `--size-sol` parses to `Decimal`, `size_sol_to_lamports(Decimal)` with `ROUND_HALF_UP`; `UpstreamModel(extra=ignore)` + `parse_upstream` mapping to `DataStale`/`DataBlind`
- RPC discipline: retry only timeout/5xx/429 from the calling tool's `RetryPolicy`; 4xx fails over with no delay; malformed body fails over per endpoint and becomes `DataStale` when all endpoints are malformed; `x-api-key` header-only; ordered failover kept
- Scoped SC5 grep (`tools/ core/ cli.py`) prints nothing; `cli.py` float-money hits eliminated

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer: one typed READ tool resolves and runs end-to-end** - `6203a78` (feat)
2. **Task 2: Registry defects (RED)** - `a092d8b` (test); **(GREEN)** - `d03d1b1` (fix)
3. **Task 3: TOOL-008 money typing + upstream boundary** - `78cd973` (feat)
4. **Task 4: RPC discipline for TOOL-002** - `03719a9` (feat)

**Plan metadata:** `d5111f1` (docs: create phase plan)

_TDD tasks carry RED then GREEN commits per the tdd execution flow._

## Files Created/Modified

- `src/pumpgrok/tools/__init__.py` - `build_registry()` composition root (new content; file was a docstring)
- `src/pumpgrok/core/registry.py` - rng/limiter map, prefix skip, retry + rate limit in `_wrap`
- `src/pumpgrok/core/tool.py` - READ-only retry gate, `UpstreamModel`, `parse_upstream`, `RetryPolicy` seconds docstring
- `src/pumpgrok/core/idempotency.py` - `exec_place_key`, `exec_cancel_key`
- `src/pumpgrok/cli.py` - Decimal `--size-sol` boundary, NaN-safe validation
- `src/pumpgrok/tools/onchain/rpc.py` - policy-driven retry predicate, decode discipline, header-only key
- `tests/tools/test_money_types.py` - tracer (3) + money boundary (5) tests (new file)
- `tests/tools/onchain/test_rpc.py` - 11 RPC discipline tests (new file)
- `tests/core/test_registry.py` - retry split, prefix skip, R23 keys, duplicate pin, retry execution pins

## Decisions Made

- Probe tool lives in the tracer test, not in `build_registry`/src: registering a stub in shipped code would be scaffolding; acceptance criteria hold unchanged through the returned registry.
- `UpstreamModel` placed in `core/tool.py` per the plan's file list (next to `ToolInput`/`ToolOutput`) rather than `core/datasource.py`.
- Malformed RPC body fails over per endpoint and becomes `DataStale` only when every endpoint is malformed (satisfies both "typed failover" and "yields DataStale").
- `settings.py` intentionally unchanged: no money-typed floats exist there and the scoped SC5 grep passes without touching it.
- `exec.cancel` key digests `order_id` only, matching the catalog `d(order_id,cancel)` shape.
- Non-retriable transport errors (e.g. connection refused) fail over immediately per the locked "retry on timeout, 5xx, 429 only" rule.
- `requirements-completed` left empty: TOOL-008 spans later Phase 3 plans (all 37 tool models); this plan delivers only the boundary + contract. Do NOT mark TOOL-008 complete.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Plan referenced `src/pumpgrok/core/manifests.py`, which does not exist**
- **Found during:** Task 1 (tracer setup)
- **Issue:** `<read_first>` and `<files>` name `core/manifests.py`; no such module exists in the repo
- **Fix:** Used `core/bot.py` (`BotManifest`/`ToolGrant`) as the granting manifest; created no new module
- **Files modified:** tests only
- **Verification:** tracer resolves `find(probe, READ)` for a `BotManifest` grant
- **Committed in:** 6203a78 (part of task commit)

**2. [Rule 2 - Missing critical] `_size_sol` parser also converted to `Decimal`, not just `size_sol_to_lamports`**
- **Found during:** Task 3 (TOOL-008 boundary)
- **Issue:** Plan named only the `size_sol_to_lamports` param, but the argparse parser returned `float`; leaving it would keep float money flowing into the Decimal function
- **Fix:** `_size_sol(value: str) -> Decimal` with NaN/Infinity-safe validation; removed the now-unused `math` import
- **Files modified:** src/pumpgrok/cli.py
- **Verification:** `test_cli_size_sol_conversions` passes (exit 0)
- **Committed in:** 78cd973 (part of task commit)

**3. [Rule 3 - Blocking] Plan verify used `from src.pumpgrok.tools import ...`, which is not importable**
- **Found during:** Task 1 (tracer verify)
- **Issue:** `src/` is not on `sys.path`; the literal command fails with `ModuleNotFoundError`
- **Fix:** Ran the equivalent `from pumpgrok.tools import build_registry` (installed package path); exit 0, `registry ok`
- **Files modified:** none
- **Verification:** `/tmp/tracer_import.txt` exit 0
- **Committed in:** n/a (verify-only)

---

**Total deviations:** 3 auto-fixed (2 blocking, 1 missing-critical)
**Impact on plan:** All required for correctness; no scope creep. No architectural changes (Rule 4 never triggered).

## Issues Encountered

- `decimal.InvalidOperation` on NaN ordering: `Decimal("NaN") > 0` raises instead of returning False, so validation checks `is_finite()` first and wraps both steps in try/except. Pinned by the `"NaN"`/`"Infinity"` cases in `test_cli_size_sol_conversions`.
- Bash live output mis-renders pytest runs; all test evidence below comes from output redirected to files with recorded exit codes.
- One process slip: a mechanical 3-line test-handler substitution was applied via a shell heredoc instead of the edit tool; the result was verified by the passing suite. No code impact.

## Verification evidence (all exit codes recorded)

- `uv run pytest -q tests/core/test_registry.py tests/tools/test_money_types.py tests/tools/onchain/test_rpc.py` → exit 0 (32 tests)
- `uv run pytest -q tests/tools/test_money_types.py -k tracer` → exit 0 (3 tests, task 1 gate)
- `! grep -rnE "(lamports|units|sol)[A-Za-z_]*: *float" src/pumpgrok/tools/ src/pumpgrok/core/ src/pumpgrok/cli.py` → prints nothing (scoped SC5 half passes)
- Full-src SC5 literal → 7 remaining `engine/` hits (`models.py:49,50,85,264`, `reputation.py:56,147`, `tune.py:40`); `engine/` untouched by this plan (verified via diff stat); reported as unmet pending user scope approval per B1
- `uv run pytest -q` (full suite, incl. static guards and characterization) → exit 0
- `git status`: `src/pumpgrok/engine/` clean; only `.planning/` files outside this plan differ (pre-existing user changes, untouched)

## Known Stubs

None - no stubs, placeholders, or TODOs introduced. Test-only probes live in `tests/`, never in `src/`.

## Auth Gates

None - no authentication was required.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Later Phase 3 plans can register catalog tools through `build_registry()` and rely on: prefix resolution, READ retry, per-key limiting, R23 keys, Decimal boundary, upstream parsing, and the RPC policy contract.
- Blockers for the orchestrator: (a) SC5 full-src literal still matches 7 `engine/` lines — needs user scope approval (D5 above); (b) ROADMAP Phase 3 `Plans:` is still `TBD` with no per-plan rows, so no roadmap plan-progress update was possible for 03-01; (c) `settings.py` `tools.*` timeout/rate-limit config section is still open for a later plan (skeleton uses `_DEFAULT_PER_MINUTE = 60.0`).

---
*Phase: 03-tools-and-skills*
*Completed: 2026-10-21*

## Self-Check: PASSED

- All 9 created/modified files present on disk.
- All 5 task commits present (`6203a78`, `a092d8b`, `d03d1b1`, `78cd973`, `03719a9`).
- Plan-level pytest exit 0; scoped SC5 grep prints nothing; `engine/` untouched.
