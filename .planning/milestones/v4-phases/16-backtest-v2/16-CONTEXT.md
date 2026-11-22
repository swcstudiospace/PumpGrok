# Phase 16: Backtest v2 and autonomous evaluation — Context

**Phase:** 16 | **Name:** Backtest v2 and autonomous evaluation
**Goal (ROADMAP):** Backtests report the full Metrics v2 set with undefined values as None, group fills into round trips, replay strategies through the same pipeline as live-paper on a FixtureClock, segment gapped datasets, grade evidence so that only recorded, complete, long, gap-light data can count toward promotion, and run autonomously and idempotently on dataset or strategy edges. The CLI gains record, replay and strategy backtest verbs and the reports gain a per-strategy section.
**Depends on:** Phase 15 (strategy core and legacy parity); Phase 14 plan 14-07 (CLI wake-mode lane); Phase 13 plan 13-01 (recorder); Phases 11 and 12
**Requirements:** REC-03, BT-08, BT-09, BT-10, BT-11, BT-12, BT-13, OBS-07 (plus pass-through gates PRC-01, PRC-03, BT-06, BT-07, LIV-07 carried in Success Criteria)
**Deliverables (ROADMAP):** `backtest/metrics_v2.py`, `roundtrip.py`, `event_source.py`, `strategy_run.py`, `gaps.py`, `grading.py` (BT-08–BT-12); `backtest/scheduler.py`, `store.py`, `evidence.py` (BacktestEvidenceProvider) (BT-13); CLI verbs `run --record`, `live serve`, `replay trim|rebuild-ticks|import`, `backtest --strategy` in `src/pumpgrok/cli/` (REC-03); `reporting/strategy_section.py` (OBS-07); `CHANGELOG.md` Phase 16 entry with both hash pairs.

## Scope decisions (LOCKED — do not re-litigate)

- **D-01 Paper-only invariant.** No live adapter, keys, or funds code. `run --mode live` stays exit 3 throughout (SC-13 verify). No `sendTransaction`/signing path may enter `backtest/`, `replay/`, or `reporting/`.
- **D-02 Metrics v2 lives in a new module** `src/pumpgrok/backtest/metrics_v2.py`; existing `metrics.py:summarize`/`_sharpe_ratio`/`_step_returns` stays untouched as the v1 surface (plans 16-01/16-02 parallel-safe — disjoint files).
- **D-03 Undefined is None, never 0 or inf.** Annualization under 7 days returns `annualization_valid=False` (BT-08). No expected-return language anywhere (`grep -rniE 'expected (return|profit|pnl)|will earn'` must be empty — SC-2).
- **D-04 Strategy replay reuses the live-paper pipeline on `FixtureClock`.** No second search engine: `! grep -rnE 'grid|itertools\.product' src/pumpgrok/engine src/pumpgrok/backtest` (SC-10). Legacy parity bar: `legacy_screening` on smoke == v1 fills + net lamports.
- **D-05 Evidence grading refuses** `traded_only`, `fixture`, and `hand-authored` data as promotion evidence; only recorded, complete, long, gap-light data grades as promotion evidence. Look-ahead canary: extreme data after T never changes a decision at/before T (BT-10).
- **D-06 Gap handling:** position open at a gap is flattened with 500 bps haircut OR excluded+flagged; no entries during cooldown (BT-11).
- **D-07 Scheduler is autonomous-paper gated.** A run requires `read_autonomy` at `autonomous-paper`; no LLM client is constructible inside `backtest/scheduler.py`; repeated edge = no work (idempotent); results persist deterministically via `store.py`; `BacktestEvidenceProvider` (`evidence.py`) serves the promotion gate (BT-13).
- **D-08 CLI surface:** `run --record`, `live serve`, `replay trim|rebuild-ticks|import`, `backtest --strategy`. Record/replay verbs rerun byte-identically (REC-03, SC-7). The v3 `backtest --fixture smoke-10m` output stays byte-identical across runs (SC-8, BT-06).
- **D-09 Per-strategy report section** `reporting/strategy_section.py`: daily+weekly reports, parts sum to desk view (OBS-07, SC-9, frozen integer-lamports money).
- **D-10 No hash move.** Both pairs recorded EQUAL in CHANGELOG (PRC-03, SC-12): smoke-10m `events.hash` stays `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`; trading-smoke pin unchanged (fee v2 flip already happened in Phase 15).

## Deferred / out of scope

