---
phase: 10
status: passed
requirements: [LIV-01, LIV-02]
verified_at_commit: e58920b
reverification_reason: milestone audit requirement traceability (9bfb0f6 audit found LIV-01 import claim false at runtime; prior file in git history at 9bfb0f6)
---

# Phase 10 Verification: Live readiness, kept disabled

Re-verified at HEAD `e58920b` on branch `bot-00-chief/v3-closeout` in `/root/src/repos/pumpgrok-wt/v3-closeout`. All commands ran from the worktree root. Exit codes are the process exit codes captured in the shell. The full pytest suite was not run; see criterion 1e. No product code, tests, CHANGELOG, ROADMAP, or REQUIREMENTS were edited.

## Correction to the earlier verification

The earlier version of this file recorded the import-graph claim as PASS (criterion 4, substance check C). The milestone audit (`.planning/v3-MILESTONE-AUDIT.md`, LIV-01, critical) showed that claim false at runtime. `pumpgrok.cli.backtest` and `pumpgrok.cli.promotion` load `pumpgrok.execution.live/__init__.py` through the `pumpgrok.cli` package, and that `__init__.py` imports `LiveAdapterStub`. The AST guard `tests/safety/test_import_graph_no_live.py` did not follow parent-package edges, so it passed while the runtime path existed.

Phase 20 fixed this: `148dbfa` (red regression tests), `02f5997` (fix: keep live adapter off the CLI import path), `21e99dd` (CHANGELOG), `c3898ec` (plan summary). Its verification is `.planning/phases/20-close-gap-liv-01-live-adapter-import-path/20-VERIFICATION.md`. This file does not rely on the earlier PASS. The import-graph criterion below cites Phase 20 evidence and the probe run at HEAD.

## Criteria

| # | Criterion | Command | Exit | Result | Verdict |
|---|---|---|---|---|---|
| 1a | Lint gate (ROADMAP 1) | `make lint` | 0 | `816 files already formatted`; log `/tmp/r10_lint.log` | PASS |
| 1b | Typecheck gate (ROADMAP 1) | `make typecheck` | 0 | `Success: no issues found in 208 source files` | PASS |
| 1c | Repository check (ROADMAP 1) | `./scripts/check.sh` | 0 | `ok: 35 skills, 10 agents, 318 markdown files checked`; `PumpGrok repository structure looks healthy.` | PASS |
| 1d | Paper replay (ROADMAP 1) | `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` | 0 | `trades filled=2 not_filled=1` | PASS |
| 1e | Test gate (ROADMAP 1) | `make test` | not run here | Full suite excluded by assignment. Carried from Phase 20 at `c3898ec`: `make test` exit 0, and full junit `tests="2404" failures="0" errors="0" skipped="2"`. Diff `c3898ec..e58920b` touches only `.planning/` files (6 files, no `src/` or `tests/` path). | PASS (carried, not re-run) |
| 2a | Live refusal exits 3 and names nine preconditions (ROADMAP 2) | `uv run pumpgrok run --mode live --once; test $? -eq 3` | process 3; wrapper 0 | Header `LIVE GATE: refusing to start in mode=live. 8 of 9 preconditions unmet:`, then numbered lines 1 to 9 (`mode_live`, `live_enable_env`, `min_paper_days`, `performance_thresholds`, `wallet_allowlist`, `notional_cap`, `confirmation_record`, `adapter_registered`, `no_active_stop`), then `Fix every unmet line or run in mode=paper. No transaction was attempted.` Log `/tmp/r10_live_refusal.log`. | PASS |
| 2b | Fail-fast and refusal tests (ROADMAP 2) | `uv run python -m pytest -q tests/execution/test_live_gate_fails_fast.py tests/safety/test_live_refusal_lists_nine.py --junitxml=/tmp/r10_c2.xml` | 0 | `tests="24" failures="0" errors="0" skipped="0"` | PASS |
| 3 | No live adapter registered (ROADMAP 3) | `uv run python -m pytest -q tests/safety/test_no_live_adapter_registered.py --junitxml=/tmp/r10_c3.xml` | 0 | `tests="3" failures="0" errors="0" skipped="0"` | PASS |
| 4 | Import graph has no path to a live adapter (ROADMAP 4) | `uv run python -m pytest -q tests/safety/test_import_graph_no_live.py --junitxml=/tmp/r10_c4.xml` | 0 | `tests="17" failures="0" errors="0" skipped="0"`. Includes `test_guard_follows_parent_package_init` (added in Phase 20). Runtime confirmation in the probe section below. | PASS |
| 5 | Live disabled in every overlay (ROADMAP 5) | `for f in src/pumpgrok/config/overlays/*.toml; do uv run python -c "import tomllib,sys; d=tomllib.load(open('$f','rb')); assert d.get('live',{}).get('enabled') is False, '$f'" \|\| exit 1; done` | 0 | Three overlays: `dev.toml`, `live.toml`, `paper.toml`. Each assertion exits 0. | PASS |
| 6 | Safety suite and signing/custody guard (ROADMAP 6) | `uv run python -m pytest -q tests/safety --junitxml=/tmp/r10_c6.xml` | 0 | `tests="213" failures="0" errors="0" skipped="0"`. Includes `test_no_signing_outside_live_stub.py`. | PASS |
| 7 | Live-readiness record present and deferred (ROADMAP 7) | `test -f docs/LIVE_READINESS.md && grep -qi "status: deferred" docs/LIVE_READINESS.md && grep -qi "custody" ... && grep -qi "venue" ... && grep -qi "legal" ... && grep -qi "nine" ...` | 0 | Line 3 `status: deferred`. Sections `## 1. Custody model`, `## 2. Venue`, `## 3. Legal review`, `## 4. Nine-precondition evidence`, `## Refusal proof and exit contract`, `## What this record does not claim`. Sections 1 to 4 each carry `Status: deferred`. | PASS |
| 8 | Replay verify stable and recorded in CHANGELOG (ROADMAP 8) | `uv run pumpgrok verify --fixture smoke-10m` (twice), then the ROADMAP grep | 0 | Both runs: `events.hash=b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`, `verify=CONSISTENT seq=2 events=41`. Hashes equal. `CHANGELOG.md` lines 61 and 62 carry `Phase 10: smoke-10m events.hash after: b69c...ad32d`. Phase 9 lines 78 and 79 carry the same hash. | PASS |

