---
phase: 06-integrity-closure
plan: 1
subsystem: integrity-money
tags: [INT-01, integer-money, lamports, export, engine]
requires: []
provides: [integer-money-boundary, money-types-guard]
affects: [06-03-export-units, 06-08-exit-peaks, characterization-tests, supervisor-exit-rules]
tech-stack:
  added: []
  patterns: [integer-lamports, scaled-int-prices, decimal-string-export, ast-static-guard]
key-files:
  created: [tests/integrity/test_money_types.py]
  modified:
    - src/pumpgrok/ledger/export.py
    - src/pumpgrok/engine/models.py
    - src/pumpgrok/engine/analyzer.py
    - src/pumpgrok/engine/exits.py
    - src/pumpgrok/engine/reputation.py
    - src/pumpgrok/engine/tune.py
    - src/pumpgrok/supervisor/exit_rules.py
    - src/pumpgrok/tools/onchain/deployer_history.py
decisions:
  - "PRICE_SCALE=10**9 for engine per-token prices (Decimal price * scale, ROUND_HALF_UP)"
  - "Renamed money fields honestly (realized_pnl_lamports, worst_loss_pct, return_pct, pnl_lamports); kept all other public names"
  - "Strict-int validator on CreatorRecord.realized_pnl_lamports forces old float books to rebuild from ledger (D-01, no dual-read shim)"
  - "Two one-line annotations outside files_modified fixed because task-2 acceptance requires a whole-tree-clean guard (scope note below)"
metrics:
  duration: ~1h
  completed: "2026-10-25"
  tasks: 2
  files: 9
status: complete
actuals:
  tokens: 52000
  tasks: 2
  commits: 2
commits:
  - 3f80fdf: task 1 integer-money conversion (8 source files)
  - e07fefc: task 2 guard test (tests/integrity/test_money_types.py)
plan_head_before: 71694cb
---

# Phase 06 Plan 01: Integer money at boundaries (INT-01) — Summary

JWT-style one-liner: engine/export money is now integer lamports, base units, and
`PRICE_SCALE`-scaled integer prices, with export rendering exact decimal strings
and a repo-wide AST guard rejecting float money annotations.

## What was built

**Task 1 — Integer money in ledger export and engine modules** (`3f80fdf`):

- `engine/models.py`: `Trade.sol_amount`/`token_amount` and `Holder.amount` are
  now `int` (lamports / base units); `ExitPosition.entry_price`/`peak_price`
  are `int` scaled by the new `PRICE_SCALE = 10**9`, `sol_spent` is int
  lamports, `token_amount` is int base units. All public names kept.
- `engine/exits.py`: the four `price: float` parameters (`pnl_pct`,
  `stop_loss_triggered`, `exit_signal`, `apply_price`) are now `price: int`.
  Ratio math is unchanged (int arithmetic, float percent results — ratios,
  not money). Threshold/timestamp params untouched.
