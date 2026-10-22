# Go-live runbook

The live gate and the human confirmation record. In this release every live start is refused: the gate lists nine preconditions and the last ones can never hold. This runbook documents the gate order, not a path to live trading.

## Quick start

```bash
pumpgrok run --mode live --once --replay tests/fixtures/replay/smoke
pumpgrok live confirm --by human:operator --notional-cap 1 --expires 2026-10-23T00:00:00Z
```

The first command exits 3 and prints one refusal line per unmet precondition, in R21 order. The second records a human live-gate confirmation bound to the config hash; it needs `PUMPGROK_CONFIRMATION_KEY` in the environment and never changes the effective mode.

## The nine preconditions (code ids, R21 order)

The gate evaluates `PRECONDITION_IDS` from `src/pumpgrok/execution/live/live_gate.py` in this order:

1. `mode_live` -- effective mode is live.
2. `live_enable_env` -- `PUMPGROK_LIVE_ENABLE` is set to 1.
3. `min_paper_days` -- at least 14 elapsed UTC days of source=paper ledger events.
4. `performance_thresholds` -- closed count, profit factor, and drawdown on paper rows within limits.
5. `wallet_allowlist` -- live wallet allowlist configured (not a setting in this release).
6. `notional_cap` -- live notional cap configured (not a setting in this release).
7. `confirmation_record` -- a fresh `var/live_confirmation.json` verifies against the config hash.
8. `adapter_registered` -- a registered live adapter exists (no live adapter ships in this release).
9. `no_active_stop` -- halt, kill switch, and breaker state all readable and clear (not readable in this release).

Preconditions 5, 6, 8, and 9 can never hold in this release, so the gate stays closed. Preconditions 1 and 2 keep the posture explicit: every overlay ships `[live] enabled = false`, and the environment flag defaults off.

## Rules that apply to go-live

- `live confirm` is human-only: `--by` must be `human:<name>`, and `--notional-cap` must satisfy 0 < cap <= 1.
- The confirmation record expires. A stale record fails precondition 7 even if everything else holds.
- Live trading never engages in this release. A green-looking subset of preconditions is still a refusal while any line stays unmet.
- Keep `[live] enabled = false` in every overlay. Flipping it without the R21 amendment changes nothing the gate reads.

## References

- Gate implementation: `src/pumpgrok/execution/live/live_gate.py`
- Overlays: `src/pumpgrok/config/overlays/`
- Key custody and live refusal: `SECURITY.md`
- Risk boundary: `docs/RISK_POLICY.md`
