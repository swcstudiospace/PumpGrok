# Phase 8 correction set: replacing the digest evaluator with real replay

## Findings (verified 2026-10-25 on branch bot-00-chief/phase-6-integrity)

1. `src/pumpgrok/backtest/harness.py` scores candidates with `_score_candidate`
   and `_evaluate_holdout`: SHA-256 digests of seed, parameter-set hash and
   fold ids mapped to [0,1). No price, trade, fill or replay output feeds the
   score. Violates BT-05, BT-06 and the milestone rule against hollow
   implementations.
2. `src/pumpgrok/backtest/report.py` renders a manifest, holdout and trial
   counts, and zeroed fee and slippage totals. It carries no return, drawdown,
   Sharpe, win rate, trade count, exposure or turnover, although
   `src/pumpgrok/backtest/metrics.py` (08-03) already implements them.
3. The report prints `promotion_eligible: true` from the trial count alone,
   and `divergence: not-compared`. Eligibility is unsupported.
4. The data window is absent from the report. BT-06 requires it.
5. `--params` JSON reaches `run_search` as an opaque dict and never touches
   the replay. The parameter set is not connected to the engine.

## Correction contract (from the fix brief, binding on plans 08-08 to 08-10)

A. Each candidate parameter set is applied as validated settings overrides
   (pydantic, extra forbidden, against the real settings models). Fold
   windows (pre-holdout only) replay through the real engine and
   PaperAdapter. The tuning objective is net realized return in integer
   lamports over the fold. Ties break by candidate order. No digest, hash or
   random value acts as a score.
B. The winner replays once on the final 20 percent (HOLDOUT_FRACTION) with
   the same evaluator. Holdout never feeds selection. Split ids are named in
   the report.
C. Trial accounting is unchanged: every candidate recorded in the
   TrialLedger; above 20 trials ineligible; above 50 raises
   TooManyTrialsError.
D. The report carries: data window (first and last event timestamps, from
   events not the wall clock), holdout id and split ids, trial count, fee
   and slippage totals from real fills, and the BT-05 metrics (return, max
   drawdown from a running peak, Sharpe-style ratio with annualisation
   stated in code, win rate, trade count, exposure, turnover), each with
   inputs and assumptions. No expected-return, profit, pnl or will-earn
   wording. Zero-trade windows render trade-needing metrics as
   not-applicable, never zero-by-default. Byte-identical for identical
   inputs: sorted keys, no wall-clock values.
E. `promotion_eligible` is true only when trial count is at most 20 AND a
   paper comparison over the same window was supplied (optional
   `--paper-ledger PATH`) AND the D7 divergence check passed. Otherwise
   false with a stated reason. Default (no paper ledger): false, reason
   divergence not compared.
F. Divergence (PAP-02) compares backtest and paper metrics over the same
   window with the constants in `divergence.py`. A breach sets
   `promotion_eligible` false, prints DIVERGENCE BREACH on stderr, exits 1.
G. `tests/backtest/test_single_search_engine.py` is updated to the real
   evaluator. No assertion weakened; digest-pinning tests replaced by
   real-replay pins.
H. Every digest-as-score path removed. Remaining sha256 use is identity only
   (manifest, run id, hashes), never a score.

## Fixture facts relied on (read, not run)

- `tests/fixtures/replay/smoke/events.jsonl`: 5 ticks. Ticks 1-2 carry name,
  image_uri, created 30 min before, buyers 12 and 13, reserves 42.1e9 and
  42.35e9 lamports. Ticks 3-4 carry name, image_uri, created 20 min before,
  buyers 9 and 10, reserves 9.8e9 and 9.9e9 lamports. Tick 5 carries no name,
  image or buyer count. Curve completion is 85 SOL (85e9 lamports,
  `engine/monitor.py` CURVE_COMPLETION_LAMPORTS), so A-tick progress is about
  0.50 and B-tick progress about 0.12 against default max 0.40. Consequence:
  default FilterSettings admit the B ticks (metadata present, buyers at
  least 5, age far above 120 s, curve under 0.40) and refuse the A ticks on
  curve_too_full and tick 5 on no_metadata. Smoke produces real entries with
  desk defaults. Widening max_curve_progress admits the A ticks too.
