---
phase: 08-backtest-and-paper-evaluation
verified_at_commit: e58920b
status: passed
requirements: [BT-01, BT-02, BT-03, BT-04, BT-05, BT-06, BT-07, PAP-01, PAP-02, PAP-03]
reverification_reason: Milestone v3 closeout audit needs each requirement ID cited explicitly. Prior passed report (commit 9bfb0f6 and earlier) cited code at da6c071 and e6288de under /root/src/repos/pumpgrok; this re-verification runs on the v3-closeout worktree at e58920b.
notes: >
  Path drift: worktree is /root/src/repos/pumpgrok-wt/v3-closeout on branch bot-00-chief/v3-closeout.
  Prior report cited /root/src/repos/pumpgrok paths. Code under src, tests, scripts, Makefile, pyproject.toml, ci and uv.lock is identical to commit c3898ec.
  `pumpgrok backtest` has no --out flag; the report goes to stdout, which was redirected to /tmp/p8/bt-a.md and /tmp/p8/bt-b.md.
  make test was not rerun here; orchestrator evidence is /tmp/mt-e58920b.txt (run on e58920b, exit 0, 100 percent).
  Criterion 12 before and after hashes are equal (b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d); the schema change did not alter replay output.
---

# Phase 8 Verification Report: Backtest and paper evaluation

Status: passed
Gaps: none.
Scope: worktree /root/src/repos/pumpgrok-wt/v3-closeout, HEAD e58920b, branch bot-00-chief/v3-closeout. Read-only verification; no code, tests, CHANGELOG, ROADMAP or REQUIREMENTS edits. Working tree unchanged by this run (`git status --short` identical before and after).

## Criteria table (ROADMAP Phase 8, success criteria 1 to 13)

Scratch output is under /tmp/p8. Targeted pytest covered `tests/backtest`, `tests/e2e/test_autonomous_paper_recorded.py` and `tests/safety/test_manual_ticket_no_upgrade.py`: 91 tests, 0 failures, 0 errors, 0 skipped (junit /tmp/p8/p8-targeted.xml).

| # | Command | Exit code | Result | PASS or FAIL |
| --- | --- | --- | --- | --- |
| 1 | `ruff check .` and `ruff format --check .` (make lint); `mypy src/` (make typecheck); `./scripts/check.sh`; `pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke`. make test is orchestrator evidence (/tmp/mt-e58920b.txt). | 0, 0, 0, 0; make test 0 per orchestrator | ruff clean; mypy: no issues in 208 files; check.sh: 35 skills, 10 agents, 318 markdown files ok; smoke replay completed one cycle | PASS |
| 2 | `pytest tests/backtest/test_run_manifest.py` (in targeted run) | 0 | Included in 91 passing tests | PASS |
| 3 | `pytest tests/backtest/test_replay_result_fields.py` | 0 | Included in 91 passing tests | PASS |
| 4 | `pytest tests/backtest/test_holdout_split.py` | 0 | Included in 91 passing tests | PASS |
| 5 | `pytest tests/backtest/test_trial_limits.py` | 0 | Included in 91 passing tests | PASS |
| 6 | `pytest tests/backtest/test_metrics.py`; `grep -rnE "annualiz" src/pumpgrok/backtest`; `! grep -rniE "expected (return|profit|pnl)|will earn" src/pumpgrok/backtest src/pumpgrok/reporting` | 0; 0; 0 | Tests pass. Annualization stated in metrics.py (365 days per year). No expected-return language matched | PASS |
| 7 | `pumpgrok backtest --fixture smoke-10m` twice to /tmp/p8/bt-a.md and bt-b.md; `cmp`; grep holdout, trial, slippage, fees | 0, 0, 0 (cmp), 0 for all four | Byte-identical. Report contains holdout, trial, slippage and fees fields | PASS |
| 8 | `! grep -rnE "grid|itertools\.product" src/pumpgrok/engine src/pumpgrok/backtest`; `pytest tests/backtest/test_single_search_engine.py` | 0 (grep found no match, exit 1 inverted); 0 | No grid or product match; single-search-engine test passes | PASS |
| 9 | `pytest tests/backtest/test_shared_result_schema.py` | 0 | Included in 91 passing tests | PASS |
| 10 | `pytest tests/backtest/test_divergence.py` | 0 | Included in 91 passing tests; separate run also exit 0 | PASS |
| 11 | `pytest tests/e2e/test_autonomous_paper_recorded.py tests/safety/test_manual_ticket_no_upgrade.py` | 0 | Included in 91 passing tests | PASS |
| 12 | `pumpgrok verify --fixture smoke-10m` twice (hashes equal); CHANGELOG Phase 8 before and after lines | 0 | Both runs b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d. CHANGELOG lines 98 and 99 carry before and after with that same value | PASS |
| 13 | `pumpgrok run --mode live --once; test $? -eq 3` | 3 (expected) | Live refused, exit 3 (/tmp/p8/live.log) | PASS |

