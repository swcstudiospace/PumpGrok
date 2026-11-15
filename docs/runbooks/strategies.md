# Strategies runbook

How the v4 strategy runtime runs in paper, what each strategy does, and what the owner still has to approve.

## Status: PENDING OWNER APPROVAL

Every strategy parameter in this runbook is PENDING OWNER APPROVAL. The values in `DEFAULTS` are starting proposals with a reason each (see `.planning/phases/15-strategy-framework-and-multi-strategy-paper/15-PLANS-INDEX.md`, "Parameter and fee proposals"). They are kept inside the bounds in `src/pumpgrok/config/upgrade_bounds.toml` and are not final pins. A strategy parameter changes only after the owner approves it or adjusts its bound.

## Strategies

| Id | Kind | Rule, as proposed |
|---|---|---|
| `legacy_screening` | Adapter over the existing replay decision path | Runs `run_once_replay`'s decision functions through the runtime. Writes no ticket refs and no strategy state. Fills equal `run_once_replay` on the same dataset. |
| `momentum_breakout` | Baseline | BUY when price is at least `breakout_pct` above the window high of the last `lookback_seconds`. SELL on stop loss, or when the position is at least `max_hold_seconds` old. |
| `new_launch_sniper` | Baseline | BUY a mint at most `max_age_seconds` old with at least `min_unique_buyers` buyers and curve progress at most `max_curve_progress`, once per mint. SELL at `take_profit_pct`. |
| `mean_reversion` | Baseline | BUY when price is at least `z_threshold` standard deviations below the mean of the last `window_seconds`. SELL at the mean, on stop loss, or at the hold cap. |

`legacy_screening` is the one strategy module outside the IntentRouter that reaches `exec.place`, for replay only. The exception, its reason and the replay runner allowlist are in `docs/strategies-replay-exception.md`. No production module may call its placement names.

The three baseline strategies keep their state in one `StrategyBook` per strategy (price tape, open positions, peaks, probation). `save_state` and `restore_state` write and read it through the `strategy_state` sidecar table. A row whose hash does not match is refused on read.

## Bounds and proposed starting values (PENDING OWNER APPROVAL)

| Strategy | Parameter | Proposed start | Bound [min, max] |
|---|---|---|---|
| momentum_breakout | lookback_seconds | 300 | [60, 1800] |
| momentum_breakout | breakout_pct | 20.0 | [1.0, 200.0] |
| momentum_breakout | max_hold_seconds | 900 | [60, 3600] |
| momentum_breakout | stop_loss_pct | 25.0 | [1.0, 100.0] |
| new_launch_sniper | max_age_seconds | 300 | [10, 900] |
| new_launch_sniper | min_unique_buyers | 5 | [1, 1000] |
| new_launch_sniper | max_curve_progress | 0.10 | [0.0, 1.0] |
| new_launch_sniper | take_profit_pct | 80.0 | [1.0, 1000.0] |
| mean_reversion | window_seconds | 600 | [60, 7200] |
| mean_reversion | z_threshold | 2.0 | [0.5, 5.0] |
| mean_reversion | max_hold_seconds | 900 | [60, 3600] |
| mean_reversion | stop_loss_pct | 15.0 | [1.0, 100.0] |

Open question for the owner: `new_launch_sniper.max_age_seconds` is the sniper's own rule. It is not `filter.min_age_seconds` (120). Confirm the interaction.

## Paper-event profile

Select with `PUMPGROK_PROFILE=paper-event`. The overlay is `src/pumpgrok/config/overlays/paper-event.toml`. It is paper with two wider risk limits:

- `risk.max_open_positions = 6`
- `risk.max_trades_per_day = 40`

Every other value is copied from `paper.toml`. `paper.toml` and `live.toml` are unchanged. The live overlay stays at 3 open positions and 20 trades per day.

## Fee model v2 (paper default)

Paper fees default to fee model v2 (`paper_fees.model = "v2"`). v1 is still accepted explicitly. v2 charges the ATA rent on the first filled buy of each mint. The live paper root reads that rent from RPC (`getMinimumBalanceForRentExemption(165)`). Replay keeps the offline pin, recorded with its epoch and source. The v2 terms and their values are PENDING OWNER APPROVAL (see the proposal table in the plans index).

## Router refusal below autonomous-paper

Strategy Intents reach `exec.place` only through `supervisor/intent_router.py`. Below the `autonomous-paper` level, read from the ledger by `read_autonomy`, the router:

- journals a refusal (`JournalNote`, reason `autonomy_manual_ticket`),
- returns `refused`,
- calls neither `RiskEngine.check` nor `exec.place`,
- approves nothing.

Other refusals (unknown strategy, slice exceeded, ticket allocation failed, approval mismatch) are journaled the same way. Each refusal is journaled once per (strategy, decision, reason).

## Live-data paper root

`supervisor/live_paper.py` builds the live-data paper root. It refuses to build unless the mode is `paper`. It has no default RPC endpoint: the caller passes one, and the owner chooses it at deployment (owner decision 4). Tests use a read-only double.

## Verifying a strategy change

```bash
uv run pytest -q tests/strategies tests/upgrade
uv run pytest -q tests/strategies/test_no_llm.py
uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
```

Live stays refused: `uv run pumpgrok run --mode live --once` exits 3.
