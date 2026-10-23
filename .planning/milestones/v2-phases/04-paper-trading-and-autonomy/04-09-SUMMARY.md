---
phase: 04-paper-trading-and-autonomy
plan: 09
subsystem: reporting
tags: [paper-trading, ascii-reports, live-refusal, hmac-confirm, paper-only-metrics, vendor-retirement]
requires:
  - phase: 04-01
    provides: Position/equity ledger views and reducer folds the daily and weekly builders consume
  - phase: 04-07
    provides: CLI verb surface and registry grants the live verbs refuse through
provides:
  - Daily and weekly ASCII paper reports rendered from str.format templates (paper-engine.md 8.3)
  - Exit-3 live refusal with nine R21 stderr lines and zero sends
  - HMAC-SHA256 live-confirm record bound to the config hash
  - Paper-only gate metrics that refuse replay-contaminated ledgers
  - Vendor-free tree with the license preserved at src/pumpgrok/engine/LICENSE-grokbot-pumpfun
affects: []
actuals:
  tokens: 22000
  tasks: 3
  commits: 4
tech-stack:
  added: []
  patterns: [str-format-template-constants, read-only-sqlite-uri, wallclock-only-cli-time]
key-files:
  created:
    - src/pumpgrok/reporting/__init__.py
    - src/pumpgrok/reporting/daily.py
    - src/pumpgrok/reporting/weekly.py
    - src/pumpgrok/reporting/render.py
    - src/pumpgrok/engine/LICENSE-grokbot-pumpfun
    - tests/reporting/test_reporting_render.py
    - tests/execution/test_live_gate_fails_fast.py
  modified:
    - src/pumpgrok/cli.py
    - src/pumpgrok/execution/live/live_gate.py
    - src/pumpgrok/execution/live/live_adapter.py
    - skills/grokbot-pipeline/SKILL.md
key-decisions:
  - "Reports keep str.format via module-level template constants (R9): inline literals trip the repo UP030/UP032 gate, so every format string is a named constant; operator messages in cli.py and live_gate.py use f-strings, the prevailing file idiom"
  - "WallClock is the only new wall-time source: _utc_now in cli.py and _paper_days in live_gate.py read WallClock().now(), keeping the static wall-clock guard green"
  - "The 59 ruff UP findings were plan-introduced, not pre-existing: a HEAD~3 worktree check under the identical config reports zero errors, refuting the 102-error pre-existing claim"
requirements-completed: [PAPER-006, SEC-004, GOLIVE-001, GOLIVE-002, STRUCT-006]
coverage:
  - id: C1
    description: "Daily report renders summary plus trades sections from a fixture ledger, ASCII only"
    requirement: "PAPER-006"
    verification:
      - kind: unit
        ref: "tests/reporting/test_reporting_render.py"
        status: pass
      - kind: cli
        ref: "uv run pumpgrok report --daily (exit 0); non-ASCII grep count 0"
        status: pass
    human_judgment: false
  - id: C2
    description: "Weekly report renders per-day table plus live-gate section, ASCII only"
    requirement: "PAPER-006"
    verification:
      - kind: cli
        ref: "uv run pumpgrok report --weekly (exit 0); non-ASCII grep count 0"
        status: pass
    human_judgment: false
  - id: C3
    description: "Live start with any unmet precondition exits 3 with nine R21 stderr lines and sends nothing; confirm writes the HMAC record without changing mode; metrics stay paper-only"
    requirement: "SEC-004"
    verification:
      - kind: unit
        ref: "tests/execution/test_live_gate_fails_fast.py"
        status: pass
      - kind: cli
        ref: "uv run pumpgrok run --mode live --once (exit 3, stdout 0 bytes)"
        status: pass
    human_judgment: false
  - id: C4
    description: "Vendor tree deleted with license preserved and scoped census empty"
    requirement: "STRUCT-006"
    verification:
      - kind: cli
        ref: "test ! -e vendor/grokbot-pumpfun (exit 0); test -f license (exit 0); rg census prints nothing (exit 1)"
        status: pass
    human_judgment: false
duration: 2026-10-22 single session
completed: 2026-10-22
status: complete
---

# Phase 04 Plan 09: Reports, Live Refusal, and Vendor Retirement Summary

**Daily and weekly ASCII reports from str.format templates, exit-3 live refusal with HMAC-bound confirm record and paper-only metrics, and a vendor-free tree. Suite, lint, format, and types green; ROADMAP criteria 4 and 5 verified command by command.**

## Performance

- **Completed:** 2026-10-22
- **Tasks:** 3 of 3 (tracer daily report; weekly plus live refusal plus confirm plus paper-only metrics; STRUCT-006 vendor retirement)
- **Files:** 7 created, 4 modified (plus license copy; vendor tree deleted)
- **Commits:** 4 implementation commits (`bd663a8`, `fdf40e8`, `ea06b2b`, `c92b294`)

