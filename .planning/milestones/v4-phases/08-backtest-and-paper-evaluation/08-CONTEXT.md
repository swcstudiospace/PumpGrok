# Phase 8 CONTEXT: Backtest and paper evaluation

Branch: `bot-00-chief/phase-6-integrity`. Replay hash to preserve as BEFORE:
`b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`
(smoke-10m events.hash, Phase 6 before equals after, Phase 7 after equals same).
Phase 8 CHANGES replay output on purpose (ROADMAP criterion 12): the result
schema gains per-fill fields, so the AFTER hash will differ. The orchestrator
measures the AFTER hash at the gate; no executor runs `pumpgrok verify`.

## Locked decisions (non-negotiable, from the brief)

- D-01: Money as integers in base units (lamports, token units). Decimal only
  for ratios. No float money in new code.
- D-02: ULIDs from `src/pumpgrok/core/ids.py`. All time through the Clock
  (`src/pumpgrok/replay/clock.py`); no direct `asyncio.sleep` or `time.time`
  in new code.
- D-03: Paper only. No code path may place a live order. Live stays refused
  with exit 3 (ROADMAP criterion 13).
- D-04: Backtest datasets are self-recorded only: the desk's own recorded
  fixtures (`tests/fixtures/replay/smoke`, `tests/fixtures/replay/smoke-10m`)
  or the desk's own paper ledger. No external dataset import, no network
  fetch in the backtest path.
- D-05: The holdout is the final 20 percent of the time window (BT-03).
  No tuning step may read it. The report names the split identifiers.
- D-06: Trial accounting (BT-04): above 20 trials flags the result ineligible
  for promotion; above 50 trials is rejected with a typed error.
- D-07: Annualisation must be stated in code (BT-05). Metrics must not contain
  expected-return, expected-profit, pnl-forecast or will-earn language.
- D-08: The result schema changes replay output (ROADMAP Phase 8 criterion 12).
  Record the BEFORE hash `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`
  and the AFTER hash in CHANGELOG.md. The AFTER hash is measured by the
  orchestrator at the gate, not by an executor, so plans must not require an
  executor to run `pumpgrok verify`.
- D-09: The backtest report must be byte-identical for identical inputs
  (ROADMAP criterion 7). Use sorted keys, fixed float-free formatting, and no
  timestamps from the wall clock.
- D-10: No second search engine: after BT-07 the harness is the only search
  entry point. `src/pumpgrok/engine/tune.py` is removed.
- D-11: Style: mypy --strict on `src/pumpgrok`, ruff, no dead code, no
  swallowed errors, no TODO or placeholder text, ASCII-only new docs.
- D-12: Divergence defaults for PAP-02 are a 2 percentage point absolute
  return gap and a 0.5 Sharpe gap. Authority: `.planning/PROJECT.md` V3-4
  (owner approval 2026-10-25). Grep-confirmed 2026-10-25: `docs/RISK_POLICY.md`
  and `docs/SAFETY_INVARIANTS.md` contain no numeric divergence thresholds,
  so the new `src/pumpgrok/backtest/divergence.py` module owns the named
  constants and cites PROJECT.md V3-4.
- D-13: PAP-03 runs autonomous paper end to end on the recorded `smoke` and
  `smoke-10m` datasets at the human-set autonomous-paper level. The level is
  configured with `pumpgrok state autonomy autonomous-paper --by human:NAME`
  and enforced through `src/pumpgrok/ledger/autonomy.py` (`read_autonomy`,
  default `manual-ticket`); manual-ticket never runs an upgrade.
- D-14: `tests/safety/test_manual_ticket_no_upgrade.py` is named by PAP-03 and
  does not exist yet (confirmed by directory listing 2026-10-25); plan 08-07
  creates it. `tests/backtest/` and `tests/e2e/` do not exist yet; plans
  08-01 and 08-07 create them.
- D-15: CHANGELOG.md is owned by the last plan only (08-07). Plans in the same
  wave have disjoint `files_modified`.
- D-16: Format deviation from Phase 7 plans: this brief forbids angle brackets
  in every file written, so Phase 8 plans use markdown task sections
  (`## Task N`, `Files`, `Read first`, `Action`, `Acceptance`, `Verify`)
  instead of Phase 7 XML tags. Field names and frontmatter keys are unchanged.

