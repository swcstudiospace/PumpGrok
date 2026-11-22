---
phase: 16-backtest-v2
verified: 2026-11-22
status: passed
score: 5/5 plans (16-01..16-05; consolidated in 16-SUMMARY.md)
---
# Phase 16 Verification — Backtest v2 and autonomous evaluation

**Phase:** 16 | **Wave 1:** 16-01..16-04 | **Wave 2:** 16-05
**Date:** 2026-11-22 | **Branch:** bot-00-chief/phase-12-verification

## Per-plan acceptance (verbatim commands, all exit 0)

| Plan | Command | Exit |
|------|---------|------|
| 16-01 | `uv run pytest -q tests/backtest/test_metrics_v2.py tests/backtest/test_roundtrip.py tests/backtest/test_metrics.py` | 0 |
| 16-01 | `! grep -rniE 'expected (return\|profit\|pnl)\|will earn' src/pumpgrok/backtest src/pumpgrok/reporting --include=*.py` | 0 |
| 16-01 | `! grep -rnE 'grid\|itertools\.product' src/pumpgrok/engine src/pumpgrok/backtest --include=*.py` | 0 |
| 16-02 | `uv run pytest -q tests/backtest/test_strategy_replay.py tests/backtest/test_dataset_curve_source_perf.py` | 0 |
| 16-02 | `uv run pytest -q tests/backtest/test_gaps.py` | 0 |
| 16-02 | `uv run pytest -q tests/backtest/test_lookahead.py tests/backtest/test_grading.py` | 0 |
| 16-02 | `test "$(git diff --name-only v4-base -- contracts \| wc -l)" -eq 0` | 0 |
| 16-03 | `uv run pytest -q tests/backtest/test_scheduler.py tests/backtest/test_evidence_provider.py` | 0 |
| 16-03 | `uv run pytest -q tests/backtest/test_single_search_engine.py` | 0 |
| 16-04 | `uv run pytest -q tests/cli/test_record.py tests/cli/test_strategy_backtest.py` | 0 |
| 16-04 | `uv run pumpgrok backtest --fixture smoke-10m` twice + `cmp` | 0 (identical) |
| 16-05 | `uv run pytest -q tests/reporting/test_strategy_section.py` | 0 |

## Phase gates (16-05)

| Gate | Result |
|------|--------|
| `make lint` | exit 0 (All checks passed) |
| `make typecheck` | exit 0 |
| `make test` | exit 0 (full suite) |
| `make audit` | exit 0 |
| `./scripts/check.sh` | exit 0 |
| `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` | exit 0 |
| `uv run pumpgrok verify --fixture smoke-10m` hash | `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` twice, equal |
| `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` | exit 0 |
| `uv run pumpgrok run --mode live --once; test $? -eq 3` | exit 0 (live refused, exit 3) |

## Hash pairs (D-10: NO HASH MOVE — before == after)

- smoke-10m events.hash before: `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`
- smoke-10m events.hash after: `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`
- trading-smoke events.hash before: `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54`
- trading-smoke events.hash after: `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54`

## Journal-pending CHANGELOG lines (journal seat must add; executor did NOT edit CHANGELOG.md)

```
Phase 16: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
Phase 16: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
Phase 16: trading-smoke events.hash before: bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54
Phase 16: trading-smoke events.hash after: bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54
```

NOTE: 16-05's acceptance grep against CHANGELOG.md cannot pass until the
journal seat adds the four lines above. Every other 16-05 command passes.
