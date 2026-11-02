# Phase 16 CONTEXT: Backtest v2 and autonomous evaluation

Milestone v4, Phase 16. Goal per ROADMAP: backtests report the full Metrics v2 set with undefined values as None, group fills into round trips, replay strategies through the SAME pipeline as live-paper on a FixtureClock, segment gapped datasets, grade evidence so only complete, long, gap-light data can count toward promotion, and run autonomously and idempotently on dataset or strategy edges. The CLI gains record, replay and strategy backtest verbs and the reports gain a per-strategy section.

Depends on: Phase 15 (strategy core, ParamSet identity R0, FEE2), Phase 13 (recorder), Phase 12 (DeterministicBus, SourceSupervisor), Phase 14 (14-07 for the cli/doctor chain), and the merged PRs 17 and 19 (shared valuation backtest/equity.py). Reuses without re-implementing: v1 MetricsReport and BT-05 tests (untouched), evaluate_window, fold_windows, run_search, TrialLedger limits 20 and 50, holdout-once, backtest/divergence.py D7, backtest/manifest.py dataset_digest, read_autonomy.

## Locked decisions (NON-NEGOTIABLE)

- D-01: Money integer lamports; ratios Decimal; undefined metrics are None, NEVER 0 or infinity.
- D-02: Clock-only time; the backtest runs on FixtureClock.
- D-03: Live stays refused (exit 3); no LLM client is constructible in a backtest run.
- D-04: hashes are identity only: run keys and dataset digests identify, they never rank or score a result.
- D-05: mypy --strict, ruff, no dead code, no swallowed errors, no placeholders, ASCII-only docs.
- D-06: One valuation function, backtest/equity.py (from PRs 17 and 19), shared by backtest, paper metrics and promotion, so they cannot diverge. MetricsReportV2 is new; v1 MetricsReport and BT-05 tests are untouched; no expected-return language.
- D-07: Metric formulas: total_return R = (E1-E0)/E0; annualized = (1+R)^(365/D)-1 (-1 if 1+R <= 0) with `annualization_valid=false` and annualized_return None when D < 7 days; round trip = fills grouped by (mint, opening PositionOpened seq), pnl_rt = sum of cash_delta (fees included); profit_factor = winners/|losers|, None with no loser, 0 with no winner; sortino = mean(r)/sqrt(mean(min(r,0)^2))*sqrt(365n/D), None if n < 2, D = 0 or downside deviation 0; max_drawdown over the full series including marks; time_weighted_exposure = integral of open cost basis over integral of equity; per-strategy breakdown with pnl_share.
- D-08: Strategy-aware replay uses the same StrategyRuntime, RiskEngine, PaperAdapter and a scratch sqlite ledger as live-paper; only the source (DatasetEventSource), clock (FixtureClock) and price source (DatasetCurveSource, same three methods as FixtureCurveSource) differ. Events replay through A2's DeterministicBus ordered by (ts, priority_rank, source_seq), NOT (ts, line). run_replay and run_once_replay are untouched. Coalescing stays off.
- D-09: DatasetCurveSource indexes ticks per mint and answers latest() with bisect (FixtureCurveSource._latest scans all ticks per call, replay/sources.py:58-75, quadratic over multi-day data); a perf-shaped test bounds comparisons. Fixture manifest values are strings (dict[str, str]).
- D-10: Look-ahead and survivorship controls: the context exposes only history at or before now; a fill prices at the latest tick known at decision plus seeded latency; ts_utc is knowledge time; importer never back-fills. evidence_grade = promotion only if coverage is all_launches or watchset, gap and overflow shares <= 5 percent each, span >= 7 days and >= 200 tokens (backtest.grade.*); traded_only, fixture and hand-authored data grade research or synthetic and NEVER count as promotion evidence.
- D-11: Gaps: gaps.jsonl and any tick gap over 120 s split a dataset into segments replayed independently; a position open at segment end is closed at its last price with gap_haircut_bps 500 (flatten_at_last) or its round trip is excluded and flagged (exclude_trade); no entries for post_gap_cooldown_s after a gap.
- D-12: BacktestScheduler reacts to DatasetSealed, StrategyVersionRegistered and ParamsProposed from the A1 catalog (no B-private events); run key = sha256(strategy_version_id, dataset_digest, params_hash, rng_stream) (rng_stream, never seed); a seen key is skipped; one run at a time and only when read_autonomy(store) is autonomous-paper; trial limits unchanged. Results persist deterministically under var/backtest/RUNID/ (result.json, report.md, trials.jsonl, manifest.json) plus append-only index.jsonl; BacktestEvidenceProvider.latest(strategy_id, param_set_hash) returns run id, HarnessResult, MetricsReport; BacktestCompleted carries evidence_grade and content hash to the promotion gate.
- D-13: `run --record NAME --duration S` replaces the exit-5 stub (cli/verbs_state.py:88) with a real record-only run on the 13-01 recorder; `replay trim`, `replay rebuild-ticks`, `replay import` rerun byte-identically; one parser function and one handler line per verb on the serial cli lane.

