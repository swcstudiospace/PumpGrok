---
phase: 02-restructure
plan: "02"
subsystem: engine-screening
tags: [characterization, struct-003, monitor, analyzer, scoring, reputation, exits, watcher]
requires: [02-01]
provides: [engine-models, engine-monitor, engine-analyzer, engine-scoring, engine-reputation, engine-exits, engine-watcher]
affects: [02-03-pipeline, 02-04-cli, phase-4-replay]
tech-stack:
  added: []
  patterns: ["injected Clock sleeps and timeouts", "explicit now threading", "PositionBook Protocol seam", "MockTransport fixtures"]
key-files:
  created:
    - src/pumpgrok/engine/__init__.py
    - src/pumpgrok/engine/models.py
    - src/pumpgrok/engine/monitor.py
    - src/pumpgrok/engine/analyzer.py
    - src/pumpgrok/engine/scoring.py
    - src/pumpgrok/engine/reputation.py
    - src/pumpgrok/engine/exits.py
    - src/pumpgrok/engine/watcher.py
    - tests/characterization/test_monitor.py
    - tests/characterization/test_analyzer.py
    - tests/characterization/test_scoring.py
    - tests/characterization/test_reputation.py
    - tests/characterization/test_exits.py
    - tests/characterization/test_watcher.py
    - tests/fixtures/http/pumpfun_holder.json
  modified:
    - ownership.yaml
    - tests/test_skip_cycle.py
decisions:
  - Tri-state unique_buyers (None means no evidence) fails closed with data_unavailable, terminal in _promote
  - Engine position named ExitPosition, distinct from core/adapter.py Position
  - Analyzer drops the pump.fun Bearer header (no settings field carries a key) and tracks per-source health
  - Veto and verdict strings are ASCII codes (creator_share_veto, top5_share_veto, creator_rugged)
  - Watcher depends on a PositionBook Protocol, never RiskManager; Phase 4 implements the real book
  - engine/reputation.py settles to bot-08-signal (explicit pin of the engine default)
metrics:
  duration: 1 working session
  completed: 2026-10-21
  tasks: 3
  commits: 3
status: complete
actuals:
  tokens: 52000
  tasks: 3
  commits: 3
  plan_head_before: c4045db
---

# Phase 02 Plan 02: Vendor Screening Engine Summary

Fail-closed pump.fun screening core (STRUCT-003 part 1): domain models, launch monitor, REST analyzer, scoring matrix, creator reputation, exit rules, and position watcher, pinned by 102 offline characterization tests plus one hand-authored holder fixture.

## Tasks Completed

| # | Task | Commit | Verify |
|---|------|--------|--------|
| 1 | Tracer: Token model plus fail-closed filter end-to-end | 487dbfc | 26 passed |
| 2 | Analyzer, scoring, and reputation ports | 47deefd | 52 passed (analyzer 19, scoring 13, reputation 20) |
| 3 | Exit rules and position watcher ports | 17fc83c | 24 passed (exits 14, watcher 10); manifest OK |

## Verification Evidence

- Full plan suite: `.venv/bin/python -m pytest tests/characterization/test_monitor.py test_analyzer.py test_scoring.py test_reputation.py test_exits.py test_watcher.py` -> exit 0, 102 passed, no NetworkBlocked.
- Regression: `tests/test_skip_cycle.py` -> exit 0, 8 passed.
- Manifest: `python3 ci/gates/check_ownership.py --validate-manifest` -> exit 0, 371 tracked paths owned (G-1 line in output is the gate's own label).
- Cyrillic spot check: `LC_ALL=C.UTF-8 grep -rlP '\p{Cyrillic}' src/pumpgrok/engine/ tests/characterization/test_{monitor,analyzer,scoring,reputation,exits,watcher}.py` prints nothing (exit 1).
- Static surface: no `import time`, `asyncio.sleep`, `asyncio.wait_for`, or ambient `random` in `src/pumpgrok/engine/` (docstring prose mentions only, which the AST guard ignores).
- Note: `uv run pytest` collects nothing in this environment (wrapper issue, pre-existing); the project venv binary (`.venv/bin/python -m pytest`) is the equivalent runner and was used for every suite above.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Frozen settings] Assignment to frozen FilterSettings/ExitsSettings in tests**
- Found during: tasks 1 and 3 test runs
- Issue: `cfg.require_metadata = False` and `exits.take_profit_pct = 0.0` raise on frozen models
- Fix: `model_copy(update={...})` in `test_metadata_ignored_when_not_required` and `test_zero_disables_each_rule`
- Files modified: tests/characterization/test_monitor.py, test_exits.py