## Grey-area defaults (chosen; one-line reason each)

- G-01: `backtest` writes its Markdown report to stdout (criterion 7 redirects
  stdout for the byte-identity `cmp`); reason: matches the existing
  `verify` events.hash stdout precedent and needs no new output flag.
- G-02: Datasets are addressed with `--fixture NAME` resolving under
  `tests/fixtures/replay/`; reason: matches the `verify --fixture smoke-10m`
  precedent executors already know.
- G-03: The parameter set arrives as `--params PATH` JSON; absent means desk
  defaults; the file bytes are content-hashed into the manifest; reason: BT-01
  needs a parameter-set hash, and a file gives a stable hash input.
- G-04: Code version is the git HEAD sha, `UNKNOWN-DEV` only when git is
  unavailable; reason: BT-01 needs a code version and HEAD is the identity
  the repo already uses for receipts.
- G-05: Walk-forward uses expanding-window folds over the pre-holdout region
  with split ids `DATASET-train-N` and `DATASET-holdout`; reason: simplest fold
  scheme that satisfies BT-03 tuning folds plus named split identifiers.
- G-06: The trial ledger is JSONL at `var/backtest/RUNID/trials.jsonl`;
  reason: mirrors the replay ledger containment precedent
  (`var/replay/DATASET/ledger.sqlite`).
- G-07: Annualisation is a named constant `ANNUALIZATION_DAYS_PER_YEAR = 365`
  with a code comment stating the 24/7 market assumption; reason: BT-05 needs
  annualisation stated in code and crypto has no close days.
- G-08: A divergence breach sets `promotion_eligible: false` in the report,
  prints `DIVERGENCE BREACH` on stderr and exits 1; reason: exit 1 is the
  existing generic failure code and no new exit code is approved.
- G-09: `src/pumpgrok/engine/tune.py` is deleted entirely (not slimmed) and
  `tests/characterization/test_tune.py` goes with it; reason: criterion 8
  greps for `grid` and `itertools.product`, and kept helpers would drift back
  into a second engine.
- G-10: Per-fill detail extends the replay result payload written to the
  replay ledger (same event types, added integer fields), and the shared model
  in `backtest/results.py` wraps it; reason: criterion 12 already expects the
  replay hash to change, so the schema change lands where the hash records it.
- G-11: The no-live-path guard for criterion 13 is an AST test in
  `tests/safety/`; reason: matches the existing static-guard precedent
  (`tests/safety/test_static_guards.py`) and runs offline.

## Explicit scope boundary

In scope: `src/pumpgrok/backtest/` package (manifest, split, trials, metrics,
results, harness, report, divergence), the `backtest` CLI verb, per-fill
result fields in the replay path, removal of `engine/tune.py` and its
characterization pin, `tests/backtest/`, `tests/e2e/`,
`tests/safety/test_manual_ticket_no_upgrade.py`, the import-graph guard test,
and the Phase 8 CHANGELOG lines.

Out of scope: any live adapter or signing code (REQUIREMENTS LIV family,
Phase 10); paid RPC procurement; external datasets or network fetch;
new signal families or alpha research (PROJECT.md Out of Scope);
the constitution amendment and promotion gate (UPG family, Phase 9);
`STATE.md` and `ROADMAP.md` edits (orchestrator-owned);
`pumpgrok verify` runs by executors (orchestrator gate, D-08).

## Verified evidence (read 2026-10-25 on this branch)

- Roadmap: `.planning/ROADMAP.md` lines 98-134, 13 success criteria, 11 deliverable
  lines, requirements BT-01..BT-07 and PAP-01..PAP-03.
- Requirements: `.planning/REQUIREMENTS.md` BT and PAP entries plus the
  self-recorded-only out-of-scope row.
- Tune: `src/pumpgrok/engine/tune.py` holds `simplex`, `grid_lines` and an
  `itertools.product` grid; only `tests/characterization/test_tune.py`
  imports it; `src/pumpgrok/engine/__init__.py` mentions tune in its docstring
  only.