## Grey-area defaults

- G-01: Imports never fabricate evidence (ub stays absent; ledger import emits ticks only for traded mints, coverage=traded_only). Reason: survivorship.
- G-02: Per-strategy report section lives in journal-owned reporting code; its CHANGELOG lines move to 16-06 so each phase has one journal changelog PR.
- G-03: Non-legacy runs add a JournalNote `backtest-result`; legacy runs add none (hash safety).

## Phase boundary

In scope: src/pumpgrok/backtest/{metrics_v2,roundtrip,event_source,strategy_run,gaps,grading,scheduler,store,evidence}.py, cli verbs (parsing, dispatch, verbs_state, verbs_ops, backtest), reporting per-strategy section, fixture strat-gap. Out of scope: promotion thresholds, risk enforcement, live path, external historical data, procurement.

## Canonical references

src/pumpgrok/backtest/{evaluate,harness,report,divergence,manifest,results,trials}.py, src/pumpgrok/replay/{sources,fixtures,clock,runner}.py, src/pumpgrok/cli/{backtest,verbs_state,verbs_ops,dispatch,parsing}.py, src/pumpgrok/reporting/, research/B-strategies-backtest-data.md section 6, research/changes-applied.md items 11, 17, 26.

## Existing code insights

- The cli lane is serial: dispatch.py and parsing.py are edited in order 12-02, 16-04, 17-03, 18-02, 18-05.
- `run_replay` raises DataStale on any gap over STALE_GAP_S 120 and treats every events.jsonl line as a tick; segmenting is therefore new code, never a change to v1.
- Window days D comes from the series; v1 max_drawdown used post-fill points only.

## Specifics

- Hash rule this phase: smoke-10m and trading-smoke pairs EQUAL (16-06); new fixtures change no existing pin.
- Evidence provider verification uses the PR 18 `is_writer` plus verify_stored_content pattern (preflight symbols from 11-01).
- Acceptance includes real runs of the new verbs on fixtures, never dry-run flags.

## Deferred ideas

Walk-forward over live-recorded multi-week sets; fee-model sweep reports; a web UI for reports; external historical datasets.

## Ownership, receipt and hash rules (every plan of this phase)

