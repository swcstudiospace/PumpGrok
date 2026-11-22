# Phase 15 Plan 07: Phase closure — Summary

**Status: complete** (pending-journal only). All 15 Phase 15 success criteria
hold on the final tree; the evidence record is
`.planning/phases/15-strategy-framework/15-VERIFICATION.md`. This plan
changed no production code of its own; two tree-level gate fixes landed
alongside (recorded below as deviations).

## Commits

- `f330180` — 15-06 (live-data paper root + Intent router + exit ticket filter)
- `4743c56` — 15-06 gate lint/typecheck fixes (make lint/typecheck exit 0)
- Pending: this plan's docs + tree fixes (15-VERIFICATION.md, summaries,
  `tests/strategies/__init__.py`, `CandidateParams` extra-forbid restore)

## Gate results (final tree)

| Gate | Exit | Note |
|---|---|---|
| `make lint` | 0 | 1255 files formatted, all checks passed |
| `make typecheck` | 0 | no issues in 295 source files |
| `make test` | 0 | full fast suite green (after the two fixes below) |
| `make audit` | 0 | no known vulnerabilities |
| `./scripts/check.sh` | 0 | 35 skills, 10 agents, 530 markdown files ok |
| replay smoke | 0 | paper `--once --replay smoke`: `trades filled=2 not_filled=1` |
| SC 10 (15-06) | 0 | root/exit/readonly suites |
| SC 11 (15-06) | 0 | router suites, zero skipped |
| SC 12 import-graph + no-signing guards | 0 | 31 passed |
| SC 13 contracts | 0 | `git diff --name-only v4-base -- contracts` empty |
| SC 14 hash pairs | 0 | smoke-10m equal pair + trading-smoke pin pair in CHANGELOG (working tree) |
| SC 15 live refusal | 0 | `run --mode live --once` exits 3 |
| SC 2–9 regressions | 0 | upgrade, strategies, desk, datafeed, execution, config, backtest suites |

## Pending journal (journal seat, bot-09-journal)

- The four Phase 15 CHANGELOG lines (smoke-10m before/after, trading-smoke
  before/after) are present and grep-verified in the `CHANGELOG.md` working
  tree but **uncommitted**; the journal seat owns their commit. 15-07 did
  not edit or commit CHANGELOG.md. Nothing else is pending.

## Deviations (auto-fixed during closure)

1. **[Rule 3] Gate lint/typecheck were red at HEAD** (37 pre-existing lint
   findings across 15-01…15-05 files; mypy `--strict` on the registry
   module fallback). Fixed mechanically with `ruff check --fix`/`ruff
   format` plus manual E501/SIM/PLC0415 wraps; one tautological `or True`
   assertion in `tests/strategies/test_no_llm.py` dropped (the `hasattr`
   and `find_spec` asserts still carry that test). Commit `4743c56`.
2. **[Rule 3] `make test` collection collision**: `tests/strategies/test_registry.py`
   and `tests/core/test_registry.py` share a basename with no `__init__.py`
   in either dir. Added the empty `tests/strategies/__init__.py`, the repo's
   own convention (`tests/datafeed/__init__.py`), qualifying the strategies
   test modules. The SC 3 command naming `tests/strategies/test_registry.py`
   is unaffected.
3. **[Rule 1] 15-01 regression**: `CandidateParams` lost its
   `ConfigDict(extra="forbid")` — unknown top-level keys (e.g. `scoring`,
   `top_k`) were silently accepted, failing
   `test_unknown_top_level_key_raises_validation_error` and
   `test_param_set_hash_refuses_invalid_bytes[{"top_k": 10}]` on the final
   tree (verified failing at `82fb3b2`, i.e. before this plan's work). The
   docstring still promises extra-forbidden behavior. Restored the config;
   both tests and the upgrade/backtest suites pass again.
   `backtest/candidate.py` is 15-01-owned; the fix is in the owning file
   and is covered by the existing tests.
4. **[Rule 1] Two more pre-existing failures** (both verified failing at
   `82fb3b2`): the `code_digest` broad `except Exception` in
   `strategies/base.py` (15-02) tripped
   `test_no_plain_swallow` — narrowed to `(ImportError, OSError, TypeError)`;
   `test_live_disabled_overlays` still expected the pre-D-04 overlay set —
   updated to include `paper-event` (the profile every-overlay-disables-live
   proof still passes).

## Files

- `.planning/phases/15-strategy-framework/15-VERIFICATION.md` — verbatim gate evidence
- `.planning/phases/15-strategy-framework/15-07-SUMMARY.md` — this file
- `tests/strategies/__init__.py` — collection-collision fix
- `src/pumpgrok/backtest/candidate.py` — extra-forbid restore (deviation 3)
