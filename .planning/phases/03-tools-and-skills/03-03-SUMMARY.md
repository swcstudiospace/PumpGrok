---
phase: 03-tools-and-skills
plan: "03"
subsystem: write-tools
tags: [paper-write, idempotency, allowlist, kill-switch, journal, desk, notify, httpx-mocktransport]

# Dependency graph
requires:
  - phase: 02-restructure
    provides: [LedgerStore hash chain, BotManifest grants, RpcClient]
  - phase: 03-tools-and-skills plan 01
    provides: [build_registry composition root, R23 keys, retry/rate-limit wiring]
  - phase: 03-tools-and-skills plan 02
    provides: [READ tool patterns, MockTransport fixtures, safety settings]
provides:
  - NotYetImplementedAdapter refusing backend (B5 envelope, B7 input-contract scope)
  - exec/portfolio/risk/journal/notify/desk ToolSpecs with catalog timeouts/keys
  - Allowlisted Notifier with j8 sink retry; desk doctor sharing the CLI path
affects: [03-04, 03-05, 03-06, 03-07]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
# Same estimateTokens scale (chars/4 over the realized diff), never a harness token count.
actuals:
  tokens: 42087
  tasks: 3
  commits: 4
  plan_head_before: 5fa5dc97c8668a47b25f90f29f97db793a5bce8f

# Tech tracking
tech-stack:
  added: []
  patterns: ["bind-backend-at-build tool factories", "fail-closed input validation before adapter", "minute-derived idempotency keys", "subprocess gate rows as data"]

key-files:
  created: [src/pumpgrok/execution/not_yet_implemented.py, src/pumpgrok/tools/exec/place.py, src/pumpgrok/tools/exec/quote.py, src/pumpgrok/tools/exec/simulate.py, src/pumpgrok/tools/exec/cancel.py, src/pumpgrok/tools/exec/positions.py, src/pumpgrok/tools/portfolio/ledger_read.py, src/pumpgrok/tools/portfolio/ledger_write.py, src/pumpgrok/tools/portfolio/exposure.py, src/pumpgrok/tools/portfolio/pnl.py, src/pumpgrok/tools/risk/check_limits.py, src/pumpgrok/tools/risk/drawdown.py, src/pumpgrok/tools/risk/kill_switch.py, src/pumpgrok/tools/risk/halt_status.py, src/pumpgrok/tools/journal/append.py, src/pumpgrok/tools/journal/render_report.py, src/pumpgrok/tools/notify/allowlist.py, src/pumpgrok/tools/notify/notifier.py, src/pumpgrok/tools/notify/telegram.py, src/pumpgrok/tools/notify/webhook.py, src/pumpgrok/tools/notify/alert.py, src/pumpgrok/tools/desk/brief.py, src/pumpgrok/tools/desk/docs_search.py, src/pumpgrok/tools/desk/memory_retain.py, src/pumpgrok/tools/desk/memory_recall.py, src/pumpgrok/tools/desk/ownership_resolve.py, src/pumpgrok/tools/desk/receipt_check.py, src/pumpgrok/tools/desk/event_emit.py, src/pumpgrok/tools/desk/doctor.py, src/pumpgrok/tools/desk/_memory.py, src/pumpgrok/tools/desk/_tokens.py, tests/tools/exec/test_place.py, tests/tools/exec/test_exec_family.py, tests/tools/portfolio/test_portfolio.py, tests/tools/risk/test_risk.py, tests/tools/journal/test_journal.py, tests/tools/notify/test_notify.py, tests/tools/desk/test_desk.py]
  modified: [src/pumpgrok/core/errors.py, src/pumpgrok/ledger/store.py, src/pumpgrok/config/settings.py, src/pumpgrok/config/overlays/paper.toml, src/pumpgrok/config/overlays/dev.toml, src/pumpgrok/config/overlays/live.toml, contracts/README.md]

key-decisions:
  - "Simulate/cancel raise not_yet_implemented directly: no OrderRequest is constructible from the catalog simulate input and no order book exists for cancel (B7 scope)"
  - "check_limits is advisory with R34 vocabulary: structural checks evaluate, engine rules skip, approved reflects hard fails only"
  - "event_emit dedup rides on the journal key with the seat in the body; event_emit_key pins the (tool,bot,sha) shape in tests"
  - "doctor install_prompt/repair fail closed (Phase 4 gateway) instead of returning a faked prompt"
  - "retry stays registry-none for paper-write tools; j8 applies per network sink inside the Notifier"