## Accomplishments

- Task 1 tracer: `daily.py` folds the fixture ledger through the 04-01 views without creating `var/` files (guarded path plus read-only sqlite URI, never the `LedgerStore` constructor); `render.py` emits the summary plus trades sections from named `str.format` templates with an ASCII-only assertion; snapshot tests pin both sections.
- Task 2 live: `run --mode live` with any unmet R21 precondition exits 3, prints one `[x]`/`[ ]` line per id on stderr in R21 order, and sends nothing; `LiveAdapter.place`/`cancel` raise `LiveGateError` after `LiveWriteAttempted` plus a critical alert; `live confirm` writes the HMAC-SHA256 record bound to the config hash and appends `ApprovalRecorded(kind=live_gate)` without changing mode; gate metrics count `source=paper` rows only and refuse replay-contaminated ledgers. No signing code outside `execution/live/`.
- Task 3 retirement: the six `MIGRATION_MAP` 3.4 checks ran first, the vendor LICENSE was copied to `src/pumpgrok/engine/LICENSE-grokbot-pumpfun`, in-scope references under the nine census paths were rewritten, then `vendor/grokbot-pumpfun/` was deleted last. Characterization stays green post-deletion.

## Task Commits

1. **Task 1: tracer daily report from fixture ledger with ASCII snapshot** - `bd663a8` (feat)
2. **Task 2: weekly report, live refusal, confirm record, paper-only metrics** - `fdf40e8` (feat)
3. **Task 3: STRUCT-006 vendor retirement with license preserved** - `ea06b2b` (feat)
4. **Fix: static guard and mypy strict for live gate and CLI clock** - `c92b294` (fix)

## Verify runs (exit codes)

- `uv run pytest -q` exit 0 (1184 passed, 2 skipped; result chars counted from dot output)
- `.venv/bin/python -m pytest -p no:cacheprovider -q` exit 0 (same 1184 passed, 2 skipped)
- `.venv/bin/python -m pytest -p no:cacheprovider tests/reporting tests/execution tests/safety` exit 0 (100 passed)
- `uv run ruff check .` exit 0 (all checks passed)
- `uv run ruff format --check .` exit 0 (459 files already formatted)
- `uv run mypy src/` exit 0 (no issues found); bare `uv run mypy` exit 0
- `uv run pumpgrok run --mode live --once` exit 3, stdout 0 bytes (nothing sent), stderr 11 lines: header plus nine R21 lines plus fix line
- `uv run pumpgrok report --daily` exit 0; `uv run pumpgrok report --weekly` exit 0
- `uv run pumpgrok report --daily | LC_ALL=C grep -c -P '[^\x00-\x7F]'` prints `0`; same for `--weekly`
- `test ! -e vendor/grokbot-pumpfun` exit 0; `test -f src/pumpgrok/engine/LICENSE-grokbot-pumpfun` exit 0
- `rg -l -F vendor/grokbot-pumpfun src skills agents rules hermes scripts ci contracts prompts` prints nothing (rg exit 1, no matches)

## Ruff pre-existing analysis (assignment step 3)

- The prior report of 102 pre-existing UP030/UP032 errors is refuted. Method: `git worktree add --detach /tmp/pg-base HEAD~3` (stash-free), then the repo venv ruff over `src tests ci` of that tree under the identical `pyproject.toml` select list: **all checks passed, 0 errors**. Worktree removed afterwards.
- The current tree had 59 errors (31 UP030 plus 28 UP032) in exactly the 5 files this plan touches: `daily.py` 16, `cli.py` 14, `live_gate.py` 12, `render.py` 10, `weekly.py` 7. All came from the plan's inline `"{0}".format(...)` literals.
- Fix, no `noqa` and no per-file ignores: reporting files hoist every format string to a named module-level `str.format` template constant (the existing `_REPORT_TEMPLATE` pattern, R9 intact); `cli.py` and `live_gate.py` operator messages become f-strings (the prevailing idiom, e.g. pre-existing `cli.py` usage errors). Rendered output is byte-identical, so snapshots hold. Follow-on E501/SIM108 findings from the longer named lines were wrapped, and one ternary applied.
- Final `uv run ruff check .` exit 0.

## Files Created/Modified

