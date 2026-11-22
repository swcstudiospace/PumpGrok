---
phase: 13-curve-truth
plan: 04
status: complete
commit: 473764d
---

# Phase 13 Plan 04: Token-first decode + price gate

## What shipped

- `curve_layout.py` decodes 49- and 166-byte token-first accounts (token fields precede SOL); bad discriminator/length raised as `CurveDecodeError`; `CurveState.token_mint` added (hex string, JSON-safe). `encode_curve_fixture` builds both sizes, 49-byte backward compatible.
- `pump_events.py` gains `EVENT_DECODE_STATUS = "ASSUMED"`, `EVENT_DECODE_REVIEWED_BY = None`, `decode_status()` helper.
- `rpc_curve_price_allowed`: replay/fixture/rest/pumpportal allowed, rpc refused while either status is ASSUMED, unknown refused.

## Verification

- `uv run pytest -q tests/tools/onchain/test_curve_layout.py tests/tools/onchain/test_pump_events.py tests/tools/onchain/test_price_gate.py` — exit 0.
- `uv run pytest -q tests/tools/onchain/test_event_decode_status.py tests/tools/onchain/test_probe_record.py` — exit 0.
- `uv run pytest -q tests/execution tests/cli/test_review_trade_prices.py tests/safety/test_blind_advisory.py` — exit 0 (status-agnostic).

## Deviations

- Real pump discriminator `17b7f83760d8ac60` accepted alongside the ASSUMED fixture marker so the probe's discriminator check stays reachable; drift fixes (desk fixture token-first, probe checks disc before decode) folded into the 13-05 commit `6a14fc1`.