patterns-established:
  - "run_<name>(input, backend...) returns a model-validated dict; build_<name>_tool(backend...) binds it behind @tool(SPEC)"
  - "Coroutines for retry are passed as factories; a coroutine object cannot be re-awaited"
  - "Virtual-clock sleeps hang without a replay runner: retry-path tests use WallClock"

requirements-completed: []

# Coverage metadata (#1602)
coverage:
  - id: D1
    description: "Tracer: exec.place input contract rejects without approval; exit+BUY refused seat_may_trade; valid shape surfaces not_yet_implemented (B7 Phase 3)"
    requirement: "TOOL-004"
    verification:
      - kind: unit
        ref: "tests/tools/exec/test_place.py (9 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Exec family + portfolio/risk/journal specs per CONTEXT table; kill_switch set/flatten only; seats write journal_note/escalation; ledger_write denied to all ten seats; simulate ledger-clean"
    requirement: "TOOL-005"
    verification:
      - kind: unit
        ref: "tests/tools/exec/test_exec_family.py + tests/tools/portfolio/test_portfolio.py + tests/tools/risk/test_risk.py + tests/tools/journal/test_journal.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "notify.alert via abstract Notifier: allowlist-only network, stdout+file always, 12 escalation kinds, j8 sink retry, minute-derived keys (MockTransport only)"
    requirement: "TOOL-006"
    verification:
      - kind: unit
        ref: "tests/tools/notify/test_notify.py (7 tests)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Desk core eight resolvable with catalog timeouts/keys; doctor check shares the pumpgrok doctor code path (check); prompt assembly fails closed (Phase 4 gateway)"
    requirement: "TOOL-007"
    verification:
      - kind: unit
        ref: "tests/tools/desk/test_desk.py (11 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "B7 accepted partial: input contract delivered; atomic consume-and-order transaction and repeat-returns-first-fill are Phase 4"
    verification: []
    human_judgment: true
    rationale: "Only the user/orchestrator can accept the deferred scope; code states the partial at every boundary"

# Metrics
duration: 55min
completed: 2026-10-21
status: complete
---

# Phase 3 Plan 03: Write-Side and Core Tools Summary

**Fail-closed write tools over a refusing adapter: exec input contracts (B7 scope), ledger-backed portfolio/risk/journal, allowlisted notify, and the desk core eight — 63 plan tests green, full suite (641) green.**

## Performance

- **Duration:** 55 min (first to last task commit, 12:03–12:58 UTC)
- **Started:** 2026-10-21T12:03:53Z
- **Completed:** 2026-10-21
- **Tasks:** 3
- **Files modified:** 44 (37 src, 7 tests)

## Accomplishments

- Tracer: `exec.place` validates ticket/decision/size/approval fail-closed, refuses exit+BUY with `seat_may_trade` before touching the adapter, and surfaces `not_yet_implemented` (never a fake Fill) on valid shapes; key derived from `(ticket_id,side,decision_id)` only
- Exec family: quote/positions delegate to the adapter; simulate/cancel validate then refuse (no OrderRequest constructible, no order book); cancel keys on `order_id`
- Portfolio: `ledger_read` filtered reads + snapshots; `ledger_write` required-key append with duplicate replay; exposure/pnl fold real events (zeros on empty ledger)
- Risk: `check_limits` reports all 19 R34 ids (structural evaluate, engine skip); drawdown from snapshots; kill_switch set/flatten only with minute keys; halt_status folds env/file/ledger causes
- Journal: append restricted to seat kinds with note_kind rules + JSONL export; render_report writes markdown via tmp+replace
- Notify: `[notify]` config section + overlays (empty = stdout+file); allowlist-only Telegram/webhook; token env-only with sanitized errors; j8 per-sink retry with factories
- Desk eight: brief (real halt+recall, empty tickets), docs_search (real substring search), memory retain/recall (refused without provenance), ownership (last-match-wins), receipt_check (G-2/G-3/G-5/G-6 rows), event_emit (scrub+4KB cap), doctor (check shares CLI path; prompt assembly fails closed)
- Stale `contracts/README.md` write-needs-g6 claim fixed (scoped edit): g6 is approval-gated tools only; kill_switch carries no gate tag

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer: exec.place input contract rejects without approval** - `2f770e1` (feat)
2. **Task 2: Exec family + portfolio/risk/journal (TOOL-004 remainder, TOOL-005)** - `13252fc` (test, RED) + `363a339` (feat, GREEN)
3. **Task 3: Notify + desk core eight (TOOL-006, TOOL-007)** - `2c17945` (feat)