- Replay: `src/pumpgrok/replay/runner.py` defines `ReplayTrade` (side, mint,
  outcome, reason, rule) and `ReplayResult`; per-fill price, fee, latency and
  filled-fraction fields are absent.
- Execution: `src/pumpgrok/core/adapter.py` `Fill` carries
  `filled_lamports`, `filled_units`, `filled_fraction`, `price_avg`,
  `realised_slippage_bps`, `venue_fee_lamports`, `network_cost_lamports`,
  `route`, `ledger_seq`; `src/pumpgrok/execution/fees.py` (venue 100 bps,
  base 5000 lamports) and `src/pumpgrok/execution/latency.py` (seeded draws)
  already exist.
- CLI: `src/pumpgrok/cli.py` has verbs `run`, `doctor`, `audit`, `verify`,
  `report`, `paper`, `state`, `killswitch`, `ticket`, scout/risk/chief/rug/
  journal/audit orchestration verbs and `live confirm`; no `backtest` verb.
- Ids and time: `src/pumpgrok/core/ids.py` (ULID, `IdFactory`, approval ids)
  and `src/pumpgrok/replay/clock.py` (`Clock`, `WallClock`, `FixtureClock`;
  sole `time`/`asyncio.sleep` allowlist).
- Autonomy: `pumpgrok state autonomy manual-ticket|autonomous-paper --by`
  (`src/pumpgrok/cli.py`, `state_autonomy`); policy read from ledger
  `ConfigChanged` rows in `src/pumpgrok/ledger/autonomy.py`, default
  `manual-ticket`.
- Fixtures: `tests/fixtures/replay/smoke/` and `tests/fixtures/replay/smoke-10m/`
  exist with `manifest.json` digests; `tests/backtest/` and `tests/e2e/` do not.
- Safety: `tests/safety/test_manual_ticket_no_upgrade.py` does not exist.
- Changelog: `CHANGELOG.md` head holds the Phase 7 entry with
  `Phase 7: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`
  and the Phase 6 before line with the same hash.

## Cross-plan interface contracts (wave-1 plans code to these)

Wave-2 and wave-3 plans import these names; do not rename them without
updating every consumer plan in the same change.

- `src/pumpgrok/backtest/manifest.py`: `RUN_ID_VERSION: str`,
  `def dataset_digest(dataset_dir: PATH) -> str` (sha256 over every file in
  the directory, sorted names, concatenated per-file digests),
  `def build_manifest(dataset: str, seed: int, filter_settings_hash: str,
  param_set_hash: str, code_version: str) -> RunManifest`,
  `RunManifest` frozen model with `run_id: str` derived from the canonical
  JSON of the manifest.
- `src/pumpgrok/backtest/split.py`: `HOLDOUT_FRACTION = 0.20`,
  `def holdout_split(stamps: SEQUENCE, dataset: str) -> HoldoutSplit` with
  `train_ids: tuple[str, ...]`, `holdout_id: str` (`DATASET-holdout`),
  `train_end_ts: float`, `holdout_start_ts: float`;
  `def walk_forward_folds(stamps: SEQUENCE, dataset: str,
  n_folds: int) -> tuple` of expanding-window `(train, test)` id pairs over
  the pre-holdout region only.
- `src/pumpgrok/backtest/trials.py`: `MAX_ELIGIBLE_TRIALS = 20`,
  `MAX_ALLOWED_TRIALS = 50`, `class TooManyTrialsError(PumpgrokError)`,
  `class TrialLedger` with `record_trial(params_hash: str) -> TrialVerdict`
  where the verdict carries `eligible_for_promotion: bool`; recording trial 51
  raises `TooManyTrialsError`.
- `src/pumpgrok/backtest/metrics.py`: `ANNUALIZATION_DAYS_PER_YEAR = 365`,
  `def summarize(fills: SEQUENCE, ctx: MetricsContext) -> MetricsReport`
  with return, max drawdown from a running peak, Sharpe-style ratio,
  win rate, trade count, exposure and turnover; every field documents inputs
  and assumptions in its docstring; no forecast language anywhere.
