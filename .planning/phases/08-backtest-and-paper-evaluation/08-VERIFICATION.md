# Phase 8 Verification Report: Backtest and paper evaluation

Status: passed

Gaps: none. All 13 roadmap criteria verify against code, tests, and gate logs. One wording note under J: criterion 12 prose expects changed replay output, but the correction kept per-fill fields memory-only so the hash is unchanged; the CHANGELOG records this honestly and the gate command itself exits 0.

Scope: /root/src/repos/pumpgrok code HEAD e6288de on branch bot-00-chief/phase-6-integrity. Read-only verification. No gate was rerun; gate evidence comes from orchestrator logs listed below.

Gate logs read:
- /tmp/f8_lint.log, lint exit 0
- /tmp/f8_type.log, typecheck exit 0
- /tmp/f8_test.log, full make test exit 0
- /tmp/f8_check.log, scripts/check.sh exit 0
- /tmp/f8_vdc.log, verify_doc_commands exit 0
- /tmp/f8_smoke.log, smoke replay exit 0
- /tmp/f8_live.log, live refusal output, exit 3
- smoke-10m events.hash b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d on both runs, equal to BEFORE
- criterion 7 backtest double run exit 0; criterion 8 grep exit 0; criterion 6 greps exit 0

## Criteria table, roadmap Phase 8 success criteria 1 to 13

| Criterion | Command | Verdict | Evidence |
| --- | --- | --- | --- |
| 1 | make lint, make typecheck, make test, ./scripts/check.sh, each exit 0, plus paper smoke replay exit 0 | PASS | /tmp/f8_lint.log, /tmp/f8_type.log, /tmp/f8_test.log, /tmp/f8_check.log, /tmp/f8_smoke.log all exit 0 per orchestrator |
| 2 | uv run pytest -q tests/backtest/test_run_manifest.py | PASS | file exists at /root/src/repos/pumpgrok/tests/backtest/test_run_manifest.py; full suite green in /tmp/f8_test.log; code: /root/src/repos/pumpgrok/src/pumpgrok/backtest/manifest.py dataset_digest hashes every file in the dataset dir, run_id is sha256 over the manifest, filter_settings_hash and param_set_hash recorded |
| 3 | uv run pytest -q tests/backtest/test_replay_result_fields.py | PASS | file exists; suite green; code: /root/src/repos/pumpgrok/src/pumpgrok/replay/runner.py class ReplayTrade carries price_avg, venue_fee_lamports, network_cost_lamports, latency_s, filled_fraction, outcome |
| 4 | uv run pytest -q tests/backtest/test_holdout_split.py | PASS | file exists; suite green; code: /root/src/repos/pumpgrok/src/pumpgrok/backtest/split.py HOLDOUT_FRACTION equals 0.20; harness asserts tuning stamps below cutoff |
| 5 | uv run pytest -q tests/backtest/test_trial_limits.py | PASS | file exists; suite green; code: /root/src/repos/pumpgrok/src/pumpgrok/backtest/trials.py MAX_ELIGIBLE_TRIALS equals 20, MAX_ALLOWED_TRIALS equals 50, TooManyTrialsError with code too_many_trials |
| 6 | uv run pytest -q tests/backtest/test_metrics.py plus annualiz grep plus no-expected-return grep | PASS | file exists; suite green; /root/src/repos/pumpgrok/src/pumpgrok/backtest/metrics.py states ANNUALIZATION_DAYS_PER_YEAR equals 365 and annualization in comments; expected-return grep over backtest and reporting returns nothing |
| 7 | uv run pumpgrok backtest --fixture smoke-10m twice byte-identical; report names holdout, trial, slippage, fees | PASS | orchestrator double run exit 0; /tmp/bt-a.md contains holdout_id, trial_count, realized_slippage_bps_total, realized_fees_lamports_total; renderer is /root/src/repos/pumpgrok/src/pumpgrok/backtest/report.py render with sorted keys and no wall-clock values |
| 8 | no grid or itertools.product in engine or backtest; test_single_search_engine green | PASS | orchestrator grep exit 0; /root/src/repos/pumpgrok/src/pumpgrok/engine/tune.py absent; file /root/src/repos/pumpgrok/tests/backtest/test_single_search_engine.py exists; suite green |
| 9 | uv run pytest -q tests/backtest/test_shared_result_schema.py | PASS | file exists; suite green; code: /root/src/repos/pumpgrok/src/pumpgrok/backtest/results.py SharedResult.from_fills, from_ledger_rows, compare with window equality |
| 10 | uv run pytest -q tests/backtest/test_divergence.py | PASS | file exists; suite green; code: /root/src/repos/pumpgrok/src/pumpgrok/backtest/divergence.py ABSOLUTE_RETURN_GAP_PP equals 2.0, SHARPE_GAP equals 0.5, breach_line, enforce |
| 11 | uv run pytest -q tests/e2e/test_autonomous_paper_recorded.py tests/safety/test_manual_ticket_no_upgrade.py | PASS | both files exist; suite green |
| 12 | verify hash stable across runs; CHANGELOG before and after lines | PASS with wording note | both runs print b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d; /root/src/repos/pumpgrok/CHANGELOG.md lines 22 to 24 hold the before line, the after line, and the correction bullet; see J for the prose mismatch |
| 13 | uv run pumpgrok run --mode live --once; test exit code 3 | PASS | /tmp/f8_live.log shows the nine-precondition refusal; orchestrator reports exit 3; /root/src/repos/pumpgrok/tests/safety/test_no_backtest_to_live_path.py pins exit 3 |