**Plan metadata:** `5fa5dc9` style-fix baseline (predates this plan; no docs commit for the plan file)

## Files Created/Modified

- `src/pumpgrok/core/errors.py` - `NotYetImplemented` (code `not_yet_implemented`) for B5/B7
- `src/pumpgrok/execution/not_yet_implemented.py` - refusing adapter (all five methods raise)
- `src/pumpgrok/tools/exec/` - `place.py`, `quote.py`, `simulate.py`, `cancel.py`, `positions.py`
- `src/pumpgrok/tools/portfolio/` - `ledger_read.py`, `ledger_write.py`, `exposure.py`, `pnl.py`
- `src/pumpgrok/tools/risk/` - `check_limits.py`, `drawdown.py`, `kill_switch.py`, `halt_status.py`
- `src/pumpgrok/tools/journal/` - `append.py`, `render_report.py`
- `src/pumpgrok/tools/notify/` - `allowlist.py`, `notifier.py` (+`HttpxNotifier`), `telegram.py`, `webhook.py`, `alert.py`
- `src/pumpgrok/tools/desk/` - `brief.py`, `docs_search.py`, `memory_retain.py`, `memory_recall.py`, `ownership_resolve.py`, `receipt_check.py`, `event_emit.py`, `doctor.py`, `_memory.py`, `_tokens.py`
- `src/pumpgrok/ledger/store.py` - `read`, `by_key`, `read_snapshots`, `latest_snapshot` (read-only)
- `src/pumpgrok/config/settings.py` + 3 overlays - `[notify]` allowlist section
- `contracts/README.md` - g6 scoped to approval-gated writes (R22 kill_switch note)
- `tests/tools/{exec,portfolio,risk,journal,notify,desk}/` - 63 plan tests

## Decisions Made

- Simulate/cancel raise directly: the catalog simulate input has no `decision_id` (no `OrderRequest` without fabricating one) and cancel's `decision_id` lives in the Phase 4 order book; both name the missing backend
- `check_limits.approved` reflects structural hard fails only; enforcement stays in-adapter (Phase 4), so the advisory read never authorises anything
- `event_emit` delegates dedup to the journal key with the bound seat in the body; `event_emit_key` pins the `(tool,bot,sha)` shape in tests
- Doctor `install_prompt`/`repair` fail closed with a Phase-4-gateway row instead of assembling a fake prompt
- Registry-level retry stays `none` for paper-write tools; j8 lives inside the Notifier per network sink (timeout/5xx/429 only, D5)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] LedgerStore had no read path for the read tools**
- **Found during:** Task 2 (GREEN)
- **Issue:** `portfolio.ledger_read`/exposure/pnl/drawdown need filtered reads and snapshots; the store only appended
- **Fix:** Added read-only `read` (seq/types/source/ticket filters), `by_key` (repeat lookup), `read_snapshots`, `latest_snapshot`; no chain or schema change
- **Files modified:** src/pumpgrok/ledger/store.py
- **Committed in:** 363a339

**2. [Rule 3 - Blocking] No `not_yet_implemented` error code existed**
- **Found during:** Task 1 (tracer)
- **Issue:** Plan requires every adapter method to raise `PumpgrokError` code `not_yet_implemented`; no such class existed
- **Fix:** Added `NotYetImplemented` to `core/errors.py` (B5 envelope code)
- **Files modified:** src/pumpgrok/core/errors.py
- **Committed in:** 2f770e1

**3. [Rule 1 - Bug] Retry helper awaited a coroutine object per attempt**
- **Found during:** Task 3 verification (webhook retry test: `cannot reuse already awaited coroutine`)
- **Issue:** `_with_j8` took a coroutine; tenacity re-awaits it per attempt
- **Fix:** Factories (`lambda: ...`) created fresh per attempt; wired `wait_random_exponential` so j8 actually backs off
- **Files modified:** src/pumpgrok/tools/notify/notifier.py
- **Committed in:** 2c17945