- `engine/analyzer.py`: `parse_trade` converts provider SOL/token amounts to
  integer lamports/base units via `Decimal(str(v))` ROUND_HALF_UP; poisoned
  rows still degrade to skips (`ValueError` → `_safe_parse`). Volume
  accumulator is `int`; all metric math is scale-invariant. `parse_holder`
  amount is int; `share`/`enrich_token` analytics stay float (follow-up #9).
- `engine/reputation.py`: book persists `realized_pnl_lamports: int` with a
  strict before-validator that rejects non-ints (old float books quarantine
  to degraded and must `rebuild_from_ledger` — D-01, no dual-read shim).
  `worst_pnl_pct` → `worst_loss_pct: float`, `record_close` takes
  `pnl_lamports: int, return_pct: float`. All call sites are in-file.
- `engine/tune.py`: `Candidate.pnl_lamports: int | None`,
  `Outcome.kept_pnl/lost_pnl: int`, `score -> int`; `collect_pnl` parses
  trades-log `pnl_sol` (legacy SOL float or new exact decimal string) to
  integer lamports. Report formatting (`:+10.4f`) works on ints.
- `ledger/export.py`: `_sol_str`/`_price_str` render integer lamports and
  scaled prices as exact decimal strings via `Decimal` — no float division.
  `pnl_pct` stays a float ratio; `ts` stays epoch float (time, not money).
  `LAMPORTS_PER_SOL` constant kept: 06-03 owns INT-04 consolidation.

**Task 2 — Static money-types guard test** (`e07fefc`):
`tests/integrity/test_money_types.py` fails on any money-keyword (`lamport,
equity, fee, pnl, cost, price, size, balance`) annotation admitting `float`
(`float`, `X | float`, `Optional/Union[float, ...]`, quoted `"float"`) in
function args or assignments under `src/pumpgrok` (AST-based, prose-proof),
and pins export round-trips: string → `Decimal` → integer equals the ledger
input, including a negative-PnL close.

## Verification (executor-run, read-only)

- Task-1 verify on the six listed files: `grep ... exits 1` — zero matches.
- Task-2 verify on the whole tree: `grep ... exits 1` — zero matches.
- New-file syntax parsed OK. `uv run pytest`, `make`, linters were NOT run
  per wave instructions; the orchestrator runs all gates after merging.

Orchestrator acceptance commands:

```bash
git -C /root/src/repos/pumpgrok-wt/p6-01 log --oneline 71694cb..bot-00-chief/p6-01
grep -rnE "[a-z_]*(lamport|equity|fee|pnl|cost|price|size|balance)[a-z_]*\s*:\s*float" src/pumpgrok/ledger/export.py src/pumpgrok/engine/models.py src/pumpgrok/engine/analyzer.py src/pumpgrok/engine/exits.py src/pumpgrok/engine/reputation.py src/pumpgrok/engine/tune.py; test $? -eq 1
grep -rnE "\b[a-z_]*(lamport|equity|fee|pnl|cost|price|size|balance)[a-z_]*\s*:\s*float\b" src/ --include='*.py'; test $? -eq 1
uv run pytest -q tests/integrity/test_money_types.py
```

## Deviations from plan

### Scope note (not a deviation in behavior): two one-line annotations outside `files_modified`

Task 2 requires the whole tree clean, but `files_modified` omits two files
no Phase-6 plan owns. Each got the minimal annotation-only fix (zero runtime
effect — plain-function annotations are unenforced; the ToolOutput field is
`None` in practice today):

- `src/pumpgrok/supervisor/exit_rules.py:153` — `_sell(..., price: float)`
  → `price: int`.
- `src/pumpgrok/tools/onchain/deployer_history.py:39` —
  `worst_pnl_pct: float | None` → `Decimal | None` (ratio keeps its name).

### Auto-fixed issues

1. **[Rule 1 — dropped lines] `exits.pnl_pct` body lost in a range edit.**
   Re-added the `entry_price <= 0` guard and ratio return verbatim; verified
   the full function reads identically apart from the annotation + docstring.
2. **[Rule 1 — wrong anchor] an `exits.py` edit replaced
   `position: ExitPosition,` with a duplicate `price: int,`.** Restored and
   re-applied to the correct line; full-file read confirms one `position`,
   one `price` per signature.
3. **[Rule 2 — dropped imports] two edits ate `from __future__` /
   `from typing` lines.** Restored immediately; import blocks verified
   alphabetically ordered per ruff isort.

### Intentionally unchanged (plan-listed but out of safe scope)

- `Token.market_cap_sol`/`sol_in_curve`, `Holder.share`,
  `analyzer.enrich_token`: provider analytics floats whose producers
  (`monitor.py`, `pipeline.py` — 06-03 owns `pipeline.py`) no plan migrates.
- `TokenMetrics`/scores/weights/thresholds: ratios and counts, correctly float/int.

## Known fallout — follow-up required (no Phase-6 plan owns these files)

These break at merge-gate time by design (float money is gone); each needs
its owner to migrate to the integer boundary:

1. `tests/characterization/test_vendor_log.py:127-128,196-199,211-212` —
   asserts float `size_sol`/`entry_price`/`exit_price`/`pnl_sol`.
2. `tests/characterization/test_exits.py`, `test_watcher.py` — fractional
   `ExitPosition(...)` construction (pydantic rejects) and float price calls.
3. `tests/characterization/test_analyzer.py:168,191,253-262` — float `Trade`
   construction.
4. `tests/characterization/test_tune.py:44-45,57,62,67-70,108-141` —
   `Candidate(pnl_sol=...)`, float `Outcome`, float log fixtures.
5. `tests/characterization/test_reputation.py:40-103`,
   `tests/safety/test_reputation_degraded.py:232-233`,
   `tests/risk/test_reputation_durable.py`,
   `tests/characterization/test_vendor_state.py` — old `record_close`
   kwargs and `realized_pnl_sol`/`worst_pnl_pct` names.
6. `src/pumpgrok/supervisor/exit_rules.py:109-119` — `LedgerExitBook.sync`
   builds `ExitPosition` from `float(...)`; needs `Decimal`-to-`PRICE_SCALE`
   conversion (and `_price` float → int for mypy).
7. `src/pumpgrok/engine/watcher.py` — float quote passed to
   `apply_price(price: int)`; needs integer price sourcing to match.
8. `src/pumpgrok/engine/agents/auditor.py:79` — renders
   `trade.sol_amount` (now lamports) as `"sol"`.
9. `Token` SOL analytics + `monitor.py`/`pipeline.py` producers (see above).

## Threat flags

None — no new network endpoints, auth paths, file access, or schema changes
at trust boundaries. Persistence formats: export `trades.jsonl` value types
float→string (documented consumer: `pumpgrok scout pipeline --candidates`
matches on `tx_hash`, unaffected); reputation book JSON gains integer
`realized_pnl_lamports` (old float books quarantine by design).

## Self-Check: PASSED

- All 9 files exist; `git log` shows `3f80fdf` then `e07fefc` on
  `bot-00-chief/p6-01`; no unintended deletions (`git diff --diff-filter=D`
  empty); working tree clean except this SUMMARY (to be committed next).
