# Phase 16 Summary: Backtest v2 and autonomous evaluation

**Phase:** 16 | **Date:** 2026-11-22 | **Branch:** bot-00-chief/phase-12-verification

## Delivered

Backtests report the full Metrics v2 set with undefined→None, group fills
into round trips, replay strategies through the live-paper pipeline on a
FixtureClock, segment gapped datasets with a 500 bps haircut flatten,
grade evidence so only recorded+complete+long+gap-light data promotes,
and run autonomously and idempotently on dataset/strategy edges. CLI
gains `run --record`, `live serve`, `replay trim|rebuild-ticks|import`,
and `backtest --strategy`. Nominal score 90.27% → these plans land the
ROADMAP Phase-16 criteria verbatim.

## Plans

| Plan | Scope | Commit |
|------|-------|--------|
| 16-01 | `metrics_v2.py` (None semantics, <7d annualization flag), `roundtrip.py` (entry→exit grouping, partial-exit fold, unclosed flag, per-strategy breakdown) | `0f560fe` |
| 16-02 | `event_source.py` (FixtureClock + per-mint bisect), `strategy_run.py` (legacy parity via evaluate_window; runtime replay otherwise), `gaps.py` (500bps policy), `grading.py` (recorded-only promotion) | `3fbc0fa` |
| 16-03 | `scheduler.py`/`store.py`/`evidence.py` (edge-triggered idempotence, autonomous-paper gate, deterministic store, promotion-gate provider) | `e2d6f93` |
| 16-04 | CLI `run --record`, `live serve`, `replay trim\|rebuild-ticks\|import`, `backtest --strategy`; `replay/normalize.py`, `replay/rebuild_ticks.py` | `e445d59` |
| 16-05 | `reporting/strategy_section.py` + ReportModel wiring; phase gates | `50818bf` + `9911e62` (gate lint/typecheck fixes) |

## Success criteria (13/13 runnable items pass)

- SC-1 `make lint/typecheck/test/audit`, `./scripts/check.sh`, paper `--once` replay smoke: all exit 0.
- SC-2 pytest metrics_v2+roundtrip+metrics; no expected-return language; no grid/product in engine/backtest.
- SC-3 lookahead + grading pytest pass: traded_only/fixture/hand-authored never promote; post-T extremes never change pre-T decisions.
- SC-4 gaps pytest pass: 500 bps haircut flatten, no entries in cooldown.
- SC-5 strategy replay + perf pytest pass: legacy parity at v1 net lamports; bisect within budget.
- SC-6 scheduler + evidence pytest pass: idempotence, autonomy gate, no-LLM, deterministic store, gate-readable evidence.
- SC-7 record + strategy-backtest pytest pass; record/replay verbs byte-identical reruns.
- SC-8 `backtest --fixture smoke-10m` twice + cmp: byte-identical.
- SC-9 reporting pytest pass: daily+weekly per-strategy section sums exactly to desk view.
- SC-10 no second search engine grep + single-search-engine pytest pass.
- SC-11 no contracts/ diff vs v4-base.
- SC-12 verify smoke-10m hash `b69c2959...2d` twice equal; replay pin tests pass; trading-smoke pin `bdcbe2d3...54` unchanged.
- SC-13 `run --mode live --once` exit 3 (paper-only invariant holds).

## Contract

Phase 17 consumes `BacktestEvidenceProvider` (`get(strategy_id, param_hash)`
→ persisted run record + `eligible` verdict). Promotion lifecycle itself
stays Phase 17. No live adapter/keys/funds code entered; live stays exit 3.

## Known stubs

None. All modules are fully wired; below-budget perf test is deterministic
(correctness + lookup count, no wall-clock).

## Journal-pending (CHANGELOG.md untouched — journal seat must add)

```
Phase 16: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
Phase 16: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
Phase 16: trading-smoke events.hash before: bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54
Phase 16: trading-smoke events.hash after: bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54
```

## Deviations

- Rule 2: fixture-shape (S/T) → CurveTick normalization (`replay/normalize.py`)
  so record/trim/import work on checked-in fixtures (existing trim/import
  validated CurveTick and failed on fixture shape).
- Rule 1: round-trip close rule — consecutive partial sells fold into one
  trip; closes on the last consecutive sell (so losing full exits close).