## Substance checks A to J

### A. Hollow-evaluator sweep, verdict PASS

Grep for sha256, hashlib, random, Random, secrets, uuid over /root/src/repos/pumpgrok/src/pumpgrok/backtest and /root/src/repos/pumpgrok/src/pumpgrok/cli.py.

Hits and classification:
- /root/src/repos/pumpgrok/src/pumpgrok/backtest/manifest.py: hashlib sha256 in dataset_digest, filter_settings_hash, param_set_hash, run_id. Identity only. Each names inputs, for example run_id is sha256 over the canonical JSON of the manifest. Never a score.
- /root/src/repos/pumpgrok/src/pumpgrok/backtest/evaluate.py: the only hash-adjacent words are comments stating no digest acts as a score; param_set_hash is used on the sliced window bytes as a slice identity marker, not a score. The word random appears only in the comment forbidding random draws as scores.
- /root/src/repos/pumpgrok/src/pumpgrok/backtest/harness.py: random appears only in the comment stating space order with no shuffle. Scoring is total and mean over evaluate_window lamports with strict greater-than tracking.
- /root/src/repos/pumpgrok/src/pumpgrok/backtest/split.py and trials.py: random appears only in comments stating no randomness.
- /root/src/repos/pumpgrok/src/pumpgrok/cli.py: hashlib sha256 and hmac appear in the live-confirmation statement path around lines 1112 to 1132, plus refuse_cli_secrets import. No hash, random, or uuid feeds a backtest score, metric, verdict, or sort. The backtest verb uses make_rng only indirectly through IdFactory for the default ledger run id, which is identity.

No score, metric, verdict, or sort derives from a hash or random value. The old _score_candidate and _evaluate_holdout digest scorers are gone; the only remaining match is a comment describing their removal.

### B. Real replay, verdict PASS

Function chain:
- /root/src/repos/pumpgrok/src/pumpgrok/backtest/evaluate.py evaluate_window slices recorded events by window stamps, materializes the slice as events.jsonl plus manifest, then calls run_once_replay from /root/src/repos/pumpgrok/src/pumpgrok/supervisor/scheduler.py with params.filter_settings, seed, explicit ledger_path, and params.exits_settings. The score is _net_lamports over FillRecorded rows: sells minus buys minus venue fees and network costs, partial fills at recorded filled amounts, zero trades score 0.
- /root/src/repos/pumpgrok/src/pumpgrok/backtest/harness.py run_search takes candidates in space order, validates each through CandidateParams, records every trial in the TrialLedger, sums evaluate_window over the pre-holdout fold windows, tracks the best by strict greater-than, then evaluates the winner once on the holdout window. Tuning never feeds on holdout data: asserts require tuning stamps below cutoff and fold windows ending at or below cutoff; holdout stamps are asserted at or past cutoff and the holdout evaluation happens after selection.
- /root/src/repos/pumpgrok/src/pumpgrok/cli.py _backtest_verb calls run_search with the single validated candidate, then _evaluate_holdout replays the holdout window once via evaluate_window and summarizes fills into window metrics. No digest anywhere in the scoring path.

Holdout isolation confirmed in /root/src/repos/pumpgrok/src/pumpgrok/backtest/harness.py: tuning_stamps filtered below cutoff, assert all tuning stamps below cutoff, assert each fold window ends at or below cutoff, and the holdout evaluate_window call occurs after best selection.

### C. Zero-trade honesty, verdict PASS

