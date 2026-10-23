---
phase: 03-tools-and-skills
plan: "05"
subsystem: desk-gateway
tags: [TOOL-010, gateway, projection, seat-isolation, json-rpc, stdlib-http]
requires:
- phase: 03-tools-and-skills plan 04
  provides: [effective_roster/transport_map helpers, ten manifests, 37-tool registry shape]
provides:
- projection facade in src/pumpgrok/contracts/projection.py
- services/desk-gateway package with own pyproject plus lock
- per-seat compare_digest auth with 401/403/503 semantics
- tools/call dispatch with isError:true code envelopes
- root facade linkage tests for the -k gateway selector
affects: [03-06, 03-07]
tech-stack:
  added: [desk-gateway service project (stdlib http.server only, no web framework)]
  patterns: [owner-thread tool loop for sqlite affinity, forward-built transport dict, per-seat token env]
key-files:
  created: [src/pumpgrok/contracts/__init__.py, src/pumpgrok/contracts/projection.py, services/desk-gateway/pyproject.toml, services/desk-gateway/uv.lock, services/desk-gateway/README.md, services/desk-gateway/src/desk_gateway/__init__.py, services/desk-gateway/src/desk_gateway/config.py, services/desk-gateway/src/desk_gateway/server.py, services/desk-gateway/tests/conftest.py, services/desk-gateway/tests/test_auth.py, services/desk-gateway/tests/test_tools_list.py, services/desk-gateway/tests/test_transport_names.py, services/desk-gateway/tests/test_call_dispatch.py]
  modified: [tests/test_gateway_projection.py]
decisions:
- "Owner-thread tool loop: the registry is built and used in one thread because LedgerStore sqlite affinity forbids cross-thread use; request threads submit via run_coroutine_threadsafe"
- "Seat-map miss falls back to a registry-wide forward map so an existing-but-ungranted tool is refused permission_denied under the path manifest instead of unknown_tool"
- "503 message keeps the words but no token value; the test pins no configured value leaks"
- "check_secrets hits are pre-existing files from earlier plans; left untouched per scope boundary"
metrics:
  duration: 27min
  completed: 2026-10-21
  status: complete
actuals:
  tokens: 21000
  tasks: 3
  commits: 5
  plan_head_before: 3da0cf5
---

# Phase 3 Plan 05: Desk Gateway Summary

**Seat-isolated stdlib-HTTP projection over the in-process registry: per-seat compare_digest tokens (401/403/503), tools/list equals roster plus core with verbatim schemas, tools/call binds the path manifest with isError:true code envelopes, 21 gateway tests green in both runners and 683 root tests green.**

## Performance

- **Duration:** 27 min (first to last task commit, 13:20-13:47 UTC)
- **Started:** 2026-10-21T13:20:08Z
- **Completed:** 2026-10-21
- **Tasks:** 3
- **Files modified:** 14 (13 created, 1 extended)

## Accomplishments

- `src/pumpgrok/contracts/projection.py`: facade over manifests with a
  default contracts dir, `effective_roster(seat)`, `transport_map(seat)`,
  `short_to_seat`/`seat_to_short` from roster YAML, and `exposure_entries`
  (transport name plus verbatim description/inputSchema). The service
  imports it, never the reverse.
- `services/desk-gateway/`: own `pyproject.toml` (deps pumpgrok path
  editable, pydantic, pyyaml; dev pytest/pytest-asyncio) plus committed
  `uv.lock` (25 packages, stdlib HTTP only, no mcp/starlette/uvicorn).
- Auth: `Authorization: Bearer` compared with `hmac.compare_digest` in a
  loop over every seat; no match 401, other-seat match 403, unconfigured
  path seat 503 with no token value; only seat plus status logged.
- Methods: `initialize`, `notifications/initialized` (202, empty body),
  `tools/list`, `tools/call`, anything else -32601; non-POST 405,
  unknown seat 404, bad JSON 400/-32700.
- Dispatch: seat roster dict first, then a registry-wide forward map, so
  `exec.quote` on chief is `permission_denied` (bound manifest) while
  `desk.nope` is `unknown_tool`; `find` plus the tool run under a bound
  correlation id in the owner thread; `PumpgrokError` becomes
  `isError:true` with its code, validation failures `invalid_arguments`,
  unexpected failures `internal_error` with no stack or path.
- Owner-thread tool loop (`_start_owner_loop`/`close_server`): registry
  construction and every call run in one thread because `LedgerStore`
  sqlite connections are thread-bound; build failures raise instead of
  hanging on the ready event.