**4. [Rule 1 - Bug] Retry-path tests hung on FixtureClock.sleep**
- **Found during:** Task 3 verification (suite timed out at the webhook retry test)
- **Issue:** Virtual-clock sleep waits for `advance_to`, which no unit test drives
- **Fix:** Retry-path test uses `WallClock` (bounded real backoff); no-retry tests keep `FixtureClock`
- **Files modified:** tests/tools/notify/test_notify.py
- **Committed in:** 2c17945

**5. [Rule 2 - Missing critical] 4 KB cap replaced the whole escalation payload**
- **Found during:** Task 3 verification (Escalation schema validation failed on capped output)
- **Issue:** Whole-dict `{"truncated": ...}` replacement breaks the closed event schema
- **Fix:** `scrub_payload` shortens long string values in place; the key set never changes
- **Files modified:** src/pumpgrok/tools/desk/event_emit.py
- **Committed in:** 2c17945

---

**Total deviations:** 5 auto-fixed (3 blocking, 2 bug, 1 missing-critical counting the store read path)
**Impact on plan:** All required for correctness; no scope creep. No architectural changes (Rule 4 never triggered).

## Issues Encountered

- Edit-tool range drift on fresh files: several hashline patches landed off-target and were repaired by re-read plus rewrite; final files parse and the suite is green
- Bash live output mis-renders pytest runs (known runner quirk, also noted in 03-01/03-02): every verify below comes from output redirected to files with recorded exit codes
- `uv run pytest ... | tail` reports "No tests collected" under pipe; file redirect works (same quirk)

## Verification evidence (all exit codes recorded)

- `uv run pytest -q tests/tools/exec/test_place.py` → exit 0 (9 tests, task 1 gate)
- `uv run pytest -q tests/tools/exec tests/tools/portfolio tests/tools/risk tests/tools/journal` → exit 0 (36 tests, task 2 gate)
- `uv run pytest -q tests/tools/notify tests/tools/desk` → exit 0 (18 tests, task 3 gate)
- Full `uv run pytest -q` → exit 0 (641 tests, no regressions)
- `git status`: only `.planning/` files outside this plan differ (pre-existing user changes, untouched)

## Known Stubs

None introduced. Accepted partials (bindings, not stubs — each is documented at the code boundary and below):

- B7: atomic consume-and-order ledger transaction + repeat-returns-first-fill are Phase 4; tools state this in module docstrings
- Supervisor relay of `Escalation` to `notify.alert` is Phase 4 (`render_report.deliver` records `queued` on disk only)
- `desk.brief.tickets` is empty (no ticket store in Phase 3); halt and recall are real
- Doctor `install_prompt`/`repair` fail closed pending Phase 4 seat-bound prompt assembly
- Breaker state in `halt_status` is `False` until the Phase 4 RiskEngine owns it; marks/unrealised are zero until the mark engine lands

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: network-sink | src/pumpgrok/tools/notify/telegram.py, webhook.py | New outbound HTTP (Telegram Bot API, webhooks); allowlist-only, token env-only with sanitized errors, no secrets in logs |
| threat_flag: hmac-key | src/pumpgrok/tools/desk/doctor.py | Doctor bindings are HMAC-bound with an injected key; the gateway (Phase 4) must supply a per-seat key — no key material in repo |

## Auth Gates

None - no authentication was required.

## User Setup Required

- `PUMPGROK_TELEGRAM_TOKEN` env var for the Telegram sink; without it Telegram sends refuse with `telegram token is unset` (stdout+file still deliver)
- Notify allowlist in `PUMPGROK_CONFIG` operator TOML or `[notify]` overlay; empty means stdout+file only

## Next Phase Readiness

- Later plans compose these tools via `build_registry()`: every module exposes `build_<name>_tool(deps)` with no globals; `HttpxNotifier` is the concrete sink composer
- Registry-level approval enforcement is still fail-closed (`_refuse_all` until RiskEngine lands in Phase 4)
- Blockers for the orchestrator: (a) B7 same-transaction/flush deferred to Phase 4 (D5 user-accepted partial); (b) ROADMAP Phase 3 `Plans:` is still `TBD`, so no roadmap plan-progress update was possible (same as 03-01/03-02); (c) doctor binding HMAC key management belongs to the Phase 4 gateway

---

*Phase: 03-tools-and-skills*
*Completed: 2026-10-21*

## Self-Check: PASSED

- All 44 created/modified files present on disk.
- All 4 task commits present (`2f770e1`, `13252fc`, `363a339`, `2c17945`).
- Plan-level pytest exit 0 for all three gates (9 + 36 + 18); full suite exit 0 (641).
