---
phase: 13-curve-truth
plan: 01
status: complete
commit: 8b68d56
---

# Phase 13 Plan 01: Datafeed foundation + recorder

## What shipped

- `DatafeedSettings`/`RecorderSettings` bounded defaults (watch_cap 32, rate 30/10s, state dirs), off by default.
- `src/pumpgrok/datafeed/`: integer-only `CurveTick`/`GapEvent` types, bounded `WatchSet` (pinned held mints, overflow counter), `MintBook`, `bridge.py` onto one `EventKind` catalog. One `gap` kind added to `events/models.py` with priority 1.
- `replay/live_recorder.py` seals datasets passing `load_dataset` (ticks in `events.jsonl`, gaps in `gaps.jsonl`); decreasing ticks raise; torn last line truncated on startup; tmp+os.replace writes. `import_data.py` preserves timestamps; `trim.py` cuts sealed windows.

## Verification

- `uv run pytest -q tests/datafeed/test_watchset.py tests/datafeed/test_mintbook.py tests/datafeed/test_bridge.py tests/events/test_models_v4_kinds.py tests/config/test_datafeed_settings.py tests/datafeed/test_events.py` — exit 0.
- `uv run pytest -q tests/replay/test_live_recorder.py tests/replay/test_live_recorder_manifest_strings.py` — exit 0.
- One-catalog grep count 1.

## Deviations

- Ticks are stored as `events.jsonl` (the name `load_dataset` requires) rather than `ticks.jsonl`; both files are listed in the manifest.