- Root linkage: `tests/test_gateway_projection.py` gains two facade tests
  (equality with the loader for all ten seats; short maps match roster
  shorts and `/mcp/<short>` endpoints), so `-k gateway` stays green
  without entering `services/`.

## Task Commits

Each task was committed atomically:

1. **Task 1: Tracer** - `763e543` (test, RED: no desk_gateway module);
   `178c551` (feat, GREEN: projection facade plus chief tools/list)
2. **Task 2: Gateway package** - `8e0b8ab` (test, RED: 11 failed,
   auth/dispatch missing); `80cf615` (feat, GREEN: auth, methods,
   dispatch, uv.lock)
3. **Task 3: Root linkage** - `dba886a` (test: facade equality for all
   ten seats plus endpoint checks)

_TDD tasks carry RED then GREEN commits per the tdd execution flow._

## Files Created/Modified

- `src/pumpgrok/contracts/__init__.py` (new, package marker)
- `src/pumpgrok/contracts/projection.py` (new, facade)
- `services/desk-gateway/pyproject.toml` (new)
- `services/desk-gateway/uv.lock` (new, committed per T-03-05-SC)
- `services/desk-gateway/README.md` (new, build metadata)
- `services/desk-gateway/src/desk_gateway/__init__.py` (new)
- `services/desk-gateway/src/desk_gateway/config.py` (new,
  `DESK_GATEWAY_TOKEN_<SHORT>` loading only)
- `services/desk-gateway/src/desk_gateway/server.py` (new, routing plus
  registry composition, no tool logic)
- `services/desk-gateway/tests/conftest.py` (new, live-HTTP fixtures
  with MockTransport safety net)
- `services/desk-gateway/tests/test_auth.py` (new, 6 tests)
- `services/desk-gateway/tests/test_tools_list.py` (new, 2 tests)
- `services/desk-gateway/tests/test_transport_names.py` (new, 4 tests)
- `services/desk-gateway/tests/test_call_dispatch.py` (new, 9 tests)
- `tests/test_gateway_projection.py` (extended, 2 facade tests)

## Decisions Made

- Owner-thread loop instead of per-request registries: one registry keeps
  single in-process semantics and avoids per-connection sqlite handles
  and diverging memory banks.
- Seat-map miss falls back to the global forward map before refusing, so
  the audit distinguishes typo (`unknown_tool`) from ungranted
  (`permission_denied` via `find` with `not_in_roster`).
- `desk.event_emit` stays bound to `bot-00-chief` (root harness parity);
  per-seat binding is out of scope until a gateway caller needs it.
- `send_webhook` keeps the base `str` url type; the bare `except` carries
  no noqa (contract forbids them) with the intent as a code comment.
- 503 body keeps the words "no token configured" but no value; the test
  asserts none of the configured values appear in the dumped body.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] sqlite thread affinity broke tools/call**
- **Found during:** Task 2 (GREEN run: brief dispatch returned
  `internal_error`)
- **Issue:** `LedgerStore` sqlite connections are bound to their creating
  thread; `ThreadingHTTPServer` workers are different threads, so every
  store-backed call raised `ProgrammingError`
- **Fix:** owner-thread tool loop builds and runs the registry in one
  thread; request threads dispatch through `run_coroutine_threadsafe`
  with an explicitly bound correlation id; build errors stored and
  re-raised instead of hanging `ready.wait`
- **Files modified:** services/desk-gateway/src/desk_gateway/server.py,
  tests/conftest.py, tests/test_auth.py (new `create_server` signature
  plus `close_server`)
- **Committed in:** 80cf615

**2. [Rule 2 - Missing critical] Un granted-but-existing tools need
permission_denied, not unknown_tool**
- **Found during:** Task 2 (GREEN run: chief exec_quote)
- **Issue:** Seat-scoped dict alone maps chief's `exec_quote` to
  `unknown_tool`; the elevation refusal must bind the path manifest
- **Fix:** Fall back to a registry-wide forward map, then `find` refuses
  with `permission_denied` (`not_in_roster`) under the path manifest
- **Files modified:** services/desk-gateway/src/desk_gateway/server.py
- **Committed in:** 80cf615

**3. [Rule 1 - Bug] rpc_call helper hid the 202 status**
- **Found during:** Task 2 (GREEN run: notification test)
- **Issue:** Helper hardcoded status 200 on success, so the 202 empty
  body assertion could never pass
- **Fix:** Return `response.status` on the success path
- **Files modified:** services/desk-gateway/tests/conftest.py
- **Committed in:** 80cf615