- /root/src/repos/pumpgrok/src/pumpgrok/backtest/report.py build_report: when metrics.trade_count equals 0, total_return, max_drawdown, sharpe_ratio, and win_rate are set to None. The _decimal renderer prints None as not-applicable. trade_count, exposure_lamports, and turnover_lamports render as 0 with stated assumptions counting fills, biggest single commitment, and sum of notionals.
- Fee and slippage totals are summed from fills in ledger order: slippage_total sums realised_slippage_bps, fees_total sums venue_fee_lamports plus network_cost_lamports. Nothing is hard-coded; zero is the empty sum.
- Layering note: /root/src/repos/pumpgrok/src/pumpgrok/backtest/metrics.py summarize returns Decimal 0 metrics for an empty fill list. Those metric-level zeros never reach the reader as measured performance because build_report maps them to not-applicable. The render contract, not the summarize default, is what the user sees.
- Pinned by /root/src/repos/pumpgrok/tests/backtest/test_report_render.py: not-applicable appears exactly 4 times, total_return, max_drawdown, sharpe_ratio, and win_rate each render not-applicable, trade_count 0, exposure 0, turnover 0, zeroed fee and slippage totals render 0, alongside real window identity.

### D. Eligibility, verdict PASS

- Computing lines: /root/src/repos/pumpgrok/src/pumpgrok/cli.py _paper_gate. Without a paper ledger path it returns promotion_eligible False with reason divergence not compared. With a ledger it builds the same-window paper summary, enforces window equality via SharedResult.compare, runs divergence check, and on breach returns False with the breach reason and exit 1 via enforce. On a clean verdict it returns True only when the passed-in eligible flag from the harness is true, with reason trial count within limit and paper divergence within D7 defaults. Otherwise False.
- The harness eligible flag comes from /root/src/repos/pumpgrok/src/pumpgrok/backtest/harness.py: eligible is true only when every ledger verdict is eligible, cross-checked against ledger length at or below MAX_ELIGIBLE_TRIALS.
- Trial count above 20 therefore cannot promote: the ledger marks trial 21 ineligible, eligible becomes False, _paper_gate returns False, and the report carries the past-the-limit reason.
- Label check: /root/src/repos/pumpgrok/src/pumpgrok/backtest/report.py render prints trial_limit_eligible from eligible_for_promotion and, separately, promotion_eligible from promotion_eligible. The renamed trial label is not confused with promotion; both appear in /tmp/bt-a.md as trial_limit_eligible true and promotion_eligible false.

### E. Divergence, verdict PASS

- Constants: /root/src/repos/pumpgrok/src/pumpgrok/backtest/divergence.py ABSOLUTE_RETURN_GAP_PP equals 2.0 and SHARPE_GAP equals 0.5, each citing PROJECT.md V3-4 D7 in comments.
- Same-window enforcement: /root/src/repos/pumpgrok/src/pumpgrok/cli.py _paper_gate filters paper rows by _row_in_window at the cutoff, builds paper SharedResult over cutoff to infinity, calls backtest_result.compare before check, and compare rejects foreign windows and mismatched fills.
- Breach behavior: check sets blocks_promotion on at-or-past thresholds; breach_line returns the DIVERGENCE BREACH line with four-decimal gaps and reasons; enforce returns 1 when blocked else 0; _paper_gate prints the line to stderr and returns exit 1.
- Reachability: _backtest_verb calls _paper_gate and returns gate.exit_code; argparse registers the backtest verb and VERBS maps backtest to _backtest_verb in /root/src/repos/pumpgrok/src/pumpgrok/cli.py. The no-ledger default returns exit 0 with promotion false; the breach path with a supplied ledger returns exit 1. Dead code is not present: every helper in this chain is called from the verb.

### F. Tests are not wiring checks, verdict PASS overall