- Branch `bot-0N-seat/v4-pPHASE-slug`, one PR per (phase, seat) (PR table below). Receipt `.receipts/bot-0N-seat/v4-pPHASE-slug.json` (task_id = slug, branch = the branch), tracked through the glob `!.receipts/bot-0*/v4-p*.json` from plan 11-01; no other seat edits .gitignore.
- `approved_by` is NEVER self-written and a seat never approves its own work. An agent reviewer (chief for risk-authored work, risk for other seats) reads the diff; human-gated receipts are committed WITHOUT approved_by and the owner adds `human:SomeRandmGuyy` in a batch at the ship checkpoint (after phases 12, 14, 17, 19).
- Seat purity: every path resolves to the plan seat via `resolve_owner(path, load_manifest(DEFAULT_MANIFEST))`; tests/** is risk except tests/desk/** (chief) and tests/engine/** (signal); execution/** sniper; cli/** risk; supervisor/** chief. A foreign-test failure gets a one-file companion plan by the owning seat, merged first.
- Replay hashes: smoke-10m `events.hash` is `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` (seq=2 events=41, verdict and rollover rows only). Trading `smoke` (5 events, seq 11) gave `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54` at HEAD 641927c; plan 11-01 pins it at v4-base; it moves only in plan 15-01. Run receipts in a fresh worktree without var/ledger.sqlite.
- Live stays refused: `uv run pumpgrok run --mode live --once; test $? -eq 3`; nothing arms it.
- Acceptance lines are real commands; exit 0 means success. The G-2 bypass family (collect-only, `--co`, `|| true`, stderr to /dev/null, `--force`, `--dry-run`, inline PUMPGROK_LIVE_ENABLE) never appears; `! cmd -rs | grep -q SKIPPED` proves no skips. Plans touching src also run make lint and make typecheck.


## Plans (7 planned; research/plans.json is the source)

Pull requests in merge order (numbers from research/pr-plan.md):

| PR | Branch | Plans | Approver | Checkpoint |
|----|--------|-------|----------|------------|
| PR-27 | `bot-02-risk/v4-p16-backtest-v2` | 16-01, 16-02, 16-03, 16-04 | bot-00-chief (agent) | CP17 |
| PR-28 | `bot-09-journal/v4-p16-reports-changelog` | 16-05, 16-06 | bot-02-risk (agent) | CP17 |
| PR-29 | `bot-00-chief/v4-p16-close` | 16-07 | bot-02-risk (agent) | CP17 |

### 16-01: Metrics v2 and round trips (one valuation function, undefined is None)

- seat bot-02-risk; wave 1; PR-27; depends_on: 15-01; requirements: BT-08, BT-09.
- files: src/pumpgrok/backtest/metrics_v2.py, src/pumpgrok/backtest/roundtrip.py, tests/backtest/test_metrics_v2.py, tests/backtest/test_roundtrip.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/backtest/test_metrics_v2.py tests/backtest/test_roundtrip.py tests/backtest/test_metrics.py
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 16-02: Strategy-aware replay: event source with bisect index, strategy run, gaps, grading

- seat bot-02-risk; wave 2; PR-27; depends_on: 12-03, 13-01, 15-01, 15-02, 15-03, 16-01; requirements: BT-10, BT-11, BT-12, BT-13.
- files: src/pumpgrok/backtest/event_source.py, src/pumpgrok/backtest/strategy_run.py, src/pumpgrok/backtest/gaps.py, src/pumpgrok/backtest/grading.py, tests/backtest/test_strategy_replay.py, tests/backtest/test_lookahead.py, tests/backtest/test_grading.py, tests/backtest/test_gaps.py, tests/backtest/test_dataset_curve_source_perf.py, tests/fixtures/replay/strat-gap/events.jsonl, tests/fixtures/replay/strat-gap/gaps.jsonl, tests/fixtures/replay/strat-gap/manifest.json.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/backtest/test_strategy_replay.py tests/backtest/test_lookahead.py tests/backtest/test_grading.py tests/backtest/test_gaps.py tests/backtest/test_dataset_curve_source_perf.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/replay/test_trading_smoke_pin.py
make lint
make typecheck
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 16-03: Backtest scheduler, result store and BacktestEvidenceProvider

- seat bot-02-risk; wave 3; PR-27; depends_on: 12-02, 16-02; requirements: BT-10, BT-11, BT-12, BT-13.
- files: src/pumpgrok/backtest/scheduler.py, src/pumpgrok/backtest/store.py, src/pumpgrok/backtest/evidence.py, tests/backtest/test_scheduler.py, tests/backtest/test_evidence_provider.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/backtest/test_scheduler.py tests/backtest/test_evidence_provider.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 16-04: CLI: run --record, live serve, replay trim, rebuild-ticks and import, backtest --strategy

- seat bot-02-risk; wave 4; PR-27; depends_on: 11-04, 13-01, 14-07, 15-06, 16-02, 16-03; requirements: REC-03, BT-12.
- files: src/pumpgrok/cli/parsing.py, src/pumpgrok/cli/dispatch.py, src/pumpgrok/cli/verbs_state.py, src/pumpgrok/cli/verbs_ops.py, src/pumpgrok/cli/backtest.py, tests/cli/test_record.py, tests/cli/test_strategy_backtest.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/cli
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 16-05: Per-strategy section in the daily and weekly reports

- seat bot-09-journal; wave 4; PR-28; depends_on: 11-01, 16-01, 16-02, 16-03; requirements: BT-09, OBS-07.
- files: src/pumpgrok/reporting/strategy_section.py, src/pumpgrok/reporting/weekly.py, tests/reporting/test_strategy_section.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/reporting
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
make lint
make typecheck
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 16-06: CHANGELOG entry for Phase 16 with both hash pairs

- seat bot-09-journal; wave 5; PR-28; depends_on: 16-01, 16-02, 16-03, 16-04, 16-05; order_after 15-07; requirements: PRC-03, PRC-06.
- files: CHANGELOG.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -qF 'Phase 16: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
grep -qF 'Phase 16: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 16: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 16: trading-smoke events.hash after: $p" CHANGELOG.md
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 16-07: Phase 16 close: STATE, verification record, progress table

- seat bot-00-chief; wave 6; PR-29; depends_on: 16-01, 16-02, 16-03, 16-04, 16-05, 16-06; order_after 15-08; requirements: PRC-06.
- files: .planning/STATE.md, .planning/ROADMAP.md, .planning/phases/16-backtest-v2-and-autonomous-evaluation/16-VERIFICATION.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -q 'Phase 16' .planning/STATE.md
./scripts/check.sh
test -f .planning/phases/16-backtest-v2-and-autonomous-evaluation/16-VERIFICATION.md
python3 ci/gates/check_ownership.py --validate-manifest
```