- Promotion lifecycle wiring (Phase 17 consumes `BacktestEvidenceProvider`; this phase only exposes it).
- Risk slices/kills, entry checks (Phase 17).
- Dormant live path (Phase 18). No amendment files touched.

## Success criteria (verbatim from ROADMAP Phase 16)

1. `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` each exit 0 and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 (PRC-01)
2. `uv run pytest -q tests/backtest/test_metrics_v2.py tests/backtest/test_roundtrip.py tests/backtest/test_metrics.py` exits 0 and `! grep -rniE 'expected (return|profit|pnl)|will earn' src/pumpgrok/backtest src/pumpgrok/reporting --include=*.py` exits 0; the formulas hold, undefined values are None, and annualization under 7 days returns annualization_valid=false (BT-08, BT-09)
3. `uv run pytest -q tests/backtest/test_lookahead.py tests/backtest/test_grading.py` exits 0; traded_only, fixture and hand-authored data never grade as promotion evidence and extreme data after time T never changes a decision at or before T (BT-10)
4. `uv run pytest -q tests/backtest/test_gaps.py` exits 0; a position open at a gap is flattened with the 500 bps haircut or excluded and flagged, with no entries during the cooldown (BT-11)
5. `uv run pytest -q tests/backtest/test_strategy_replay.py tests/backtest/test_dataset_curve_source_perf.py` exits 0; legacy_screening replayed on smoke matches the v1 fills and net lamports and the per-mint bisect index meets its perf-shaped test (BT-12)
6. `uv run pytest -q tests/backtest/test_scheduler.py tests/backtest/test_evidence_provider.py` exits 0; a repeated edge does no work, a run needs read_autonomy at autonomous-paper, no LLM client is constructible, results persist deterministically and the BacktestEvidenceProvider serves the promotion gate (BT-13)
7. `uv run pytest -q tests/cli/test_record.py tests/cli/test_strategy_backtest.py` exits 0; `run --record`, `replay trim|rebuild-ticks|import` rerun byte-identically (REC-03)
8. `uv run pumpgrok backtest --fixture smoke-10m > /tmp/bt-a.md && uv run pumpgrok backtest --fixture smoke-10m > /tmp/bt-b.md && cmp /tmp/bt-a.md /tmp/bt-b.md` exits 0; the v3 verb output is byte-identical across runs (BT-06 from v3, unchanged)
9. `uv run pytest -q tests/reporting/test_strategy_section.py` exits 0; daily and weekly reports carry a per-strategy section whose parts sum to the desk view (OBS-07)
10. `! grep -rnE 'grid|itertools\.product' src/pumpgrok/engine src/pumpgrok/backtest --include=*.py` exits 0 and `uv run pytest -q tests/backtest/test_single_search_engine.py` exits 0; no second search engine appears (BT-07 from v3, unchanged)
11. `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0` exits 0; no contract surface changed in this phase (BT-12)
12. `a=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); b=$(uv run pumpgrok verify --fixture smoke-10m | grep -oE '[0-9a-f]{64}' | head -n1); test -n "$a" && test "$a" = "$b" && test "$a" = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" && grep -qF "Phase 16: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d" CHANGELOG.md && grep -qF "Phase 16: smoke-10m events.hash after: $a" CHANGELOG.md` exits 0, `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` exits 0 and `p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 16: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 16: trading-smoke events.hash after: $p" CHANGELOG.md` exits 0; both pairs are recorded and equal, because this phase does not move either hash (PRC-03)
13. `uv run pumpgrok run --mode live --once; test $? -eq 3` exits 0; live stays refused (LIV-07)

**Checkpoint:** A recorded or imported dataset can be backtested per strategy, graded, and the result is persisted and published to the promotion gate as an event.

## Test strategy (phase-wide)

- Every new module lands with its `tests/backtest/test_<module>.py` (or `tests/cli/test_record.py`, `tests/reporting/test_strategy_section.py`) added in the SAME plan — no test-only or code-only plans.
- Determinism: rerun the same fixture twice and `cmp` outputs (SC-8 pattern) for every CLI verb; scheduler idempotence = second identical edge does zero work.
- Money stays integer lamports; ratios Decimal only; undefined metric = None.
- Rollback per plan: revert the plan's own commits only (each plan owns disjoint files); never touch `tests/fixtures/replay/pins/` (no re-pin — D-10); if a hash moves, stop and hand off to Main rather than re-pinning.