One key assert per file, quoted exactly:
- test_evaluator.py: PASS, real behaviour. Quote: assert score == expected, where expected replays the same window through the supervisor and sums fills independently.
- test_single_search_engine.py: PASS, real behaviour with a static scan inside. The file asserts source text has exactly one run_search and no itertools.product, and it also executes run_search on smoke asserting result.holdout_id == smoke-holdout with trial counts and cutoff isolation: assert end_ts <= cutoff, tuning window reached past the cutoff.
- test_report_render.py: PASS, real behaviour. Quote: assert text.count not-applicable == 4 plus assert realized_slippage_bps_total: 7 in the nonzero case, pinning sums from fills.
- test_divergence.py: PASS, real behaviour. Quote: assert verdict.blocks_promotion is True at the 2.0 return gap and assert DIVERGENCE BREACH in breach_line output.
- test_holdout_split.py: PASS, real behaviour. Quote: assert HOLDOUT_FRACTION == 0.20 with holdout id smoke-holdout and stamps partitioned at the cutoff.
- test_trial_limits.py: PASS, real behaviour. Quote: assert verdicts trial 21 eligible_for_promotion is False and with pytest.raises TooManyTrialsError at trial 51 with nothing stored.
- test_metrics.py: PASS, real behaviour. Quote: assert report.total_return == Decimal 300 / Decimal 10000 and assert ANNUALIZATION_DAYS_PER_YEAR == 365 with the Sharpe ratio matched against an independent computation.
- test_replay_result_fields.py: PASS, real behaviour. Quote: assert trade.price_avg > 0 and assert filled_fraction > 0 on fills from a live smoke replay, with typed integer fee fields.
- test_shared_result_schema.py: PASS, real behaviour. Quote: assert verdict.matched with assert verdict.differences == empty tuple on identical fills, and mismatch detected down to fills venue_fee_lamports 100000 != 100001.
- test_run_manifest.py: PASS, real behaviour. Quote: filter_settings_hash of defaults equals itself while a changed setting hashes differently, and run ids derive from the manifest digest.
- test_autonomous_paper_recorded.py: PASS, real behaviour. Quote: assert trades filled=2 not_filled=1 on smoke with FillRecorded rows, minted approvals, and ledger verify.
- test_manual_ticket_no_upgrade.py: PASS, real behaviour. Quote: assert not var backtest exists and assert autonomy change lists are empty after a manual-ticket run.
- test_no_backtest_to_live_path.py: PASS, real behaviour plus static guard. Quote: assert main run --mode live --once --replay SMOKE == 3 with an import scan finding no backtest or paper to live adapter path.

No file asserts only non-emptiness or wording. Every file executes the unit under test and pins numeric or behavioral outcomes.

### G. Criterion 2 to 13 mapping, verdicts

Covered in the criteria table above. Each criterion names its exact command, the corresponding test or command exists in the tree at the path given, and the verdict is PASS on gate-log evidence plus code presence. Criterion 1 additionally passes on /tmp/f8_lint.log, /tmp/f8_type.log, /tmp/f8_test.log, /tmp/f8_check.log, and /tmp/f8_smoke.log.

### H. Requirement BT-06 report contents, verdict PASS

Checked in /root/src/repos/pumpgrok/src/pumpgrok/backtest/report.py render:
- fees: realized_fees_lamports_total plus schedule fields venue_fee_bps, base_fee_lamports, network_cost_lamports. Present.
- slippage: realized_slippage_bps_total. Present.
- data window: data_start_utc, data_end_utc, window_start_utc, window_end_utc. Present, all from recorded event timestamps.
- trial count: trial_count plus max_eligible_trials and max_allowed_trials. Present.
- holdout id: holdout_id plus split_ids. Present.
All five render in /tmp/bt-a.md.

### I. CHANGELOG, verdict PASS

- /root/src/repos/pumpgrok/CHANGELOG.md line 22: Phase 8 smoke-10m events.hash before b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d.
- Line 23: Phase 8 smoke-10m events.hash after with the identical value.
- Line 24: correction bullet stating the first harness scored with a hash digest, the replacement by net realized lamports, and that per-fill fields are memory-only so ledger bytes and hash are unchanged.
- The after hash equals the before hash, matching the two equal orchestator run hashes.
- The report claims no change in replay output. It explicitly claims the opposite: the hash is unchanged because the new fields never enter ledger bytes. No false change claim exists.

### J. Criterion 12 wording judgment

Criterion 12 reads: the result schema changes replay output, so the before and after hash are both recorded.

Judgment: the recording obligation is fully satisfied. Both runs are stable, both CHANGELOG lines exist, and the values match the measured runs. The rationale clause, the result schema changes replay output, is not literally satisfied: the schema gained per-fill fields but they are held in memory only, so replay ledger bytes and the events.hash did not change. The CHANGELOG correction bullet discloses exactly this. This is a wording mismatch in the criterion prose, not a code or honesty gap. No plan or code change follows from it; a later roadmap edit may reword the rationale to say the schema may change replay output and both values are recorded either way.

## Not verified

- Nothing material remains unverified. Static import-scan portions of test_single_search_engine.py and test_no_backtest_to_live_path.py were read, not executed here, but both files also execute behavior and the full suite is green in /tmp/f8_test.log.
- Live exit code 3 is taken from the orchestrator log /tmp/f8_live.log content plus the brief; the command was not rerun per the brief rules.
- Fixture-level trade behavior on smoke-10m holdout shows zero trades with honest not-applicable rendering; this is the fixtures producing no holdout entries under defaults, not a defect, and the evaluator test pins nonzero scoring on the full smoke window.
