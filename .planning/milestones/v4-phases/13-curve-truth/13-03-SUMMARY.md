---
phase: 13-curve-truth
plan: 03
status: complete
commit: a3da719
---

# Phase 13 Plan 03: Fee v2, factory, entry hook

## What shipped

- `execution/fees.py`: `FeeModelV2` beside v1 (builder fee when `use_builder`, ATA rent first-buy-only, capped priority fee); `fee_model_for` selector; all integer, floored.
- `PaperFeesSettings.model` widened to `Literal["v1","v2"]`, default v1.
- `execution/paper_factory.py` (only constructor path, imports paper_adapter only) and `execution/entry_hook.py` (buys-only allowlist + graduation gate; sells/flatten pass).
- Import-graph guard extended to both new modules.

## Verification

- `uv run pytest -q tests/execution/test_fee_model_v2.py tests/execution/test_paper_factory.py tests/execution/test_entry_gate_hook.py tests/safety/test_import_graph_no_live.py tests/characterization/execution` — exit 0.
- Default config still yields v1; every v1 number unchanged.