- `src/pumpgrok/backtest/results.py` (plan 08-04): `class FillDetail`
  frozen model (price, venue fee, network cost, latency, filled fraction,
  outcome; money integers, latency Decimal seconds), `class SharedResult`
  built from the same `Fill` model for backtest fills and paper ledger fills
  over the same window.
- `src/pumpgrok/backtest/harness.py` (plan 08-05):
  `def run_search(dataset: str, space: PARAMSPACE, n_trials: int,
  seed: int) -> HarnessResult`, the only search entry point; reads the
  pre-holdout region only and evaluates the final pick on the holdout once.
- `src/pumpgrok/backtest/report.py` (plan 08-06):
  `def render(report: BacktestReport) -> str` deterministic Markdown
  (sorted keys, fixed formatting, no wall-clock timestamps).
- `src/pumpgrok/backtest/divergence.py` (plan 08-06):
  `ABSOLUTE_RETURN_GAP_PP = 2.0`, `SHARPE_GAP = 0.5`,
  `def check(backtest: WINDOW, paper: WINDOW) -> DivergenceVerdict`
  with `blocks_promotion: bool`.

## Coverage: criterion to plan to task

| # | Criterion | Plan | Task |
|---|-----------|------|------|
| 1 | lint, typecheck, test, check.sh, replay smoke exit 0 | none | Orchestrator gates only (no task runs the suite) |
| 2 | test_run_manifest green; manifest holds dataset digest, seed, FilterSettings hash, param-set hash, code version; one changed byte changes run id | 08-01 | Build run manifest; acceptance is the exact pytest command |
| 3 | test_replay_result_fields green; per-fill price, venue fee, network cost, latency, filled fraction, outcome | 08-04 | Shared result model plus replay per-fill fields; acceptance is the exact pytest command |
| 4 | test_holdout_split green; final 20 percent holdout; no tuning reads it; report names split ids | 08-02 | Holdout split plus walk-forward folds; acceptance is the exact pytest command |
| 5 | test_trial_limits green; above 20 ineligible; above 50 typed rejection | 08-02 | Trial ledger; acceptance is the exact pytest command |
| 6 | test_metrics green; annualiz stated in code; no expected-return language in backtest or reporting | 08-03 | Bounded metrics; three-part acceptance copied exactly |
| 7 | backtest twice byte-identical; report names holdout, trial, slippage, fees | 08-06 | backtest verb plus deterministic report; both commands copied exactly |
| 8 | no grid or itertools.product in engine or backtest; single search engine test green | 08-05 | Holdout-aware harness plus tune removal; both commands copied exactly |
| 9 | test_shared_result_schema green; one result model, same-window compare | 08-04 | Shared result model; acceptance is the exact pytest command |
| 10 | test_divergence green; 2pp return gap and 0.5 Sharpe gap alert and block | 08-06 | Divergence check on D7 defaults; acceptance is the exact pytest command |
| 11 | autonomous paper e2e plus manual-ticket no-upgrade green | 08-07 | Recorded-dataset autonomy verification; acceptance is the exact pytest command |
| 12 | verify hash stable across runs; CHANGELOG before and after lines | 08-07 (before line only) | CHANGELOG before line plus live-refusal guard; AFTER line is orchestrator-measured at the gate (D-08) |
| 13 | run --mode live exits 3 | 08-07 | Existing refusal plus import-graph guard; acceptance is the exact command |

## Plan list

- 08-01 (wave 1): backtest package plus run manifest, BT-01, criterion 2.
- 08-02 (wave 1): holdout split plus trial ledger, BT-03 and BT-04, criteria 4 and 5.
- 08-03 (wave 1): bounded metrics, BT-05, criterion 6.
- 08-04 (wave 2, dep 08-01): shared result model plus replay per-fill fields, BT-02 and PAP-01, criteria 3 and 9.
- 08-05 (wave 2, dep 08-01, 08-02, 08-03): holdout-aware harness plus tune removal, BT-07, criterion 8.
- 08-06 (wave 3, dep 08-04, 08-05): backtest verb, deterministic report, divergence check, BT-06 and PAP-02, criteria 7 and 10.
- 08-07 (wave 4, dep 08-06): autonomy e2e, manual-ticket guard, live-refusal guard, CHANGELOG before line, PAP-03, criteria 11, 12 (partial) and 13.