- `src/pumpgrok/reporting/__init__.py` - package exports
- `src/pumpgrok/reporting/render.py` - ASCII renderer, named `str.format` templates, `sol()`, `assert_ascii`
- `src/pumpgrok/reporting/daily.py` - read-only ledger fold, `DailyReport.build`, window helpers
- `src/pumpgrok/reporting/weekly.py` - ISO-week fold, per-day table, weekly live-gate section
- `src/pumpgrok/execution/live/live_gate.py` - nine preconditions in R21 order, WallClock paper-days, paper-only metrics
- `src/pumpgrok/execution/live/live_adapter.py` - refusing stub (`LiveGateError` after `LiveWriteAttempted`)
- `src/pumpgrok/cli.py` - `report --daily/--weekly`, `live` refusal path, `live confirm` HMAC record, `_utc_now`
- `src/pumpgrok/engine/LICENSE-grokbot-pumpfun` - verbatim preserved vendor license
- `skills/grokbot-pipeline/SKILL.md` - reference rewrite away from `cd vendor/grokbot-pumpfun`
- `tests/reporting/test_reporting_render.py` - ASCII snapshot tests
- `tests/execution/test_live_gate_fails_fast.py` - refusal-path tests
- `vendor/grokbot-pumpfun/` - deleted after the six retirement checks

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] `datetime.now` in new code tripped the static wall-clock guard**
- **Found during:** Fix pass (assignment step 1; `tests/safety/test_static_guards.py` forbids `datetime.now` outside `replay/clock.py`)
- **Issue:** `live_gate._paper_days` used `datetime.now(UTC)`; `cli.py` had three more call sites.
- **Fix:** `_paper_days` reads `datetime.fromtimestamp(WallClock().now(), UTC)` via `from pumpgrok.replay.clock import WallClock` (no cycle: `clock.py` imports stdlib only); `cli.py` gained `_utc_now()` on the same source and all three sites use it.
- **Files modified:** `src/pumpgrok/execution/live/live_gate.py`, `src/pumpgrok/cli.py`
- **Commit:** `c92b294`

**2. [Rule 3 - Blocking] mypy strict rejected untyped `dict` payloads**
- **Found during:** Fix pass (assignment step 2)
- **Issue:** `_fold_perf_row(payload: dict)` and the confirm `record = dict(body)` failed strict annotation checks.
- **Fix:** `payload: dict[str, Any]` (plus `from typing import Any`) and `record: dict[str, Any]`.
- **Files modified:** `src/pumpgrok/execution/live/live_gate.py`, `src/pumpgrok/cli.py`
- **Commit:** `c92b294`

**3. [Rule 1 - Bug] Exact `sign` local tripped the no-signing-symbols guard**
- **Found during:** Full suite (`test_no_signing_symbols_outside_live_stub` failed on `render.py:16,18`)
- **Issue:** `sol()` named its minus-prefix local `sign`, an exact-match forbidden symbol outside `execution/live/`.
- **Fix:** Renamed to `neg`; no behavior change.
- **Files modified:** `src/pumpgrok/reporting/render.py`
- **Commit:** `c92b294`

**4. [Rule 3 - Blocking] 59 UP030/UP032 findings in plan files failed the lint gate**
- **Found during:** Fix pass (assignment step 3; `ruff check .` exit 1)
- **Issue:** Inline `"{0}".format(...)` literals in the 5 plan files; proven plan-introduced (HEAD~3 worktree clean), not pre-existing.
- **Fix:** Named `str.format` template constants in `render.py`/`daily.py`/`weekly.py`; f-strings in `cli.py`/`live_gate.py`; wrapped 7 E501 lines; applied 1 SIM108 ternary; repaired one indent slip from the wrap itself.
- **Files modified:** all 5 files above
- **Commit:** `c92b294`

### Environment notes (not code deviations)

- `uv run mypy src/` first crashed with mypy 2.4.0 INTERNAL ERROR on a stale `.mypy_cache`; after `rm -rf .mypy_cache` both `mypy src/` and bare `mypy` exit 0. Per-package runs were clean throughout.
- One `uv run pytest -q` run collected nothing ("No tests collected") while a sibling executor was active; clean reruns collect and pass (exit 0). The `.venv/bin/python -m pytest` form is stable.
- One combined `>out 2>err` live-refusal run returned exit 1 with empty files under concurrency; clean sequential reruns return exit 3 with the full stderr block. All recorded criteria outputs come from quiet reruns.

## Known Stubs

None. Grep over `reporting/` and `execution/live/` finds no TODO, FIXME, placeholder, or missing-data marker.

## Threat Flags

None beyond the plan register. No new network endpoints, auth paths, file access, or schema changes: reports read the ledger read-only, the live path refuses before any other work, and the confirm secret travels only via `PUMPGROK_CONFIRMATION_KEY` (T-04-19, T-04-20, T-04-21 mitigations hold). No new packages (T-04-SC).

## Scope note

The 04-08 ROADMAP checkbox and its AUTO/RISK requirements still read pending although `04-08-SUMMARY.md` (status complete) is committed; that bookkeeping gap predates this plan and is left untouched as out of scope.

## Self-Check: PASSED

- All 7 created files exist; `bd663a8`, `fdf40e8`, `ea06b2b`, `c92b294` present in `git log`.
- `run --mode live --once` exits 3 with nine R21 stderr lines and 0 stdout bytes; both reports exit 0 with non-ASCII count 0.
- Vendor dir absent, license present, scoped census prints nothing.
- Full suite exit 0 (1184 passed, 2 skipped); ruff, format, mypy exit 0.