## Requirements table

| ID | Requirement (REQUIREMENTS.md) | Status | Evidence |
| --- | --- | --- | --- |
| BT-01 | Run manifest with whole-dataset digest, seed, FilterSettings hash, parameter-set hash, code version; run id derives from manifest | PASS | Criterion 2 test passes. src/pumpgrok/backtest/manifest.py |
| BT-02 | Per-fill price, venue fee, network cost, latency, filled fraction, outcome | PASS | Criterion 3 test passes. src/pumpgrok/replay/runner.py |
| BT-03 | Holdout is final 20 percent, never used for tuning; folds tune; report names split ids | PASS | Criterion 4 test passes. src/pumpgrok/backtest/split.py; report contains holdout id (bt-a.md) |
| BT-04 | Every trial recorded; above 20 flagged ineligible; above 50 rejected | PASS | Criterion 5 test passes. src/pumpgrok/backtest/trials.py |
| BT-05 | Metrics with stated annualization, no expected-return language | PASS | Criterion 6 test and greps pass. src/pumpgrok/backtest/metrics.py |
| BT-06 | `pumpgrok backtest` report with fees, slippage, window, trial count, holdout id; byte-identical runs | PASS | Criterion 7 cmp exit 0 and greps exit 0 |
| BT-07 | In-sample grid search replaced by holdout-aware harness; no second search engine | PASS | Criterion 8 grep and test pass. src/pumpgrok/backtest/harness.py |
| PAP-01 | Backtest and paper ledger trades share one result schema over the same window | PASS | Criterion 9 test passes. src/pumpgrok/backtest/results.py |
| PAP-02 | Divergence check on D7 defaults (2 pp absolute return gap or 0.5 Sharpe gap) over the same window; breach raises an alert and blocks promotion | PASS | See PAP-02 conclusion below |
| PAP-03 | Autonomous paper verified end to end on recorded datasets; manual-ticket never runs upgrades | PASS | Criterion 11 tests pass |

## PAP-02 conclusion

Question: the earlier integration check warned that the alert channel was unverified (backtest/divergence.py:92 and cli/backtest.py:546-557).

Requirement text relied on (.planning/REQUIREMENTS.md line 43): "PAP-02: A divergence check uses the D7 defaults (2 percentage points absolute return gap, or 0.5 Sharpe gap) over the same window. A breach raises an alert and blocks promotion."

Roadmap Phase 8 criterion 10: "a 2 percentage point absolute return gap and a 0.5 Sharpe gap each raise an alert and block promotion, using the D7 defaults as the configured values (PAP-02)."

Conclusion: the requirement text does not name a delivery channel (no Telegram, pager, or operator-notification requirement). Its stated behavior is an alert that is raised and a promotion that is blocked. Evidence that both behaviors occur:
- divergence.py:23-27 sets ABSOLUTE_RETURN_GAP_PP = 2.0 and SHARPE_GAP = 0.5. check() returns blocks_promotion at or past either default.
- divergence.py:breach_line() builds the "DIVERGENCE BREACH ..." alert text, and enforce() returns exit code 1 when blocked.
- cli/backtest.py:546-557 prints that line to stderr on breach and returns a promotion-ineligible outcome with reason "divergence breach".
- upgrade/gate.py:162-163 records REASON_DIVERGENCE_BREACH with the breach line as detail, so the promotion gate blocks.
- tests/backtest/test_divergence.py passes (2 pp and 0.5 Sharpe gap cases, both block).

The unverified part is whether a human-facing channel (for example Telegram) delivers the stderr alert. That is not part of PAP-02 and is not claimed here. Result: PAP-02 is met as written; no gaps_found.

## Gate logs and evidence
- Lint, typecheck, check.sh, targeted pytest, backtest double-run, verify double-run, smoke replay, live refusal: this run, under /tmp/p8.
- make test on e58920b: orchestrator log /tmp/mt-e58920b.txt (reports 100 percent; exit 0 per orchestrator).
