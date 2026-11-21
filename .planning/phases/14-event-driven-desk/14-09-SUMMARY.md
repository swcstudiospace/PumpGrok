---
phase: 14-event-driven-desk
plan: "09"
status: complete
---

# Phase 14 Plan 09: Phase close — Summary

CHANGELOG.md Phase 14 entry records equal before/after pairs
smoke-10m b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
and trading-smoke bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54,
plus events-smoke-10m golden 888e1849dca763a0ecbc088e873969f5c8da7fee63031bca7310f58203f2204c
and events-soak-3d golden c08ad0ddddfd44de00590c9fc2f5f80b6852aa428e3d05ec1f4d26d8a7194e70.
`scripts/probe_curve_layout.py` was deleted with all references removed
(two probe test files, the probe half of the doc-commands offline test,
`docs/CURVE_LAYOUT_PROBE.md`, and stale mentions). Contracts untouched.

## Gates

- `uv run pytest -q tests/replay/test_replay_hash_pin.py tests/replay/test_trading_smoke_pin.py` — exit 0
- `uv run pumpgrok run --mode live --once; test $? -eq 3` — exit 0
- `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` — exit 0
- `test ! -e scripts/probe_curve_layout.py` — exit 0
- `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0` — exit 0
- `make lint` — exit 0; `make typecheck` — exit 0
- `./scripts/check.sh` — exit 0
- `make test` — running (1500 s window)
