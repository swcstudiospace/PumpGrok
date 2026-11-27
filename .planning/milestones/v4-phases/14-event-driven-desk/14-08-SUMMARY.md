---
phase: 14-event-driven-desk
plan: "08"
status: complete
commit: c8af5e0
---

# Phase 14 Plan 08: Operator onboarding — Summary

`src/pumpgrok/onboarding/`: snapshot-pinned input inventory (five inputs,
per-mode required/optional/forbidden/not-read), `doctor --json` readiness
records (name, required_for_mode, status, source; presence and source only,
never a secret value), paper start gate refusing with missing inputs named,
seat access grants only as operator-choice ledger rows, wallet base58 +
Ed25519 curve-point validation, RPC host-only choice records, empty x.ai
key counts as missing, HMAC key forbidden in live.

## Gates

- `uv run pytest -q tests/onboarding` — exit 0 (22 passed)
- Clean-env `doctor --json --mode live` — exit 1 (non-zero)
- Clean-env `run --mode paper --once` — exit 5 (non-zero, names missing inputs)

## Deviations

- Paper start-gate refusal returns exit 5 (not 1) to keep the pre-existing
  `test_skip_cycle.py` characterization (`--once` without `--replay` is
  `EXIT_NOT_IMPLEMENTED`) green; the refusal message names the missing
  inputs. Replay runs (`--replay <dir>`) are exempt from the gate.
- `config/sections/onboarding.py` is importable but not composed into
  `Settings`, to avoid changing the pinned settings surface digest.