- `tests/fixtures/replay/smoke-10m/events.jsonl`: 41 ticks over ten minutes
  (00:00:00 to 00:10:00 UTC) for two mints, tick-only shape (mint, S, T,
  complete, source). No tick carries name, image_uri, unique_buyers or
  created_ts_utc. Consequence: `tick_to_candidate` maps every tick to a
  candidate with no metadata, buyer count None, and age 0. `passes_filter`
  fails every smoke-10m tick closed: no_metadata under defaults, and even
  with require_metadata false the None buyer count hits data_unavailable and
  age 0 hits too_young unless min_age_seconds is also 0. No FilterSettings
  combination produces an entry on smoke-10m, because the None buyer count
  is unconditionally terminal. Smoke-10m is therefore the honest-zero case:
  zero trades, trade-needing metrics not-applicable. The evaluator and
  report must treat this as a correct outcome, not an error.
- `smoke-10m/llm.jsonl` holds one recorded outcome (verdict skip). The
  signal seat skips scoring when no record resolves (`_replay_signal`
  returns scoring skipped for replay_llm None), so window slices replayed
  without an llm.jsonl still run; entries never depend on the LLM outcome.
- Machinery reused: `supervisor/scheduler.py` run_once_replay (sniper places
  each BUY candidate through granted exec.place, exit seat sells on rules,
  PaperAdapter prices fills, FillRecorded rows land in the ledger),
  `replay/runner.py` ReplayTrade and ReplayResult, `execution/paper_adapter.py`,
  `backtest/results.py` FillDetail and SharedResult, `backtest/metrics.py`
  summarize, `backtest/split.py` holdout_split and walk_forward_folds,
  `backtest/trials.py` TrialLedger and limits, `backtest/manifest.py`,
  `backtest/divergence.py` D7 constants.

## Decisions and reasons

- D-C1: Params schema accepts `filter` (FilterSettings) and `exits`
  (ExitsSettings) override subsets only, each validated by its real model
  with extra forbidden. Scoring weights are rejected: `decide_replay`
  consults only `passes_filter`, so a scoring knob would be silently inert,
  which is the same hollow-knob failure this set removes. Unknown keys fail
  closed. Reason: every accepted knob must move the replay.
- D-C2: The evaluator materializes each fold and holdout window as a temp
  slice dataset (events.jsonl plus a recomputed manifest in the checked-in
  shape) and replays it with run_once_replay under an explicit per-eval
  ledger path. Reason: run_once_replay is the tested paper path (risk,
  PaperAdapter, exit rules, FillRecorded rows); slicing keeps tuning inside
  pre-holdout windows without touching holdout bytes. The default
  `var/replay/DATASET` ledger path must never be used for evals, or
  candidates would overwrite each other.
- D-C3: The tuning objective is net realized lamports: over a window, plus
  filled_lamports of SELL fills minus filled_lamports of BUY fills minus all
  venue fees and network costs from the FillRecorded rows; partial fills
  count at their filled fraction as recorded. Zero trades score 0 and still
  select by candidate order. Reason: integer money, no prices invented, no
  marks needed, defined on every window including the honest-zero case.
- D-C4: Best tracking uses strict greater-than in candidate order with no
  shuffle, so ties keep the earlier candidate. Reason: the contract demands
  ties break by candidate order; the old rng shuffle exists only to feed the
  digest and goes with it.
- D-C5: Zero-trade rendering: return, max drawdown, Sharpe-style ratio and
  win rate render as not-applicable; trade count, exposure and turnover
  render as 0 with stated assumptions (count of fills, biggest single
  commitment, sum of notionals). Reason: sums and counts are defined at
  zero; ratios against an empty window are not, and zero-by-default would
  read as measured flat performance.
- D-C6: `--paper-ledger PATH` points at a ledger sqlite file whose
  FillRecorded rows build the paper SharedResult over the same window via
  SharedResult.from_ledger_rows; window equality is enforced by
  SharedResult.compare before divergence.check. Reason: reuses the 08-04
  same-window machinery instead of inventing a second comparison.
- D-C7: Where CONTEXT G-03 calls the params file opaque, this set refines it
  to validated overrides; the file bytes remain the manifest hash input as
  G-03 requires. No other CONTEXT decision conflicts: D-01 to D-16 and G-01,
  G-02, G-04 to G-11 stand unchanged, including the 08-07 ownership of
  CHANGELOG work (D-15).

## Feasibility notes

- Nothing in the contract is infeasible with the current engine and
  fixtures. The one cost to state plainly: evaluation runs one full
  run_once_replay per candidate per fold plus one holdout replay, each
  spinning the ten-seat supervisor over a temp ledger. On the checked-in
  fixtures (5 and 41 events) this is small; large candidate counts over long
  recordings will be slow. The plans keep acceptance searches tiny and do
  not add parallelism or caching, which would risk determinism.
- 08-07 is unaffected in content: its acceptance commands stay exactly as
  written; only its frontmatter moves to wave 7 depending on 08-10, so the
  autonomy gate runs against the corrected evaluator.