**2. [Rule 1 - Stale TTL expectation] stale_no_traction unreachable without evidence**
- Found during: task 1 test run
- Issue: a no-evidence token hits terminal `data_unavailable` before the TTL sweep, so the stale test as ported could never see `stale_no_traction`
- Fix: the stale test observes `unique_buyers = 0` (buffered `few_buyers`), then the TTL sweep reports `stale_no_traction`
- Files modified: tests/characterization/test_monitor.py

**3. [Rule 1 - FixtureClock hang] Stream reconnect test hung on virtual sleep**
- Found during: task 1 test run (180s timeout, 2 failures plus hang)
- Issue: the reconnect path sleeps `clock.sleep(backoff)`; `FixtureClock` never advances on its own, so the test hung forever
- Fix: stream tests use a `ManualClock` (fixed `now`, real sleeps/timeouts); reconnect test allows 1.5s for the 1.0s backoff
- Files modified: tests/characterization/test_monitor.py

**4. [Rule 1 - Vendor test shape] Trailing-peak test needs explicit peak write**
- Found during: task 3 test run
- Issue: `exit_signal` is pure and never writes `peak_price`; the first draft called it with price 1.4 expecting a trailing stop
- Fix: ported the vendor shape exactly (probe 2.19, assert function did not write, set peak, then expect trailing stop); trailing-fire test now asserts the 1.4-None/1.29-fire pair
- Files modified: tests/characterization/test_exits.py

**5. [Rule 2 - Stale doctor expectation] engine flips to ok**
- Found during: task 3 regression run
- Issue: `test_doctor_reports_absent_subsystems_as_warnings` still listed `engine` as absent, but the plan-mandated `engine/__init__.py` makes doctor report `ok engine` (anticipated by 02-PATTERNS.md row 50, same as plan 01's tools flip)
- Fix: assert `ok engine (pumpgrok.engine)` present; absent list is now `gateway, supervisor, reports`
- Files modified: tests/test_skip_cycle.py
- Commit: 17fc83c

## Key Decisions

- `unique_buyers: int | None = None` is the minimum representation that makes fail-closed testable (Gap G1); `data_unavailable` is terminal in `_promote` because no trade stream can ever supply the missing evidence (Gap G2).
- `Token.age_seconds(now)`, `parse_create_event(payload, now)`, `handle_event(payload, now)`, `sweep(now)`, `exit_signal(..., now)`, and `forget_older_than(days, now)` all take `now` explicitly; `now or time.time()` defaults are banned (Pits 10, 13).
- The engine position is `ExitPosition`, recorded in `models.py` as deliberately distinct from `core/adapter.py` `Position` (Gap G4).
- `Analyzer.health` maps endpoint path to last-fetch ok; `source_health()` defaults True for untouched sources. No entry decision may rest solely on pump.fun REST (R47).
- `ReputationBook` keeps the vendor JSON shape (`version`/`creators`/`updated_at`) via `core/atomic_write_json`; `OSError` propagates loudly instead of being logged and swallowed.
- `PositionWatcher` owns `PEAK_PERSIST_STEP = 1.01` and `BLIND_AFTER = 3` from the vendor; the sale persists state itself, so `persist_needed` resets on every close.

## Known Stubs

None. No placeholders, mocks, or unwired paths were introduced. The `FakeBook`/`ManualClock`/`FakeWebSocket` doubles live in tests only.

## Threat Flags

None beyond the plan threat model (T-02-04/05/06, T-02-SC): `connect(url, proxy=None, max_queue=data.ws_max_queue)` is the only socket path and only `subscribeNewToken` is ever sent; untrusted pump.fun payloads are parsed as data through typed models; reputation persists creator records only via `atomic_write_json` to the settings path; no new packages were added.

## Self-Check: PASSED

- All created files exist on disk; all modified files committed.
- Commits 487dbfc, 47deefd, 17fc83c present in `git log`.
