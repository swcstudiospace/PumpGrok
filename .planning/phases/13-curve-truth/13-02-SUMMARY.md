---
phase: 13-curve-truth
plan: 02
status: complete
commit: 0a9d965
---

# Phase 13 Plan 02: LivePriceSource + graduation + marks

## What shipped

- `datafeed/price.py`: fail-closed `LivePriceSource` — None when disconnected or unverified; completed curve refuses entry; gap holds last good (stale flag); timeout marks zero via injected epochs.
- `datafeed/graduation.py`: entry-only refusal (`entry_refused`/`graduation_refusal_reason`).
- `datafeed/marks.py`: `MarksLoop` marks every held mint within 60s on the injected Clock; empty book means `scheduled=False`, `next_deadline()=None`.

## Verification

- `uv run pytest -q tests/datafeed/test_price_source.py tests/datafeed/test_graduation.py` — exit 0.
- `uv run pytest -q tests/datafeed/test_marks.py` — exit 0.
- No wall-time grep over `src/pumpgrok/datafeed/` — clean.