**4. [Rule 1 - Bug] 503 assertion rejected its own message wording**
- **Found during:** Task 2 (venv run)
- **Issue:** Test asserted the word "token" absent, but the compliant
  message "seat has no token configured" contains it; the rule is no
  token *value*
- **Fix:** Assert none of the configured token values appear in the
  dumped 503 body
- **Files modified:** services/desk-gateway/tests/test_auth.py
- **Committed in:** 80cf615

### Intentionally unchanged (pre-existing, out of scope)

- `check_secrets --base origin/main` exits 1 on 4 hits, all in files from
  earlier plans (`03-02-PLAN.md`, `market/liquidity.py`,
  `notify/telegram.py`, `safety/checks/authority.py`; last touched by
  commits `2c17945`, `2c681ab`, `d5111f1`). No 03-05 file is flagged.
  Left untouched per the scope boundary.

## Issues Encountered

- Two hashline edits landed on stale line numbers and were repaired by
  re-read plus targeted PUT; the file parsed cleanly after each repair.
- `transport_name` was missing from the server import list, which killed
  the owner thread and hung `ready.wait`; fixed by the import plus
  fail-fast error propagation (no more silent 120s wait).
- A gateway-run-only `NameError` (`WallClock` import missing in
  `test_auth.py`) slipped past root runs; both runners now verified at
  21 green, so the suite no longer depends on runner-specific leakage.
- `uv run pytest -q` prints a bare summary line in this harness; exact
  counts below come from `-v`/junit evidence, not the `-q` line.

## Verification evidence (all exit codes recorded)

- `cd services/desk-gateway && uv run pytest -q --junitxml` -> exit 0
  (junit: tests=21 failures=0 errors=0 skipped=0)
- `uv run pytest -q -k "least_privilege or gateway" --junitxml` ->
  exit 0 (junit: tests=21 failures=0 errors=0 skipped=0)
- `uv run pytest -q --junitxml` (full root suite) -> exit 0 (junit:
  tests=683 failures=0 errors=0 skipped=0)
- `uv run pytest -q tests/test_gateway_projection.py -k "tools_list or transport"` -> exit 0 (3 passed)
- `python3 ci/gates/check_secrets.py --base origin/main` -> exit 1
  (4 hits, all pre-existing files from earlier plans; zero in 03-05
  files; see deviation 5)
- `cd services/desk-gateway && uv lock` -> exit 0 (Resolved 25 packages)
- ROADMAP SC3 second half: gateway suite passes under its own
  `uv run pytest -q` (21/0) and root `-k gateway` collects (21/0)

## Known Stubs

None - no stubs, placeholders, or TODOs introduced. The `_ClosedNotifier`
refusing sink and the single-seat `event_emit` binding are explicit
fail-closed boundaries with comments naming their Phase 4 successors,
not stubs.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: resolved-enforcement | services/desk-gateway/src/desk_gateway/server.py | SQLite thread affinity forced dispatch into an owner thread; registry build and every call share one thread while HTTP workers only submit. No new trust boundary: tokens still env-only, compare_digest loop, seat binding via manifest. |
| threat_flag: pre-existing-secrets | src/pumpgrok/tools/market/liquidity.py etc. | check_secrets flags 4 values in earlier plans' files (see verification); none in 03-05 files. Left for the owning plans. |

No new trust boundaries: `projection.py` reads the already-contracted
roster YAML; the service adds no tool logic, no framework, and no
secret material (fixture tokens are `fake_token_*` placeholders).

## Auth Gates

None - no authentication was required.

## User Setup Required

None - gateway tokens are per-deploy environment (`DESK_GATEWAY_TOKEN_*`);
tests use placeholder literals only.

## Next Phase Readiness

- Plan 03-06 owns `tests/test_skill_manifests.py`; the SC1 joint
  selector stays red on the missing file until that plan lands
  (unchanged by this plan).
- Blocker for the orchestrator: (a) `check_secrets` is red branch-wide
  on 4 pre-existing hits outside 03-05; only the user (or the owning
  plans) can allowlist or rotate them.

---

*Phase: 03-tools-and-skills*
*Completed: 2026-10-21*

## Self-Check: PASSED

- All 14 created/modified files present on disk (checked individually).
- All 5 task commits present (`763e543`, `178c551`, `8e0b8ab`,
  `80cf615`, `dba886a`); `git rev-list --count 3da0cf5..HEAD` = 5.
- JUnit evidence on disk for all three green runners (21 + 21 + 683,
  zero failures/errors).