## Runtime probe (import graph, LIV-01)

Command: fresh interpreter run from the worktree root:

```
uv run python -c "import sys; import pumpgrok.cli; import pumpgrok.cli.backtest; import pumpgrok.cli.promotion; import pumpgrok; print(pumpgrok.__file__); print('live_adapter_in_sys_modules=', 'pumpgrok.execution.live.live_adapter' in sys.modules); print('live_gate_in_sys_modules=', 'pumpgrok.execution.live.live_gate' in sys.modules)"
```

Exit: 0.

Output:

- `pumpgrok.__file__=/root/src/repos/pumpgrok-wt/v3-closeout/src/pumpgrok/__init__.py` (worktree source, not the other checkout)
- `live_adapter_in_sys_modules= False`
- `live_gate_in_sys_modules= True`

Verdict: PASS. The live adapter is not loaded on the three CLI import paths, and the gate stays loaded.

Supplementary: `uv run python -m pytest -q tests/test_live_gate.py --junitxml=/tmp/r10_gate.xml` exits 0 with `tests="5" failures="0" errors="0" skipped="0"`.

## Requirements

| ID | Requirement (REQUIREMENTS.md) | Status | Evidence |
|---|---|---|---|
| LIV-01 | Live stays refused. `run --mode live` exits 3 listing the nine preconditions, no live adapter is registered, and an import-graph test shows no path from backtest, paper or upgrade modules to a live adapter. | satisfied | Phase 20 evidence: `.planning/phases/20-close-gap-liv-01-live-adapter-import-path/20-VERIFICATION.md` (runtime probe `adapter= False gate= True` at `c3898ec`; guard suite 17 tests passing; commits `148dbfa`, `02f5997`, `21e99dd`, `c3898ec`). This run, at HEAD `e58920b`: runtime probe `live_adapter_in_sys_modules= False`, `live_gate_in_sys_modules= True` (see Runtime probe). Refusal: criterion 2a, exit 3, nine precondition lines. No live adapter registered: criterion 3, `tests="3" failures="0"`. Import graph: criterion 4, `tests="17" failures="0"`. |
| LIV-02 | A live-readiness record lists what a future decision requires (custody model, venue, legal review, nine-precondition evidence) and is recorded as deferred. No signing or custody code is added. | satisfied | Record: `docs/LIVE_READINESS.md` line 3 `status: deferred`; sections at lines 16 (`## 1. Custody model`), 39 (`## 2. Venue`), 63 (`## 3. Legal review`), 85 (`## 4. Nine-precondition evidence`), 147 (`## What this record does not claim`); criterion 7. No signing code: `grep -rniwE "sign|signing|hmac|ed25519|private_key|keypair" src/pumpgrok/execution/live` exits 1 (no match). Guard: criterion 6, `tests/safety` `tests="213" failures="0"`, including `test_no_signing_outside_live_stub.py`. Phase 10 product code is unchanged since the audit: `git diff --stat 9bfb0f6..HEAD -- src tests` lists only Phase 20 files. |

## Notes

1. Criterion 1e (`make test`) was not re-run because the full suite is excluded for this verification. Its PASS rests on Phase 20 evidence at `c3898ec`. The only later commits touch `.planning/` files. A run at `e58920b` is still unobserved.
2. Header wording. The live refusal header now reads `8 of 9 preconditions unmet`, and the earlier file recorded `9 of 9`. Precondition 6 (notional cap) is met at the default 1 SOL cap, so 8 are unmet. The criterion requires exit 3 and that all nine preconditions be named, and both hold. Phase 20 recorded the same wording.
3. Commit lineage. The commit range cited by the earlier file (`fd973f5..HEAD`) is not reachable from HEAD in this history. The no-product-change argument is therefore re-based on `9bfb0f6..HEAD` (only Phase 20 files under `src/` and `tests/`) and on the direct signing grep above.
4. Residual risk, import graph. The AST guard follows static imports, including parent-package edges. It does not model dynamic imports (`importlib`, `__import__`). The runtime probe covers only the three named entry modules.
5. Residual risk, record. The criterion 7 check is a keyword grep. Section content was checked by heading and status line, not by a full read.
6. Pytest form. Tests were run as `uv run python -m pytest` per the assignment's form. The ROADMAP text reads `uv run pytest`; the test selection is the same.
7. File counts. `scripts/check.sh` counts 318 markdown files at HEAD, against 316 in Phase 20. The difference comes from added planning files and is not a failure.
