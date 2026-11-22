# Phase 17 Plan 01: Strategy slice and kills Summary

**Phase:** 17-risk-hardening | **Plan:** 17-01 | **Wave:** 1
**Commit:** `38bb758` feat(17-01): strategy slice enforcement and strategy kills on existing R34 rows

## One-liner

Per-strategy exposure slices and ledger-backed strategy kills enforced on the existing 19 R34 rows with no risk-row shape change.

## What shipped

- `src/pumpgrok/risk/strategy_slice.py` (new): slice weights (`0.20` per strategy with `0.20` reserve), integer-lamport cap math, ledger-backed kill replay.
- `src/pumpgrok/config/strategy_slices.toml` (new): version-controlled slice weights.
- `src/pumpgrok/risk/engine/core.py`: slice check before trade evaluation; kill verdict on `kill_switch`, exits pass.
- `src/pumpgrok/risk/engine/steps.py` + `model.py`: slice/kill reason surfacing on existing rows.
- Tests: strategy slice, strategy kill (buy blocked / exit allowed / human-only clear / restart still blocked), step-row stability (19 rows, unchanged `risk_json` shape).

## Verification (at commit time)

- Targeted pytest suites passed at commit time (see git history).
- No contract surface changed; `STEP_IDS` length stays 19.

## Requirements

RSK-01, RSK-02, RSK-08, PRC-01.

## Notes

- Feeds into 17-02 (feed health gates the slice check) and 17-05 (event desk wiring).
