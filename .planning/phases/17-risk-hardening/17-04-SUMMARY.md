# Phase 17 Plan 04: Promotion stages and thresholds Summary

**Phase:** 17-risk-hardening | **Plan:** 17-04 | **Wave:** 2
**Commit:** `2c958e9` feat(17-04): promotion stages, fail-closed thresholds, gate reuse, demotion and writer discipline

## One-liner

Ledger-row promotion stages (BACKTEST → PAPER → LIVE_ELIGIBLE) with fail-closed TOML thresholds at LiveGate floors, upgrade-gate reuse, demotion, and writer discipline.

## What shipped

- `src/pumpgrok/promotion/stages.py` (new): stage rows + decision log.
- `src/pumpgrok/promotion/thresholds.py` + `src/pumpgrok/config/promotion_thresholds.toml` (new): thresholds at or stricter than LiveGate floors; looser-than-floor files refuse to load.
- `src/pumpgrok/promotion/evaluator.py` (new): evidence-driven stage evaluation reusing `evaluate_candidate` (bounds, trial count, holdout, divergence) with the paper parameter; promotion never calls a search function.
- `src/pumpgrok/promotion/demotion.py` (new): evidence-based demotion.
- `src/pumpgrok/cli/promotion_verb.py` (new) + dispatch/parsing wiring.
- `src/pumpgrok/upgrade/gate.py`: paper-mode reuse of the upgrade gate.
- Tests: stages, thresholds, gate reuse, demotion.

## Verification (at commit time)

- Targeted pytest suites passed at commit time (see git history).

## Requirements

PRM-01, PRM-02, PRM-03, PRM-04, PRM-06, PRC-01.
