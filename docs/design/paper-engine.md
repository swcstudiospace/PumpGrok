# Paper Engine, Ledger, Replay, Risk, Supervisor and Live Gate Design

Tracker: SPE-17998 https://linear.app/swcstudio/issue/SPE-17998/n4-paper-engine-ledger-replay-riskbreakers-supervisor-live-gate-design | Notion https://app.notion.com/p/3ffbc1a0c7ae81fd8a30fb490682c0c2?pvs=204

Node n4 of ultrathink graph ut-mvgfr96y-be17fc96. Steps SPE-18025 (extend-vs-build), SPE-18024 (PaperAdapter), SPE-18026 (ledger), SPE-18029 (replay), SPE-18028 (risk and breakers), SPE-18030 (supervisor), SPE-18035 (live gate).

This document is a design only. It names module paths under `src/pumpgrok/`, data schemas, formulas, state machines, failure handling and the tests that prove each subsystem. Every repository fact cites `file:line` of the current tree (branch `feat/grokbot-desk-merge`). Inferences are tagged `[INFERENCE]`. Every numeric default that a human must confirm before the first paper run is tagged `REVIEW`.

Fixed decisions D1-D9 from the orchestrator are taken as given. Where the vendored engine behaves differently from a decision, the difference is recorded in section 11 and in the closing summary; it is not resolved here.

## 0. Scope and reading order

| Section | Subsystem | Module root | Primary tests |
|---|---|---|---|
| 1 | Existing code: what to extend, what to build | (survey) | characterization tests |
| 2 | PaperAdapter fill model | `src/pumpgrok/execution/` | `test_paper_fill_model.py` |
| 3 | Ledger (sqlite WAL, hash chain, snapshots, reconcile, JSONL export) | `src/pumpgrok/ledger/` | `test_ledger_restart_reconcile.py` |
| 4 | Replay (Clock, RNG, fixtures, recorder, determinism) | `src/pumpgrok/replay/` | `test_replay_determinism.py` |
| 5 | Risk engine, breakers, kill switch | `src/pumpgrok/risk/` | `test_kill_switch_one_cycle.py`, `test_breaker_trip_and_cooldown.py` |
| 6 | Supervisor | `src/pumpgrok/supervisor/` | `test_supervisor_bounded_restart.py` |
| 7 | Live gate and autonomy level | `src/pumpgrok/config/`, `src/pumpgrok/execution/live_gate.py` | `test_live_gate_fails_fast.py` |
| 8 | Reporting | `src/pumpgrok/reporting/` | `test_reporting_render.py` |
| 9 | Test list | `tests/` | all |
| 10 | Shared interfaces this design depends on | `src/pumpgrok/core/` | (owned by docs/design/interfaces.md) |
| 11 | Contradictions found with D1-D9 | | |
| 12 | Unverified Items | | |

Shared vocabulary used throughout:

- `S` = virtual SOL reserve of a pump.fun bonding curve (SOL). `T` = virtual token reserve (tokens, 6 decimals). `k = S * T`.
- `equity` = cash + sum of mark-to-market value of open positions, in SOL. Paper equity starts at 10 SOL (D6, REVIEW).
- `cycle` = one scheduled run of one seat's `Bot.cycle()` under the supervisor.
- `correlation_id` = ULID assigned when a candidate token first enters the desk; every downstream event (signal, safety report, order, fill, exit, journal) carries it (D5 contextvars).

## 1. Existing code: extend vs build (SPE-18025)

The vendored engine is a complete dry-run screening loop with a position watcher, a day-scoped risk manager and ops primitives. The root `tools/` are stateless CLIs over a markdown file bus. Neither has a fill model, a ledger, a replay harness, a supervisor or a live gate. The table below is the authoritative extend-vs-build decision for n4; every "extend" row lands as a port into `src/pumpgrok/` with a characterization test that pins the vendor behaviour before any change (D2: vendor removed only when zero inbound refs remain).

| Capability | Vendor / root code today | Evidence | Decision | Target module |
|---|---|---|---|---|
| Spot price from curve reserves | `price_from_reserves` divides `virtual_sol_reserves/1e9` by `virtual_token_reserves/1e6`, falls back to `market_cap/TOTAL_SUPPLY` | `vendor/grokbot-pumpfun/src/executor.py:85-97`, `TOTAL_SUPPLY = 1_000_000_000.0` at `:28` | EXTEND: port verbatim as `CurveQuote.spot()`; add the constant-product fill on top | `execution/curve_math.py` |
| Dry-run buy | `token_amount = size_sol / price`, no fee, no impact, no latency, `tx_hash = "dry_run"` | `executor.py:103-124`, `DRY_RUN_TX = "dry_run"` at `:30` | REPLACE with PaperAdapter (section 2). Keep `"dry_run"` only as the `venue_tx_ref` prefix so `tools/pipeline_evidence.py --candidates` (filters `tx_hash == dry_run`) keeps matching exported records | `execution/paper_adapter.py` |
| Dry-run sell | `proceeds = token_amount * price if price > 0 else 0.0` | `executor.py:126-134` | REPLACE (same) | `execution/paper_adapter.py` |
| Live executor | `LiveExecutor.buy/sell` raise `NotImplementedError` with a six-step TODO; `build_executor` selects it when `config.is_live` | `executor.py:137-172`, `:175-180` | REPLACE with `LiveAdapter` stub raising `LiveGateError` (section 7). No solders/solana imports exist in executor.py today; none are added | `execution/live_adapter.py` |
| Position model | `Position(mint, symbol, creator, entry_price, peak_price, sol_spent, token_amount, opened_at, tx_hash, score)` | `vendor/grokbot-pumpfun/src/models.py:243-255` | EXTEND: ledger `Position` view adds `fees_sol`, `cost_basis_sol`, `filled_fraction`, `correlation_id`, `ticket_id`; vendor fields kept with the same names for the export mapping (section 3.7) | `ledger/views.py` |
| Day-scoped risk state | `RiskManager` holds `day, trades_today, realized_pnl_sol, positions, grok_calls_today`; `roll_day_if_needed` zeroes counters at UTC midnight; `halted` = `daily_loss >= daily_loss_limit_sol` and auto-clears on the next day | `vendor/grokbot-pumpfun/src/risk.py:39-134`, roll at `:106-117`, `halted` at `:131-134` | EXTEND the limit checks (`evaluate` at `:151-178`) into `RiskEngine.check`; REPLACE the state holder with ledger-derived views; REPLACE auto-clear of the halt with human-only clear (D9, constitution `rules/pumpgrok-team.mdc:34`) | `risk/engine.py` |
| Position sizing | `min(max_sol_per_trade * score, remaining_loss_budget * 0.30)`, `MIN_TRADE_SOL = 0.01` | `risk.py:145-149`, constants `:33,:36` | EXTEND: keep as the proposal sizer; `RiskEngine.check` caps it by the D6 percentage limits | `risk/sizing.py` |
| Exit rules | `exit_signal` priority stop_loss -> take_profit -> trailing_stop -> max_hold; trailing only above entry | `risk.py:216-280`, defaults `RiskConfig` at `models.py:318-328` (stop 30 %, TP 120 %, trail 35 %, hold 3600 s, poll 15 s) | EXTEND: port verbatim into the exit seat's rule engine (owned by bot-06-exit; out of n4 scope except that EXIT's paper sells flow through PaperAdapter) | `engine/exits.py` |
| Position watcher | polls `price_fn` every `stop_loss_poll_seconds`, persists peak every +1 %, `BLIND_AFTER = 3` misses | `risk.py:283-382` | EXTEND: becomes the exit seat's cycle under the supervisor; `blind` feeds the DataStale breaker | `engine/watcher.py` |
| Persistence | `PipelineState` JSON written atomically (tmp + fsync + `os.replace`), corrupt file moved to `.corrupt` | `vendor/grokbot-pumpfun/src/state.py:32-45`, `:48-92` | REPLACE with sqlite WAL ledger (section 3). The atomic-write helper is reused for `var/health.json` and JSONL export | `ledger/store.py`, `core/atomic_write.py` |
| Trade log JSONL | `TradeLog.buy/skip/close` records with `ts`, `mode`; size rotation | `vendor/grokbot-pumpfun/src/log.py:90-183` | EXTEND: the JSONL export writes the same three record shapes so `tools/pipeline_evidence.py` and vendor `scripts/dashboard.py` keep reading them | `ledger/export.py` |
| Rate limiter | token bucket `RateLimiter(per_minute, burst)` | `vendor/grokbot-pumpfun/src/ops.py:90-128` | EXTEND: port as `core/ratelimit.py`; used per data source and per LLM client | `core/ratelimit.py` |
| Circuit breaker | `CircuitBreaker(failures, cooldown)`: consecutive failures open it, cooldown elapsed -> half-open with one probe | `ops.py:131-182` | EXTEND: port as the base class for the three risk breakers; add hysteresis (section 5.3) | `risk/breakers.py` |
| Daily call budget | `CallBudget(max_per_day)` resets at UTC midnight | `ops.py:187-229` | EXTEND: port for the LLM client budget; unchanged | `core/budget.py` |
| Metrics | in-memory counters/gauges with hand-rolled Prometheus text | `ops.py:41-86` | REPLACE with `prometheus_client` (D5); keep the metric names as a compatibility layer | `supervisor/metrics.py` |
| Health server | raw asyncio HTTP `/healthz` (200/503 on `status == "ok"`) and `/metrics` | `ops.py:299-358` | EXTEND: keep the two routes and the status contract, add `/readyz`, serve `prometheus_client` text | `supervisor/health.py` |
| Heartbeat, drain, signals | log heartbeat; `drain(tasks, grace)`; `install_signal_handlers` for SIGINT/SIGTERM; `cancel_and_wait` | `ops.py:372-404`, `:406-417`, `:420-431`, `:434-440` | EXTEND: supervisor reuses drain/signal/cancel helpers; heartbeat becomes per-seat | `supervisor/lifecycle.py` |
| Edge-triggered alerts | `_check_transitions` alerts once on breaker/halted/stalled/blind edges | `vendor/grokbot-pumpfun/src/pipeline.py:334-368` | EXTEND: same edge semantics for the supervisor's escalation events | `supervisor/escalation.py` |
| Status snapshot | `Pipeline.status()` JSON with `status`, `mode`, `stalled`, `open_positions`, `halted`, `breaker`, ... | `pipeline.py:392-419`, `STALL_SECONDS = 600` | EXTEND: superset, same keys kept | `supervisor/health.py` |
| Live warning and flag | `LIVE_WARNING` printed; `SystemExit` without `--i-understand-the-risk`; `Config.problems` requires wallet key + https RPC | `pipeline.py:490-543` | REPLACE with the live gate validator (section 7); the flag is one of nine preconditions, not the only one | `execution/live_gate.py` |
| Monitor create/trade events | reads `vSolInBondingCurve`, `marketCapSol`, `traderPublicKey`, `txType`; `CURVE_COMPLETION_SOL = 85.0` | `vendor/grokbot-pumpfun/src/monitor.py:61-83` (create), `:155-159` (trade updates), `:30` | EXTEND: the recorder (section 4.4) captures the raw payloads this parser consumes | `engine/monitor.py`, `replay/recorder.py` |
| Paper fill logger | `append_paper_fill` appends a markdown bullet block to `<desk>/journal/paper-YYYY-MM-DD.md`; price and size are CLI arguments; slippage recorded, not applied | `tools/paper_sim.py:25-43` | REPLACE: becomes `pumpgrok paper buy|sell` (thin wrapper over `exec.place` via PaperAdapter) over the ledger; the markdown block format is kept as one export target (section 3.6) | `cli.py`, `ledger/export.py` |
| Desk halt | `write_halt` rewrites `desk.md` `Halt: true` and appends `FLOOR HALTED - <reason> @ <ts>` plus a journal line | `tools/desk_state.py:195-210`; `HALT_RE` at `:36`; `parse_desk_md` treats any `FLOOR HALTED` text as halt at `:76-77` | EXTEND: `HaltSet` ledger events also write this file so Hermes cron prompts (which gate on `desk_state.py status`) go `[SILENT]` | `ledger/desk_bus.py` |
| Jupiter quote fields | `otherAmountThreshold`, `priceImpactPct`, `slippageBps` passed through | `tools/jupiter_quote.py:45-48` | EXTEND: `Quote` model uses the same names | `execution/quote.py` |
| Priority fee | `recommended_micro_lamports` = percentile fee x multiplier; note says micro-lamports per compute unit | `tools/priority_fee.py:75-81` | EXTEND: fee model consumes this field | `execution/fees.py` |
| Scheduler | none in code; Hermes cron prompts every 15-60 min | `hermes/cron/jobs.yaml` (6 jobs) | BUILD supervisor (section 6) | `supervisor/` |
| Ledger, replay, kill switch, live gate | none | (grep `sqlite|replay|kill|LiveGate` in vendor src and tools: no hits besides `scripts/replay.py`, which summarises the JSONL log and does not replay events) | BUILD | sections 3, 4, 5.4, 7 |

## 2. PaperAdapter (SPE-18024)

### 2.1 Module layout

```
src/pumpgrok/execution/
  __init__.py
  adapter.py         ExecutionAdapter protocol re-exported from core.interfaces
  quote.py           Quote model (Jupiter field names) and QuoteSource
  curve_math.py      pure functions: spot, buy_out, sell_out, impact (no I/O)
  fees.py            FeeModel: venue fee, base fee, priority fee, optional tip
  latency.py         LatencyModel: seeded confirmation latency
  paper_adapter.py   PaperAdapter(ExecutionAdapter)
  live_adapter.py    LiveAdapter stub: every method raises LiveGateError
  live_gate.py       LiveGate validator (section 7)
```

`ExecutionAdapter` (defined in `core/interfaces.py`, see docs/design/interfaces.md) has four methods: `quote(req) -> Quote`, `simulate(order) -> Fill`, `place(order) -> Fill`, `cancel(order_id) -> bool`. PaperAdapter implements all four; `simulate` and `place` share one code path, the only difference being that `place` appends ledger events and `simulate` does not.

Both adapters consume prices through one interface:

```python
class PriceSource(Protocol):
    async def curve(self, mint: str) -> CurveState | None: ...
    # CurveState(mint, s_sol, t_tokens, complete: bool, source_ts: float, source: str)
    async def spot(self, mint: str) -> float: ...        # SOL per token, 0.0 if unknown
```

Live-paper mode binds `PriceSource` to the pump.fun REST client (`/coins/{mint}` fields `virtual_sol_reserves`, `virtual_token_reserves`, executor.py:85-90) with the PumpPortal trade stream as a faster update path (`vSolInBondingCurve`, monitor.py:155-157). Replay mode binds it to the fixture feed (section 4). PaperAdapter does not know which.

### 2.2 Curve math (pure, `curve_math.py`)

Pre-graduation pump.fun is a constant-product curve on virtual reserves.

```
spot(S, T)            = S / T                                  SOL per token
buy_out(S, T, x)      = T * x / (S + x)                        tokens received for x SOL (net of venue fee)
avg_buy_price(S,T,x)  = x / buy_out(S,T,x) = (S + x) / T
impact_buy(S, x)      = avg_buy_price / spot - 1 = x / S       fraction
sell_out(S, T, t)     = S * t / (T + t)                        SOL received (gross of venue fee) for t tokens
impact_sell(T, t)     = t / (T + t)
post_buy(S, T, x)     = (S + x, T - buy_out(S,T,x))            reserves after the fill
```

Unit conventions match the vendor: `S` is `virtual_sol_reserves / 1e9` and `T` is `virtual_token_reserves / 1e6` (executor.py:89-91). The fallback `market_cap / TOTAL_SUPPLY` (executor.py:93-96) is used only to produce a `spot` for mark-to-market when reserves are absent; it never produces a fill, because a fill without reserves has no impact model (`OrderRejected reason=no_reserves`).

Graduation: the vendor treats the curve as complete at `CURVE_COMPLETION_SOL = 85.0` (monitor.py:30) and the REST payload carries `complete` [INFERENCE: field name from pump.fun frontend API, not read by vendor code]. After graduation the pool is a CPMM on real reserves (Raydium or PumpSwap, D8 keeps venues as integrated today so no new venue client is added). The same formulas apply with real reserves `(S_r, T_r)` and a different fee (`cpmm_fee_bps`, default 25, REVIEW). If reserves for a graduated token are unavailable from the current data sources the adapter returns `OrderRejected reason=post_graduation_no_reserves` and the position is marked `mtm_source=last_good` (section 3.5). [INFERENCE] No current data source in D8 exposes Raydium reserves; this is listed in section 12.

### 2.3 Fee model (`fees.py`)

```
venue_fee_sol      = size_sol * venue_fee_bps / 10_000          pump.fun: 100 bps (REVIEW)
base_fee_sol       = 5_000 lamports / 1e9 = 0.000005             one signature (REVIEW)
priority_fee_sol   = micro_lamports_per_cu * compute_units / 1e6 / 1e9
                     micro_lamports_per_cu from tools.priority_fee `recommended_micro_lamports`
                     (tools/priority_fee.py:78); compute_units default 200_000 (REVIEW)
jito_tip_sol       = jito.tip_lamports / 1e9 if jito.enabled else 0
                     vendor default tip_lamports = 1_000_000 (models.py:291-294); paper default enabled=false (REVIEW)
network_cost_sol   = base_fee_sol + priority_fee_sol + jito_tip_sol
```

Buy: `x_net = size_sol - venue_fee_sol` enters the curve; cash debit = `size_sol + network_cost_sol`.
Sell: `gross = sell_out(S, T, t)`; `proceeds = gross - gross * venue_fee_bps / 10_000 - network_cost_sol`.

All fee inputs are recorded on the `FillRecorded` event (section 3.3) so reports can split PnL into price, venue fee and network cost.

### 2.4 Slippage cap (Jupiter `otherAmountThreshold` semantics)

A `Quote` is produced at decision time, either from Jupiter lite-api (fields passed through by `tools/jupiter_quote.py:45-48`: `outAmount`, `otherAmountThreshold`, `slippageBps`, `priceImpactPct`) or synthesised from the curve:

```
quote.outAmount            = buy_out(S0, T0, x_net)                     ExactIn
quote.otherAmountThreshold = floor(outAmount * (1 - slippage_bps / 10_000))
quote.priceImpactPct       = impact_buy(S0, x_net) * 100
```

For sells (ExactIn tokens): `outAmount = sell_out(S0,T0,t) * (1 - venue_fee)`, `otherAmountThreshold = floor(outAmount * (1 - slippage_bps/10_000))`.

At confirmation time (after latency, section 2.5) the fill is recomputed on the reserves observed then, `(S1, T1)`. If `out_at_confirmation < otherAmountThreshold` the order is rejected with `reason=slippage_exceeded` and the ledger records both numbers. This mirrors what the on-chain program would do with `max_sol_cost` / `min_sol_output` (vendor TODO at executor.py:151-156,170-171). There is no retry: the single-send rule (`rules/pumpgrok-team.mdc:30`) applies to paper orders too, so a rejected order ends the order; a new order needs a new decision (and, under `manual-ticket`, a fresh approval).

`slippage_bps` comes from the order (the ticket's approved max slippage) and is capped by `risk.max_slippage_bps` (default 300, REVIEW).

### 2.5 Confirmation latency (`latency.py`)

```
latency_s = clip(lognormal(mu = ln(1.2), sigma = 0.5), 0.4, 20.0)     seeded (REVIEW)
dropped   = rng.random() < p_drop                                      p_drop = 0.02 (REVIEW)
```

Both draws come from the single injected `random.Random` (section 4.2) so replay is deterministic. The adapter awaits `clock.sleep(latency_s)` (virtual in replay), then re-reads `PriceSource.curve(mint)`. If `dropped`, the order is rejected with `reason=tx_dropped` (the paper analogue of "UNKNOWN RESULT - reconcile by signature", `rules/pumpgrok-team.mdc:30`); the adapter never resubmits.

### 2.6 Partial fill and liquidity floor

Evaluated against the reserves at decision time, in this order:

```
if S0 < liquidity_floor_mult * size_sol:         # D6: floor 10x order size (REVIEW)
    reject reason=below_liquidity_floor
fill_cap_sol = liquidity_fraction * S0           # D6: 2 % of pool liquidity (REVIEW)
if size_sol > fill_cap_sol:
    filled_sol = fill_cap_sol; filled_fraction = fill_cap_sol / size_sol
    remainder is cancelled (not queued): OrderPartial semantics are a FillRecorded with filled_fraction < 1
else:
    filled_sol = size_sol; filled_fraction = 1.0
```

Note 10x floor means `size <= S0 / 10` and 2 % fraction means full fill only when `size <= S0 / 50`; sizes between `S0/50` and `S0/10` fill partially. Sells use `T0` with the same two parameters (`t <= T0 / 10` to proceed, `t <= T0 / 50` for a full fill); partial sells leave the remainder in the position and EXIT's next cycle decides again.

### 2.7 Mark-to-market

Each open position is valued at liquidation value, not spot:

```
mtm_sol(pos)   = sell_out(S, T, pos.token_amount) * (1 - venue_fee_bps / 10_000)
unrealized_sol = mtm_sol - pos.cost_basis_sol           cost_basis = cash debited incl. all fees
```

This is deliberately conservative for thin curves: spot x quantity overstates what a sell would return. `MarkToMarket` events are written by the journal seat every `ledger.mtm_interval_s` (60 s, REVIEW) and whenever RiskEngine needs fresh equity (it reads the cached value if younger than `mtm_interval_s`).

### 2.8 State machine of one paper order

```
            quote ok                      latency elapsed
 NEW ------------------> ACCEPTED ----------------------------> CONFIRMING
  |  reject:no_reserves      |  reject:below_liquidity_floor        |
  |  reject:risk_* (sec 5)   |  reject:kill_switch                  +--> FILLED (filled_fraction 1.0)
  |  reject:live_gate        |                                      +--> PARTIAL (filled_fraction < 1.0)
  v                          v                                      +--> REJECTED slippage_exceeded | tx_dropped
 REJECTED               REJECTED
```

Every transition is one ledger event (section 3.3). `cancel(order_id)` succeeds only in `ACCEPTED` (before the latency sleep completes); after that it returns `False`, matching a real chain where a sent transaction cannot be recalled.

### 2.9 Worked numeric example

Inputs:

| Quantity | Value | Source |
|---|---|---|
| Paper equity | 10.000000 SOL | D6 |
| Order size (2 % of equity) | 0.200000 SOL | D6 |
| Curve at decision `S0`, `T0` | 42.000000 SOL, 766,428,571.4 tokens | `k = 30 * 1,073,000,000 = 3.219e10` [INFERENCE: pump.fun initial virtual reserves 30 SOL / 1.073e9 tokens] |
| `venue_fee_bps` | 100 | section 2.3 |
| `recommended_micro_lamports` | 20,000 | `tools/priority_fee.py:78` output for this example |
| `compute_units` | 200,000 | section 2.3 |
| Jito | disabled | section 2.3 |
| `slippage_bps` (ticket) | 100 | ticket |
| `liquidity_floor_mult`, `liquidity_fraction` | 10, 0.02 | section 2.6 |

Step 1, liquidity checks: `S0 = 42 >= 10 * 0.2 = 2` passes the floor. `fill_cap = 0.02 * 42 = 0.84 >= 0.2`, so the order is eligible for a full fill.

Step 2, fees: `venue_fee = 0.2 * 0.01 = 0.002000 SOL`; `x_net = 0.198000 SOL`. `priority_fee = 20,000 * 200,000 / 1e6 / 1e9 = 0.000004 SOL`; `base_fee = 0.000005 SOL`; `network_cost = 0.000009 SOL`.

Step 3, quote at `(S0, T0)`:

```
spot0      = 42 / 766,428,571.4             = 5.4800e-8 SOL/token
outAmount  = 766,428,571.4 * 0.198 / 42.198 = 3,596,210 tokens
avg_price  = 0.198 / 3,596,210              = 5.5058e-8 SOL/token
impact     = 0.198 / 42                     = 0.4714 %   (check: 5.4800e-8 * 1.004714 = 5.5058e-8)
threshold  = floor(3,596,210 * 0.99)        = 3,560,247 tokens
```

Step 4, latency: seeded draw `latency_s = 1.4`, `dropped = False`. The adapter sleeps 1.4 s (virtual in replay) and re-reads the curve.

Step 5a, confirmation with a small move (`S1 = 42.1`, a 0.1 SOL buy landed first): `T1 = 3.219e10 / 42.1 = 764,608,076.0`; `out1 = 764,608,076.0 * 0.198 / 42.298 = 3,579,186 tokens`; `3,579,186 >= 3,560,247` so the order FILLS. Recorded fill:

```
FillRecorded: filled_sol=0.200000 filled_fraction=1.0 token_amount=3,579,186
              fill_price=5.5320e-8 venue_fee_sol=0.002000 network_cost_sol=0.000009
              cash_delta_sol=-0.200009 cost_basis_sol=0.200009
              quote_out=3,596,210 threshold=3,560,247 confirm_out=3,579,186 latency_s=1.4
post-fill curve: S=42.298, T=761,028,890   (T1 - out1)
immediate MTM:   sell_out(42.298, 761,028,890, 3,579,186) * 0.99
               = 42.298 * 3,579,186 / 764,608,076 * 0.99 = 0.198 * 0.99 = 0.196020 SOL
unrealized:      0.196020 - 0.200009 = -0.003989 SOL  (-1.99 %: round-trip venue fee plus network cost)
```

Step 5b, confirmation with a larger move (`S1 = 42.5`): `T1 = 757,411,764.7`; `out1 = 757,411,764.7 * 0.198 / 42.698 = 3,512,285 < 3,560,247` so the order is REJECTED `reason=slippage_exceeded` with `quote_out=3,596,210 threshold=3,560,247 confirm_out=3,512,285`. No cash moves; `fees_sol` on the rejection is `network_cost_sol = 0.000009` because a failed transaction still pays the base and priority fee (REVIEW: charge network cost on `slippage_exceeded`; do not charge on `tx_dropped`).

Step 6, partial fill variant: size 1.5 SOL on the same curve. Floor: `42 >= 15` passes. `fill_cap = 0.84 < 1.5`, so `filled_sol = 0.84`, `filled_fraction = 0.56`, and the remaining 0.66 SOL is cancelled, not queued.

## 3. Ledger (SPE-18026)

### 3.1 Module layout

```
src/pumpgrok/ledger/
  __init__.py
  store.py        LedgerStore: sqlite3 WAL, append(event) -> seq, hash chain, snapshots
  events.py       pydantic v2 models for every event type; EventType enum
  reducer.py      pure reduce(state, event) -> state; LedgerState model
  views.py        positions(), cash(), pnl(), equity_curve(), drawdown(), fees()
  reconcile.py    restart = snapshot + tail replay + verify; Reconciler
  export.py       JSONL journal export; vendor trades.jsonl shape; paper-YYYY-MM-DD.md block
  desk_bus.py     mirrors HaltSet/HaltCleared into $PUMPGROK_DESK/desk.md
```

Location: `var/ledger.sqlite` (gitignored, D2). One ledger per desk process; the supervisor holds the only writer connection; readers (reporting, CLI) open read-only connections (`?mode=ro`), which WAL permits concurrently.

### 3.2 Schema

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;            -- every append is durable before the caller sees seq

CREATE TABLE events (
  seq             INTEGER PRIMARY KEY,          -- monotonic, no gaps
  ts_utc          TEXT    NOT NULL,             -- ISO-8601 with microseconds and Z, from Clock
  correlation_id  TEXT    NOT NULL,             -- ULID; "desk" for process-level events
  idempotency_key TEXT    NOT NULL UNIQUE,      -- sha256(type|correlation_id|caller-supplied key)
  type            TEXT    NOT NULL,             -- EventType value
  payload_json    TEXT    NOT NULL,             -- canonical JSON (sorted keys, no whitespace)
  prev_hash       TEXT    NOT NULL,             -- hash of seq-1; 64 zeros for seq 1
  hash            TEXT    NOT NULL UNIQUE       -- sha256(prev_hash|seq|ts_utc|correlation_id|type|payload_json)
);
CREATE TRIGGER events_append_only_u BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER events_append_only_d BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;

CREATE TABLE snapshots (
  seq         INTEGER PRIMARY KEY,              -- last event folded into this snapshot
  ts_utc      TEXT    NOT NULL,
  state_json  TEXT    NOT NULL,                 -- LedgerState canonical JSON
  state_hash  TEXT    NOT NULL,                 -- sha256(state_json)
  chain_hash  TEXT    NOT NULL                  -- events.hash at seq
);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- keys: schema_version ("1"), ledger_id (ULID), initial_equity_sol, created_ts_utc, mode, autonomy_level
```

Hash chain rule: `hash = sha256(prev_hash + "|" + str(seq) + "|" + ts_utc + "|" + correlation_id + "|" + type + "|" + payload_json)`. Verification walks `events` in `seq` order and recomputes; any mismatch makes the ledger `INCONSISTENT` (section 3.5). Because `ts_utc` comes from the injected `Clock`, replay runs produce byte-identical chains (section 4.5).

Snapshot cadence: every `ledger.snapshot_every_events` (500, REVIEW) events or `ledger.snapshot_every_s` (300 s, REVIEW), whichever first; plus on `DailyRollover`, on graceful shutdown, and on `HaltSet`. Old snapshots are kept (they are small; the table is append-only like `events`).

### 3.3 Event types and payloads

All payloads carry no secrets and no wallet keys. `*_sol` fields are decimal strings serialised from `Decimal` with 9 places (lamport precision) to keep hashes stable across platforms; token amounts are integers in base units (6 decimals).

| type | correlation_id | payload fields | written by |
|---|---|---|---|
| `OrderPlaced` | token's | `order_id, ticket_id, side(buy/sell), mint, size_sol or token_amount, slippage_bps, quote{outAmount, otherAmountThreshold, priceImpactPct, source}, approval{kind: human/autonomous-paper, approved_by, phrase_hash}, risk_check{passed, caps}` | PaperAdapter.place |
| `OrderRejected` | token's | `order_id, reason (enum section 2.8 + risk_* + kill_switch + live_gate + ledger_inconsistent), detail, fees_sol, quote_out, threshold, confirm_out` | PaperAdapter / RiskEngine / LiveGate |
| `FillRecorded` | token's | `order_id, side, mint, filled_sol, token_amount, filled_fraction, fill_price, venue_fee_sol, network_cost_sol, cash_delta_sol, latency_s, curve_before{S,T}, curve_after{S,T}, venue_tx_ref ("dry_run:<ULID>")` | PaperAdapter.place |
| `PositionOpened` | token's | `mint, symbol, creator, ticket_id, entry_price, token_amount, cost_basis_sol, score, opened_ts_utc` | reducer-driven (adapter emits after first buy fill) |
| `PositionClosed` | token's | `mint, exit_price, proceeds_sol, realized_pnl_sol, pnl_pct, hold_seconds, reason (stop_loss/take_profit/trailing_stop/max_hold/rug_alert/kill_flatten/manual), venue_tx_ref` | adapter after a sell fill that zeroes the position |
| `MarkToMarket` | `desk` | `ts_source, prices{mint: {spot, S, T, mtm_sol, source, age_s}}, cash_sol, equity_sol, unrealized_sol` | journal seat / RiskEngine |
| `HaltSet` | `desk` | `reason (daily_loss/drawdown/ledger_inconsistent/manual), detail, set_by, equity_sol, day_start_equity_sol` | RiskEngine |
| `HaltCleared` | `desk` | `reason, cleared_by ("human:<name>" required), note` | CLI only |
| `KillSwitchSet` | `desk` | `source (env/file/alert_command), reason, flatten_requested` | RiskEngine |
| `KillSwitchCleared` | `desk` | `cleared_by ("human:<name>"), sources_now_clear[]` | CLI only |
| `BreakerTripped` | `desk` | `breaker (data_stale/loss_velocity/exec_errors), metric, threshold, cooldown_s` | breakers |
| `BreakerReset` | `desk` | `breaker, after_s, probe_ok` | breakers |
| `DailyRollover` | `desk` | `day_utc, day_start_equity_sol, prior_day{realized, unrealized, fees, trades}, open_positions[]` | RiskEngine |
| `ConfigChanged` | `desk` | `keys_changed[], old_hash, new_hash, by` | startup (diff vs `meta`) |
| `LiveWriteAttempted` | token's or `desk` | `adapter, method, caller_seat, gate_result{unmet[]}, stack_hash` | LiveAdapter / registry |
| `Escalation` | `desk` | `kind (bot_restart_exhausted/heartbeat_stale/persistence_down/...), seat, detail` | supervisor |
| `JournalNote` | token's or `desk` | `seat, text, refs[]` | journal seat |

`OrderPartial` from the spec is represented as `FillRecorded` with `filled_fraction < 1`; `FeeCharged` and `CashAdjusted` are folded into `FillRecorded.cash_delta_sol` and `OrderRejected.fees_sol` so that cash has exactly one source of truth per order.

### 3.4 Reducer and derived views

`reduce(state, event)` is pure and total: unknown event types are recorded in `state.unknown_events` and otherwise ignored, so a newer process can read an older ledger and vice versa.

```
LedgerState:
  seq, day_utc, day_start_equity_sol, peak_equity_sol
  cash_sol
  positions{mint: Position(mint, symbol, creator, ticket_id, correlation_id, entry_price, peak_price,
                           token_amount, cost_basis_sol, fees_sol, opened_ts_utc, last_mtm_sol, last_mtm_ts, mtm_source)}
  halt{active, reason, since}  kill_switch{active, source, since}  breakers{name: {state, until}}
  counters{trades_today, rejected_today{reason: n}, fees_today_sol, realized_today_sol}
  last_mtm_ts_utc
```

Views (`views.py`), all computed from `LedgerState` plus the event tail where needed:

```
cash_sol            = state.cash_sol
positions()         = state.positions (filter token_amount > 0)
realized_pnl(from,to) = sum(PositionClosed.realized_pnl_sol in range)
unrealized_pnl()    = sum(pos.last_mtm_sol - pos.cost_basis_sol)
fees(from,to)       = sum(FillRecorded.venue_fee_sol + network_cost_sol) + sum(OrderRejected.fees_sol)
equity()            = cash_sol + sum(pos.last_mtm_sol)
equity_curve()      = [(MarkToMarket.ts, equity_sol)]  plus a point after every FillRecorded
drawdown()          = (peak_equity_sol - equity()) / peak_equity_sol
daily_pnl_pct()     = (equity() - day_start_equity_sol) / day_start_equity_sol
win_rate(from,to)   = closed with realized_pnl_sol > 0 / closed
profit_factor       = sum(gains) / abs(sum(losses))   (inf if no losses; reported as "n/a")
```

### 3.5 Restart: snapshot + tail replay + reconcile

```
1. open var/ledger.sqlite; if missing -> fresh ledger: write meta, write ConfigChanged, state = initial (cash = initial_equity_sol)
2. s = latest snapshot (or empty state at seq 0)
3. tail = SELECT * FROM events WHERE seq > s.seq ORDER BY seq
4. verify chain: for each event in tail recompute hash; first event's prev_hash must equal s.chain_hash
5. state = fold(reduce, s.state, tail)
6. integrity checks (all must hold):
   a. state.cash_sol == initial_equity_sol + sum(FillRecorded.cash_delta_sol) - sum(OrderRejected.fees_sol)   over the FULL event table
   b. for each open position: token_amount == sum(buy fills) - sum(sell fills) for that mint; cost_basis == sum(buy cash) - proportional reductions on sells
   c. no open position whose PositionOpened predates a PositionClosed with the same mint without a newer PositionOpened
   d. the full-replay state (fold over all events from seq 1) equals `state` field-for-field  [cheap at paper scale: tens of thousands of events; computed on every start]
   e. snapshots.chain_hash matches events.hash at snapshots.seq for the latest snapshot
7. PriceSource probe for every open position: curve() reachable -> MarkToMarket appended; unreachable -> position.mtm_source = "last_good", DataStale breaker pre-armed
8. status: CONSISTENT -> normal start; INCONSISTENT -> append HaltSet(reason=ledger_inconsistent, detail=<which check>), Notifier alert severity critical, process continues in observe-only (all seats run, RiskEngine refuses every order with reason=ledger_inconsistent); `pumpgrok verify --ledger` prints the diff
```

What "mismatch" means concretely: any of 4, 6a-6e failing, or an `UNIQUE` violation on `idempotency_key` during tail replay (duplicate write detected). Nothing is auto-repaired. A human runs `pumpgrok verify --ledger --explain`, decides, and clears with `pumpgrok state halt --clear --by human:<name> --reason "<text>"` which appends `HaltCleared`; the next start re-runs the checks. If checks still fail, the halt is re-set immediately (the clear cannot override a persistent inconsistency).

Unwritable store (disk full, permission): `LedgerStore.append` raises `LedgerUnavailable`; RiskEngine refuses orders (`reason=persistence_down`), the supervisor buffers at most `ledger.buffer_max_events` (1000, REVIEW) non-order events in memory, emits `Escalation(kind=persistence_down)` through the Notifier, and retries the append with the jittered tenacity policy (D5). If the buffer fills, the oldest `MarkToMarket` events are dropped first; `FillRecorded`/`PositionClosed` are never dropped (if they cannot be written, the order is not considered placed, which is why the ledger append happens before the adapter returns the fill).

### 3.6 JSONL journal export

Export runs after every event batch and on shutdown; files are append-only and idempotent (each line carries `seq`; the exporter resumes from the last exported `seq` stored in `meta.export_seq`).

| Target | Path | Shape | Consumer |
|---|---|---|---|
| Canonical JSONL | `var/journal/YYYY-MM-DD.jsonl` | one line per ledger event: `{seq, ts_utc, correlation_id, type, payload}` | reporting, `pumpgrok journal rollup` |
| Vendor-compatible trades log | `var/journal/trades.jsonl` | `type: buy / skip / close` records with the exact keys of `vendor/grokbot-pumpfun/src/log.py:98-183` (`ts`, `mode` stamped per `log.py:91-92`), `tx_hash` = `venue_tx_ref` | `tools/pipeline_evidence.py` (`--candidates` filters `tx_hash == dry_run`; the ref starts with `dry_run:` so the filter is changed to a prefix match in the tools port), vendor `scripts/dashboard.py`, `scripts/replay.py` |
| Desk markdown | `$PUMPGROK_DESK/journal/paper-YYYY-MM-DD.md` | the `### PAPER BUY | <ticket>` bullet block of `tools/paper_sim.py:31-40`, extended with `Fill price`, `Fees SOL`, `Correlation` lines | humans, Hermes `chief-journal-rollup` cron, `desk_state.py` (ticket id scan at `tools/desk_state.py:93-104`) |
| Desk halt mirror | `$PUMPGROK_DESK/desk.md` | `Halt: true` + `FLOOR HALTED - <reason> @ <ts>` exactly as `tools/desk_state.py:199-205` writes it | Hermes cron prompts (`[SILENT]` gate), `desk_state.py status` |

`/workspace/trading-desk` compatibility is therefore preserved without the LLM seats parsing sqlite.

### 3.7 Mapping from vendor fields

| Vendor field | Source | Ledger equivalent |
|---|---|---|
| `PipelineState.day` | state.py:36 | `LedgerState.day_utc` (set by `DailyRollover`) |
| `PipelineState.trades_today` | state.py:37 | `counters.trades_today` (count of `FillRecorded side=buy` since rollover) |
| `PipelineState.realized_pnl_sol` | state.py:38 | `counters.realized_today_sol` (sum of `PositionClosed.realized_pnl_sol` since rollover) |
| `PipelineState.grok_calls_today` | state.py:39 | not a ledger concern; `core/budget.py` persists its own counter in `var/budget.json` |
| `PipelineState.positions{mint: Position}` | state.py:40 | `LedgerState.positions` |
| `Position.entry_price` | models.py:247 | `Position.entry_price` = `FillRecorded.fill_price` of the opening fill (SOL per token, same unit) |
| `Position.peak_price` | models.py:248 | `Position.peak_price`, updated by `MarkToMarket` (vendor persisted it every +1 %, risk.py `PEAK_PERSIST_STEP`; the ledger records it on every MTM event, 60 s cadence) |
| `Position.sol_spent` | models.py:249 | `Position.cost_basis_sol` (includes fees; vendor excluded fees because it had none) |
| `Position.token_amount` | models.py:250 | `Position.token_amount` (integer base units; vendor float tokens; export divides by 1e6) |
| `Position.opened_at` (epoch float) | models.py:251 | `Position.opened_ts_utc` (ISO string; export converts) |
| `Position.tx_hash` | models.py:252 | `FillRecorded.venue_tx_ref` |
| `Position.score` | models.py:253 | `PositionOpened.score` (signal seat's total score) |
| trades.jsonl `buy.size_sol` | log.py:113 | `FillRecorded.filled_sol` |
| trades.jsonl `close.pnl_sol / pnl_pct / hold_seconds / reason` | log.py:176-179 | `PositionClosed.realized_pnl_sol / pnl_pct / hold_seconds / reason` |
| trades.jsonl `skip.stage / reason` | log.py:146-147 | `OrderRejected.reason` for stage `risk`/`executor`; pre-order skips (monitor/analyzer/scoring/checker) are `JournalNote` events emitted by the owning seat with `refs=[stage, reason]` |

## 4. Replay (SPE-18029)

### 4.1 Module layout

```
src/pumpgrok/replay/
  __init__.py
  clock.py        Clock protocol; WallClock; FixtureClock
  rng.py          make_rng(seed) -> random.Random; the only RNG constructor in the package
  fixtures.py     FixtureReader: merges dataset streams by ts; FixtureManifest
  sources.py      FixturePriceSource, FixtureEventStream, FixtureHttpTransport (httpx.MockTransport), FixtureWebSocket
  recorder.py     Recorder: wraps live transports and writes the dataset format
  runner.py       run_replay(dataset, config) -> ReplayResult(ledger_hash, events, equity_curve)
  trim.py         fixture trimming for the CI smoke dataset
```

### 4.2 Clock and RNG

```python
class Clock(Protocol):
    def now(self) -> float: ...             # epoch seconds (UTC)
    def monotonic(self) -> float: ...
    def utc_iso(self) -> str: ...           # ts_utc for ledger events
    async def sleep(self, seconds: float) -> None: ...
```

`WallClock` delegates to `time.time`, `time.monotonic`, `asyncio.sleep`. `FixtureClock` holds a virtual time that only advances when (a) the runner delivers the next fixture event, or (b) a task calls `sleep(s)`; sleeping tasks are queued in a heap and woken in `(wake_time, enqueue_seq)` order so scheduling is deterministic regardless of asyncio's internal ordering. The vendor already injects `clock` into `RiskManager` (`risk.py:45`), `RateLimiter` (`ops.py:93-98`), `CircuitBreaker` (`ops.py:139-143`), `CallBudget` (`ops.py:191-196`), `Metrics` (`ops.py:44`); the port keeps that style and extends it to every module that reads time.

One RNG: `rng.make_rng(config.replay.seed)` is called exactly once in `cli.py` and passed down by constructor injection (PaperAdapter latency, breakers' jitter, tenacity jitter, the LLM-fallback tie-breaks). `random.random()`, `random.Random()` without an argument, `uuid.uuid4()` and `secrets` are banned in `src/pumpgrok/` by a static test (`tests/safety/test_no_ambient_randomness.py`, owned by n7); ULIDs come from `core/ids.py` which takes `(clock, rng)`.

Default seed: `20260101` (config `replay.seed`, REVIEW). In live-paper mode the seed is still fixed (latency draws need no entropy), which makes a live-paper day re-runnable from its recording.

### 4.3 Fixture format

```
tests/fixtures/replay/<dataset>/
  manifest.json      {"dataset", "recorded_from_utc", "recorded_to_utc", "seed_hint", "sources": {...}, "sha256": {file: digest}, "notes"}
  pumpportal.jsonl   {"ts": 1767225600.123, "kind": "ws", "stream": "pumpportal", "payload": {... raw message ...}}
  pumpfun_rest.jsonl {"ts": ..., "kind": "http", "method": "GET", "url": "/coins/<mint>", "status": 200, "body": {...}}
  jupiter.jsonl      {"ts": ..., "kind": "http", "method": "GET", "url": "https://lite-api.jup.ag/swap/v1/quote?...", "status": 200, "body": {...}}
  rpc.jsonl          {"ts": ..., "kind": "rpc", "method": "getAccountInfo|getTokenLargestAccounts|getRecentPrioritizationFees", "params_hash": "...", "result": {...}}
  ticks.jsonl        {"ts": ..., "kind": "tick", "mint": "...", "S": 42.1, "T": 764608076.0, "complete": false, "source": "pumpportal|rest"}
  llm.jsonl          {"ts": ..., "kind": "llm", "request_hash": "...", "model": "...", "response": {...}}   (optional; absent -> rule-based fallback is exercised)
```

Every line is one JSON object with a leading `ts` (epoch seconds, float). Streams are merged by `(ts, file_order, line_no)`. The raw PumpPortal payloads are the ones `parse_create_event` and `handle_event` consume (`txType`, `mint`, `vSolInBondingCurve`, `vTokensInBondingCurve`, `marketCapSol`, `traderPublicKey`, monitor.py:61-83 and :149-159). `ticks.jsonl` is derived at record time from both streams so `FixturePriceSource.curve()` can answer without re-parsing; the derivation is deterministic and `pumpgrok replay rebuild-ticks --dataset <name>` regenerates it.

HTTP and RPC lookups are keyed by `(method, url-or-params_hash)`; when the desk asks for something the fixture does not contain, the fixture transport returns a synthetic `503` and the normal degradation path runs (this is a feature: a trimmed dataset exercises breakers).

### 4.4 Recorder

`pumpgrok run --mode paper --record <dataset> --duration 2h [--mints <list>]` runs the normal live-paper desk with every outbound transport wrapped (`--record` and `--replay <dir>` are mutually exclusive options of the one `run` command; `--once` runs a single supervisor tick, which is what Hermes cron wrappers use):

- httpx: a recording `httpx.AsyncBaseTransport` that forwards to the real transport, then writes the request/response line (API keys in headers are dropped; query parameters named `api-key`, `key`, `token` are replaced by `REDACTED`; this list is the G-3 secret regex set applied to URLs).
- websockets: a `RecordingWebSocket` wrapper that writes every received frame before yielding it.
- JSON-RPC: the `core/rpc.py` client has a `recorder` hook.
- LLM: the x.ai client records the exact request hash and response.

The recorder uses the same supervisor, bots and PaperAdapter, so a recording session is itself a paper-trading session whose ledger is kept next to the dataset (`ledger.sqlite.recorded`) as the reference for the determinism test.

### 4.5 Determinism test

`tests/test_replay_determinism.py` runs `run_replay("smoke-10m", config)` twice in fresh temp dirs and asserts:

1. `sha256` of the concatenated `events.hash` column is identical;
2. `sha256` of `var/journal/YYYY-MM-DD.jsonl` bytes is identical;
3. the final `LedgerState` dumps are identical;
4. optionally (`--compare-recorded`) both match `ledger.sqlite.recorded` from the recording session, which proves the live-paper path and replay path are one code path.

Sources of non-determinism that the design removes: wall clock (FixtureClock), RNG (single seeded), asyncio task ordering (FixtureClock's sleep heap plus the supervisor running seats in roster order within a tick), dict ordering (canonical JSON), float formatting (Decimal strings), ULIDs (from clock + rng), LLM responses (fixture or deterministic fallback).

### 4.6 CI smoke dataset

`smoke-10m` is produced once by an operator: `pumpgrok run --mode paper --record smoke-10m --duration 10m`, then `pumpgrok replay trim --dataset smoke-10m --max-events 2000 --keep-mints-with-fills` which keeps every event for mints that produced an order and a random (seeded) 5 % of the rest, then `pumpgrok verify --fixture smoke-10m` which replays it (`pumpgrok run --mode paper --replay tests/fixtures/replay/smoke-10m`) and checks the manifest digests. Target size under 1 MB so it is committed. It must contain: at least one full fill, one partial fill, one `slippage_exceeded`, one `below_liquidity_floor`, one DataStale gap (the trimmer inserts a 180 s hole), and one exit by `stop_loss` or `take_profit`. `tests/fixtures/replay/README.md` lists the datasets and how to regenerate them. A longer `soak-3d` dataset (three recorded days, trimmed to about 50 MB) is not committed; nightly CI downloads it from the artifact store named in `.github/workflows/ci.yml` (owned by n5/n8).

## 5. Risk engine, breakers, kill switch (SPE-18028)

### 5.1 Module layout

```
src/pumpgrok/risk/
  __init__.py
  engine.py     RiskEngine.check(order) -> RiskDecision; halts; daily rollover
  limits.py     RiskLimits pydantic-settings model (all REVIEW defaults)
  sizing.py     proposal sizer (vendor position_size port)
  breakers.py   Breaker base (vendor CircuitBreaker port) + DataStale, LossVelocity, ExecErrors
  killswitch.py KillSwitch: env/file/alert-command sources, set/clear, audit
```

RiskEngine is owned by bot-02-risk (D3). It is the only component that may say "no" to an order; PaperAdapter calls `risk.check(order)` first and refuses to proceed without a passed `RiskDecision` whose `order_hash` matches.

### 5.2 Limits and `RiskEngine.check`

```toml
[risk]                                   # every value REVIEW
initial_equity_sol        = 10.0         # D6
max_trade_pct_equity      = 0.02         # D6: per-order size cap
max_token_pct_equity      = 0.05         # D6: cost basis of open position + this order
max_open_positions        = 3            # vendor RiskConfig.max_open_positions (models.py:321)
max_trades_per_day        = 20           # vendor RiskConfig.max_trades_per_day (models.py:320)
min_trade_sol             = 0.01         # vendor MIN_TRADE_SOL (risk.py:36)
daily_loss_halt_pct       = 0.05         # constitution: rules/pumpgrok-team.mdc:34 (FLOOR)
drawdown_halt_pct         = 0.15         # D6
liquidity_floor_mult      = 10.0         # D6
liquidity_fraction        = 0.02         # D6
max_slippage_bps          = 300
one_position_per_creator  = true         # vendor FilterConfig (pipeline.py:376-384)
daily_loss_basis          = "total"      # total = realized + unrealized (conservative); "realized" = vendor behaviour
```

`check(order)` runs these in order and stops at the first failure; the decision carries every evaluated cap so the rejection is explainable:

```
 0. ledger status CONSISTENT                                  else reject ledger_inconsistent
 1. kill switch not active (re-read sources now, sec 5.4)     else reject kill_switch
 2. no halt active (daily_loss / drawdown / manual)           else reject halted:<reason>
 3. no breaker open (any of the three)                        else reject breaker_open:<name>
 4. live gate: order.adapter == "paper" or gate passed        else reject live_gate (and LiveWriteAttempted event)
 5. autonomy: manual-ticket -> approval record present and phrase matches (sec 7.4)   else reject approval_missing
 6. roll day if clock.utc_day != state.day_utc (sec 5.5)
 7. counters.trades_today < max_trades_per_day                else reject max_trades_per_day
 8. len(open positions) < max_open_positions (buy only)        else reject max_open_positions
 9. mint not already open (buy only)                           else reject already_open
10. creator has no open position if one_position_per_creator  else reject creator_already_open
11. equity = views.equity() (MTM younger than mtm_interval_s; else request MTM; if PriceSource fails -> reject data_stale)
12. size_sol <= max_trade_pct_equity * equity                 else size is CAPPED (not rejected) and decision.capped = true
13. cost_basis(mint) + size_sol <= max_token_pct_equity * equity   else cap or reject if cap < min_trade_sol
14. size_sol >= min_trade_sol                                 else reject size_too_small
15. liquidity: S0 >= liquidity_floor_mult * size_sol          else reject below_liquidity_floor (adapter re-checks at fill time)
16. pass -> RiskDecision(passed=True, size_sol=final, caps={...}, order_hash)
```

Sells are never blocked by 1-3 and 7-15 when `reason` is an exit rule, `rug_alert` or `kill_flatten`: reducing risk is always allowed. Sells are blocked only by 0 (ledger inconsistent means we do not know what we hold) and 4-5.

Halts (set by `RiskEngine.evaluate_halts()`, called at the start of every risk cycle and after every `PositionClosed`/`MarkToMarket`):

```
daily_loss_pct = (day_start_equity - equity) / day_start_equity      (equity per daily_loss_basis)
if daily_loss_pct >= daily_loss_halt_pct and not halt.active:
    append HaltSet(reason=daily_loss); Notifier.alert(critical, "FLOOR HALTED - DAILY LOSS LIMIT"); desk_bus.write_halt(...)
drawdown = (peak_equity - equity) / peak_equity
if drawdown >= drawdown_halt_pct and not halt.active:
    append HaltSet(reason=drawdown)
```

The constitutional alert text is a single constant `FLOOR_HALTED_DAILY` in `risk/engine.py` copied byte-for-byte from `rules/pumpgrok-team.mdc:34` (that line uses an en dash, U+2013, between `HALTED` and `DAILY`; this document is ASCII-only and writes a hyphen, the code must use the constitution's bytes; `tools/desk_state.py:76` matches case-insensitively on `FLOOR HALTED` only, so either dash satisfies the file bus).

### 5.3 Breakers

All three subclass the vendor `CircuitBreaker` port (`ops.py:131-182`: consecutive-failure threshold, `opened_at`, cooldown, half-open probe) with two additions: an explicit `half_open` state that admits exactly one probe, and hysteresis (`reset_after_ok` consecutive successes before `closed`). States: `closed -> open -> half_open -> closed | open`.

| Breaker | Trip condition (REVIEW) | Cooldown | Reset (hysteresis) | While open |
|---|---|---|---|---|
| `DataStale` | no PumpPortal frame AND no successful REST curve read for `data_stale_s = 120` (vendor `STALL_SECONDS = 600`, pipeline.py, is for the launch stream only; 120 s is for prices), OR any open position with 3 consecutive missing prices (vendor `BLIND_AFTER = 3`, risk.py) | 60 s after the first fresh tick | 3 consecutive fresh ticks within 30 s | no new buys; EXIT keeps evaluating on `last_good` prices for at most `blind_max_s = 300`, after which EXIT alerts "blind" and stops evaluating stop rules (it cannot price) |
| `LossVelocity` | `(equity_15m_ago - equity) / equity_15m_ago >= loss_velocity_pct = 0.02` over a rolling 15 min window of MTM points | 30 min | window loss below 0.5 % for 5 min | no new buys; exits allowed |
| `ExecErrors` | 3 `OrderRejected` with reason in `{tx_dropped, slippage_exceeded, quote_unavailable, rpc_error}` within 10 min | 15 min | one probe order fills (half-open admits one) | no new buys; exits allowed |

Each transition appends `BreakerTripped`/`BreakerReset` and emits an edge-triggered Notifier alert (vendor `_check_transitions` semantics, pipeline.py:334-368). Breaker state is derived from the ledger on restart so a restart cannot be used to bypass a cooldown: the reducer reconstructs `breakers{name: {state, until}}` from the last `BreakerTripped` without a later `BreakerReset`, and the supervisor's clock decides whether `until` has passed.

### 5.4 Kill switch

```
sources (checked in this order on EVERY RiskEngine.check and EVERY risk-seat cycle, max 5 s apart):
  env   : PUMPGROK_KILLSWITCH is set and not in {"", "0", "false"}          -> source=env,   reason=env value
  file  : var/KILLSWITCH exists (any size)                                  -> source=file,  reason=first line
  alert : Notifier inbound command "KILL <reason>" from an allowlisted chat id (hermes/profiles.yaml:16 telegram_token_profile chief; allowlist = alerts.telegram.allowed_chat_ids, non-empty required to enable the inbound path)
          -> the Telegram adapter writes var/KILLSWITCH with "alert:<chat_id>: <reason>" so the file source is authoritative and the switch survives restart
```

Semantics:

- Set: first observation appends `KillSwitchSet(source, reason, flatten_requested)`; `RiskEngine.check` rejects every buy with `reason=kill_switch` from that cycle on. "Within one cycle" is guaranteed because the risk seat's cadence is 5 s (section 6.2) and `check` re-reads the sources itself, so an order decided after the switch is set can never pass even if the risk seat has not ticked yet.
- Flatten: `risk.kill_switch.flatten = false` (REVIEW). When true, or when the alert command is `KILL FLATTEN <reason>`, EXIT paper-sells every open position with `reason=kill_flatten` on its next cycle (single-send per position; partial fills leave a remainder that EXIT retries on the following cycle because a sell is a new decision, not a retry of the same order).
- Clear: human only. Both `env` unset and file removed are necessary but not sufficient; the switch stays logically active until `pumpgrok killswitch clear --by human:<name> --reason "<text>"` appends `KillSwitchCleared` (`pumpgrok killswitch set --reason "<text>" [--flatten]` writes `var/KILLSWITCH`; `pumpgrok killswitch status` prints every source and the ledger state). The CLI refuses `--by` values that do not start with `human:` or that match a seat id (`bot-0N-*`), the same rule G-2 applies to `approved_by` (`check_receipt.py` in programming-desk). If any source is still set, the clear is refused and lists which.
- Audit: `KillSwitchSet`, `KillSwitchCleared`, every `OrderRejected reason=kill_switch`, and a `JournalNote` with the operator's reason are all in the ledger; the desk markdown mirror writes `FLOOR HALTED - KILL SWITCH (<source>)`.

### 5.5 Daily rollover (UTC)

At the first risk cycle after `00:00:00Z` (`clock.utc_day() != state.day_utc`):

1. `MarkToMarket` is forced (fresh prices; if PriceSource fails, `last_good` is used and the rollover is still recorded with `mtm_source=last_good`);
2. `DailyRollover` is appended with `day_start_equity_sol = equity()` including open positions at MTM and `open_positions[]`;
3. `counters.trades_today`, `rejected_today`, `fees_today_sol`, `realized_today_sol` reset;
4. open positions are untouched (vendor behaviour, risk.py:106-117: "open positions are not touched");
5. `halt` is NOT cleared. The vendor auto-resumes at the next day (`halted` recomputes from `daily_loss`, risk.py:131-134); the constitution requires an explicit human reset (`rules/pumpgrok-team.mdc:34`), so `HaltCleared` must come from the CLI. Open risk therefore carries across the rollover and counts against the new day's loss from the new `day_start_equity`.

Reports (section 8) use the `DailyRollover` boundaries, so a position opened on day 1 and closed on day 2 contributes unrealized PnL to day 1 and realized minus day-1 unrealized to day 2; the two days sum to the trade's realized PnL.

## 6. Supervisor (SPE-18030)

### 6.1 Module layout

```
src/pumpgrok/supervisor/
  __init__.py
  supervisor.py   Supervisor: builds seats from the roster, runs task-per-seat, owns shutdown
  scheduler.py    per-seat cadence, tick alignment, roster-order execution within a tick
  heartbeat.py    HeartbeatBoard: last_cycle_started/finished per seat, staleness
  restarts.py     RestartPolicy: token bucket 5/h, exponential backoff with jitter, observe-only latch
  health.py       HealthServer (vendor port) + var/health.json writer + readiness
  metrics.py      prometheus_client registry; cycle latency histograms; freshness gauges
  escalation.py   edge-triggered Escalation events -> ledger + Notifier
  lifecycle.py    install_signal_handlers, drain, cancel_and_wait (vendor ports)
```

### 6.2 Cadence per seat

| Seat | Cycle trigger | Cadence (REVIEW) | Write tools | Notes |
|---|---|---|---|---|
| bot-00-chief | timer | 60 s | none (ledger `JournalNote`, ticket files) | ticket creation, human relay; never trades |
| bot-01-scout | event-driven (PumpPortal stream) + sweep timer | stream; sweep 10 s (vendor `sweeper_delay`, monitor.py stream loop) | none | emits candidates with `correlation_id` |
| bot-02-risk | timer | 5 s | `HaltSet`, breakers, kill switch | shortest cadence: kill-switch and breaker evaluation |
| bot-03-whale | timer, per candidate | 120 s | none | holder/flow |
| bot-04-sniper | queue (approved signals) | immediate, serialised | `exec.paper_buy` | one order in flight at a time (single-send) |
| bot-05-rug | timer | 30 s | none | pre-trade safety + post-fill monitor |
| bot-06-exit | timer | 15 s (vendor `stop_loss_poll_seconds`, models.py:323) | `exec.paper_sell` | exit rules + kill flatten |
| bot-07-shill | timer | 300 s | none | detection only |
| bot-08-signal | queue (candidates with safety report) | immediate | none | scoring; LLM-backed with rule fallback |
| bot-09-journal | timer + daily | 300 s; `00:05Z` daily, Monday `00:15Z` weekly | `MarkToMarket` every 60 s, `JournalNote`, reports | export + reports |

Within one supervisor tick (`supervisor.tick_s = 1`), due seats are started in roster order (00..09) so replay ordering is stable. Each seat runs `await bot.cycle(ctx)` inside its own `asyncio.Task` with `asyncio.timeout(seat.cycle_timeout_s)` (default 4 x cadence, min 30 s); a timed-out cycle counts as a crash.

### 6.3 Heartbeats and staleness

`HeartbeatBoard` records `(started_at, finished_at, ok, duration_s)` per seat from the task wrapper, not from the bot (a bot cannot fake its own heartbeat). Staleness: `now - finished_at > 3 * cadence` (event-driven seats: `3 * sweep`) marks the seat `stale`; health goes `degraded`; an `Escalation(kind=heartbeat_stale, seat)` is emitted once (edge-triggered) and cleared when a cycle completes.

### 6.4 Bounded restarts, crash isolation, observe-only

```
on exception in bot.cycle (anything except CancelledError):
  log with correlation ids; metrics pumpgrok_bot_crashes_total{seat}
  if restart_bucket[seat].try_take():                 # capacity 5, refills 1 per 12 min (5/h)
      backoff = min(16, 2 ** attempt) + rng.uniform(0, 1)   # 1,2,4,8,16 s + jitter, attempt resets after 1 h clean
      await clock.sleep(backoff); reschedule seat
  else:
      seat.mode = observe_only                        # registry stops resolving its write tools; cycle still runs
      append Escalation(kind=bot_restart_exhausted, seat); Notifier.alert(critical)
      if seat in {bot-04-sniper}: no new buys desk-wide (nobody else can buy)
      if seat in {bot-06-exit}:  RiskEngine sets HaltSet(reason=manual, detail="exit seat observe-only")  because open positions would be unmanaged
```

A crash never propagates: the wrapper owns the task, the supervisor loop awaits `asyncio.wait(..., return_when=FIRST_COMPLETED)` over seat tasks plus the stop event (vendor pattern, pipeline.py:144-147), and a seat task finishing with an exception only triggers the policy above. Observe-only is cleared by `pumpgrok state resume --seat <seat> --by human:<name>`.

### 6.5 Graceful shutdown

SIGTERM/SIGINT -> `request_stop` (vendor semantics: second signal logs and does not force, pipeline.py:159-165) -> stop event set -> scheduler stops launching cycles -> `drain(running_cycles, grace = ops.shutdown_grace_seconds = 30)` (vendor default, models.py:382; `ops.py:406-417`) -> ledger snapshot -> JSONL export flush -> `var/health.json` `status=stopped` -> HealthServer stop -> Notifier `stopped` (vendor `notify("stopped")`, pipeline.py:181-186) -> exit 0. If open positions remain, the shutdown log and alert say so (vendor warning, pipeline.py:187-190), because stop rules do not run while the process is down. A hard kill mid-append is safe: sqlite WAL with `synchronous=FULL` and the append-before-return rule mean the ledger holds either the whole event or nothing.

### 6.6 Health signals

- `GET /healthz` -> JSON, `200` if `status == "ok"` else `503` (vendor contract, ops.py:349-355); keys are the vendor `status()` keys (pipeline.py:392-419: `status, mode, uptime_seconds, stalled, open_positions, blind_positions, trades_today, realized_pnl_sol, halted, breaker, ...`) plus `autonomy_level, ledger_status, kill_switch, breakers{...}, seats{seat: {state, last_ok_ts, stale}}, equity_sol, drawdown_pct, data_age_s`.
- `GET /readyz` -> `200` only after the ledger reconciled CONSISTENT and every seat completed one cycle.
- `GET /metrics` -> `prometheus_client` text (D5), metric families: `pumpgrok_cycle_seconds{seat}` histogram, `pumpgrok_bot_crashes_total{seat}`, `pumpgrok_orders_total{side,outcome}`, `pumpgrok_equity_sol`, `pumpgrok_drawdown_pct`, `pumpgrok_data_age_seconds{source}`, `pumpgrok_breaker_state{breaker}` (0 closed, 1 half-open, 2 open), `pumpgrok_kill_switch`, `pumpgrok_ledger_seq`.
- `var/health.json`: the `/healthz` body written atomically (vendor tmp+replace helper, state.py:76-89) every `health.file_interval_s = 10`; Hermes cron prompts and `desk_state.py` can read it without HTTP.

### 6.7 Degraded modes

| Failure | Detection | Behaviour | Recovery |
|---|---|---|---|
| LLM (x.ai) down, 5xx, 429, budget exhausted | vendor `GrokOps.precheck` + breaker (ops.py:235-297) ported into `core/llm.py` | bot-08-signal falls back to rule-based scoring (metrics-only component weights, vendor `compute_scores` with missing components = 0.0, scoring.py); if `signal.require_llm = true` (REVIEW default false for paper) the desk is observe-only for new buys; exits unaffected | breaker half-open probe succeeds |
| RPC down | tenacity retries with jitter, then failover to the next `rpc.endpoints[]` entry (D8 failover list) | after all endpoints fail: `ExecErrors` breaker counts `rpc_error`; safety checks that need RPC return `BLIND` and RISK treats BLIND as KILL for that token (constitution: missing data = KILL, agents/risk.md) | endpoint health probe every 30 s |
| PumpPortal WS down | reconnect backoff 1 -> 60 s (vendor monitor.py stream loop) | `DataStale` trips after 120 s; REST polling of open positions continues at 15 s | fresh frames |
| pump.fun REST down | httpx errors | prices from last PumpPortal tick; `DataStale` if both silent | first successful read |
| Ledger unwritable | `LedgerUnavailable` | refuse orders, bounded buffer, `Escalation(persistence_down)` (section 3.5) | append succeeds; buffer drains in order |
| Seat restart budget exhausted | restarts.py | observe-only + escalation (section 6.4) | human `seat resume` |
| Clock skew / NTP jump backwards | `clock.now() < last_event_ts - 5 s` | refuse to append (hash chain would be non-monotonic in ts), `Escalation(clock_skew)`, observe-only | clock catches up |

## 7. Live gate and autonomy level (SPE-18035)

### 7.1 Config keys (pydantic-settings, TOML overlays, env `PUMPGROK_*`)

```toml
[execution]
mode            = "paper"              # "paper" | "live"; default paper (D4)
autonomy_level  = "autonomous-paper"   # "manual-ticket" | "autonomous-paper"; live forces manual-ticket
adapter         = "paper"              # derived: paper -> PaperAdapter; live -> LiveAdapter (stub)

[live]                                  # all must hold for mode = "live"
enabled             = false            # env PUMPGROK_LIVE_ENABLE=1 also required (both, not either)
paper_started_at    = ""               # ISO date; defaults to the ledger's meta.created_ts_utc (first `pumpgrok run --mode paper`); may be set later only to a later date
min_paper_days      = 14               # D4
wallet_allowlist    = []               # base58 public keys only; never private material
max_notional_sol    = 0.0              # per-order cap; must be > 0 and <= risk.max_trade_pct_equity * equity
confirmation_path   = "var/live_confirmation.json"   # signed human confirmation record (7.3)
i_understand_the_risk = false          # the vendor CLI flag (pipeline.py:536-542) becomes a config key; CLI --i-understand-the-risk sets it

[live.thresholds]                      # evaluated from the ledger over the paper window (REVIEW)
min_closed_trades   = 50
min_win_rate        = 0.45
min_profit_factor   = 1.10
max_drawdown_pct    = 0.15
max_daily_loss_halts = 0
```

### 7.2 Preconditions and startup error

`LiveGate.validate(config, ledger) -> list[UnmetPrecondition]` runs in `cli.py` before anything else starts whenever `execution.mode == "live"`. It collects every failure (it does not stop at the first) and, if the list is non-empty, prints the block below to stderr and exits `3` (distinct from `1` config parse errors and `2` ledger inconsistent):

```
LIVE GATE: refusing to start in mode=live. 5 of 8 preconditions unmet:
  [x] live.enabled = true                       OK
  [ ] PUMPGROK_LIVE_ENABLE=1                    unset
  [ ] paper window >= 14 days                   paper_started_at=2026-10-11, elapsed 9 days
  [x] closed trades >= 50                       OK (73)
  [ ] win rate >= 0.45                          0.41
  [x] profit factor >= 1.10                     OK (1.32)
  [x] max drawdown <= 15 %                      OK (8.4 %)
  [ ] wallet_allowlist non-empty                empty
  [x] max_notional_sol in (0, 0.2]              OK (0.1)
  [ ] signed human confirmation                 var/live_confirmation.json missing
  [x] autonomy_level = manual-ticket            OK
Fix every unmet line or set execution.mode = "paper". No transaction was sent.
```

(Lines are generated from the precondition list, so the count and the `[x]/[ ]` marks are always consistent; the sample shows the shape.)

Preconditions, in evaluation order:

| # | Key | Check |
|---|---|---|
| 1 | `live.enabled` | `true` |
| 2 | env `PUMPGROK_LIVE_ENABLE` | `== "1"` |
| 3 | `live.paper_started_at`, `live.min_paper_days` | `clock.utc_day - paper_started_at >= min_paper_days` and the ledger's first `FillRecorded` is on or after `paper_started_at` |
| 4 | `live.thresholds.*` | computed from `ledger.views` over `[paper_started_at, now)` |
| 5 | `live.wallet_allowlist` | non-empty; every entry is a valid base58 32-byte public key; none appears in any G-3 secret pattern |
| 6 | `live.max_notional_sol` | `> 0` and `<= risk.max_trade_pct_equity * equity()` |
| 7 | `live.confirmation_path` | file exists, parses, signature valid (7.3), `expires_at > now`, `ledger_id` matches `meta.ledger_id` |
| 8 | `execution.autonomy_level` | `== "manual-ticket"` (autonomous live is not a supported state) |
| 9 | `live.i_understand_the_risk` | `true` (vendor flag retained, pipeline.py:536-542) |

`mode = "paper"` skips the gate entirely, and the gate result is cached on the `LiveGate` object; `LiveAdapter` re-validates on every call anyway.

### 7.3 Signed human confirmation record

```json
{
  "ledger_id": "<ULID from meta>",
  "confirmed_by": "human:<name>",
  "confirmed_at": "2026-10-30T09:12:00Z",
  "expires_at": "2026-10-31T09:12:00Z",
  "max_notional_sol": 0.1,
  "wallet_allowlist_sha256": "<sha256 of sorted allowlist>",
  "statement": "I confirm live trading with the listed wallet and cap. I have read SECURITY.md and RISK_POLICY.md.",
  "signature": "<base64 HMAC-SHA256 over the canonical JSON of the fields above, keyed by PUMPGROK_CONFIRMATION_KEY>"
}
```

`PUMPGROK_CONFIRMATION_KEY` is an operator-held secret that is never read by any seat (the registry denies it), only by `pumpgrok live confirm` (the one non-canonical subcommand this design adds; it writes the file) and `LiveGate.validate`. An HMAC rather than an asymmetric signature is sufficient because the goal is "a human with the key did this on purpose", not third-party verification (REVIEW: switch to ed25519 if external auditability is required). The record is also appended to the ledger as `ConfigChanged(keys_changed=["live.confirmation"])` with the signature, so the decision is auditable.

### 7.4 `LiveAdapter` stub and `LiveGateError`

```python
class LiveGateError(RuntimeError):
    """Raised by any live-write path when the live gate is not satisfied. Carries unmet: list[UnmetPrecondition]."""

class LiveAdapter(ExecutionAdapter):
    async def quote(...):    return await self._paper.quote(...)        # quoting is read-only; allowed
    async def simulate(...): return await self._paper.simulate(...)     # read-only; allowed
    async def place(order):  await self._audit(order, "place"); raise LiveGateError(self._gate.unmet())
    async def cancel(id):    await self._audit(None, "cancel"); raise LiveGateError(self._gate.unmet())
```

`_audit` appends `LiveWriteAttempted(adapter="live", method, caller_seat, gate_result)` before raising, so an attempt is recorded even though nothing happened. Under D3 no seat can resolve a live-write tool from the registry in the first place, so reaching `LiveAdapter.place` already means a registry bug; the ledger event plus a critical Notifier alert makes that visible. There is no code path in `LiveAdapter` that builds, signs or sends a transaction (D4); the six-step vendor TODO (executor.py:151-162) is not carried over.

### 7.5 Autonomy level: manual-ticket vs autonomous-paper

Both exist in paper mode; live mode allows only `manual-ticket`.

| | `manual-ticket` | `autonomous-paper` |
|---|---|---|
| Who approves a buy | the human, by posting the exact phrase | RiskEngine `check` passing is the approval |
| Exact phrase | `approve <ticket> <mint> <size> <slippage>` where ticket matches `SOL-\d{8}-\d{3}` (`tools/desk_state.py:32`), mint is the base58 CA, size in SOL, slippage in bps; constitution: `rules/pumpgrok-team.mdc:28`, `agents/chief.md:49`, `agents/sniper.md:27` ("until the human writes a higher autonomy level in the journal") | not required; the ticket is still created with `Status: AUTO_APPROVED_PAPER` and the `OrderPlaced.approval` says `kind=autonomous-paper, approved_by=bot-02-risk` |
| Where the approval is recorded | `ApprovalRecord` in the ledger (`JournalNote` with `refs=[ticket]` plus `OrderPlaced.approval{kind=human, approved_by="human:<telegram user>", phrase_hash}`); the phrase is matched token-for-token against the ticket, mismatch -> `OrderRejected reason=approval_mismatch` | `OrderPlaced.approval{kind=autonomous-paper}` |
| Switching | `pumpgrok state autonomy autonomous-paper --by human:<name>` appends `ConfigChanged` and a `JournalNote` (satisfying "writes a higher autonomy level in the journal", agents/sniper.md:27); setting it back is immediate | same command |
| Purpose | the Telegram human-in-the-loop desk as it exists today | the 2-4 week unattended paper run that produces the live-gate statistics |

Everything else (sizing caps, kill switch, breakers, halts, single-send, ledger) is identical between the two levels; `autonomy_level` only changes step 5 of `RiskEngine.check`.

## 8. Reporting

### 8.1 Module layout and CLI

```
src/pumpgrok/reporting/
  __init__.py
  daily.py      DailyReport.build(ledger, day_utc) -> ReportModel
  weekly.py     WeeklyReport.build(ledger, iso_week) -> ReportModel
  render.py     markdown renderer (ASCII tables, no emoji; passes scripts/check.sh)
  templates/daily.md.j2, weekly.md.j2    (jinja2 is NOT in D5; use str.format templates in render.py; the .j2 names are not used)
```

CLI (`src/pumpgrok/cli.py`, exposed as `pumpgrok`):

```
pumpgrok report --daily  [--day 2026-10-20] [--out var/reports] [--desk]
pumpgrok report --weekly [--week 2026-W43]  [--out var/reports] [--desk]
```

`--desk` additionally copies the file to `$PUMPGROK_DESK/journal/report-daily-YYYY-MM-DD.md` (or `report-weekly-YYYY-Www.md`), resolved exactly as `tools/desk_state.py:50-57` resolves the desk. bot-09-journal runs the daily build at `00:05Z` and the weekly at Monday `00:15Z` and posts a five-line summary through the Notifier.

### 8.2 CLI surface used by this design (canonical names)

Every subcommand is a thin wrapper over a registry tool (`<ns>.<verb>` names per docs/TOOL_CATALOG.md); the CLI adds no logic of its own.

| Subcommand | Wraps | Section |
|---|---|---|
| `pumpgrok run --mode paper [--once] [--replay <dir>] [--record <dataset> --duration <t>]` | supervisor start; `--once` = one tick (Hermes cron wrappers); `--replay` binds FixtureClock + fixture sources; `--record` wraps transports | 4.4, 6 |
| `pumpgrok verify --ledger [--explain]` / `--fixture <dataset>` | `ledger.verify`, `replay.verify` | 3.5, 4.6 |
| `pumpgrok doctor` / `pumpgrok audit` | health + readiness probe; receipt/ownership checks (programming-desk `desk_cli.py` precedent) | 6.6 |
| `pumpgrok report --daily|--weekly [--day|--week] [--out] [--desk]` | `journal.report` | 8.1 |
| `pumpgrok paper buy|sell --ticket --mint --size-sol|--token-amount --slippage-bps` | `exec.place` through PaperAdapter (manual-ticket path) | 2 |
| `pumpgrok killswitch set|clear|status` | `risk.kill_switch` | 5.4 |
| `pumpgrok state status|halt [--clear] |autonomy <level>|resume --seat <seat>` | `portfolio.state`, `risk.halt`, `ConfigChanged` | 5.2, 5.5, 6.4, 7.5 |
| `pumpgrok replay trim|rebuild-ticks --dataset <name>` | `replay.trim`, `replay.rebuild_ticks` | 4.3, 4.6 |
| `pumpgrok live confirm` | writes the signed confirmation record (operator-only; needs `PUMPGROK_CONFIRMATION_KEY`) | 7.3 |
| `pumpgrok ticket next|create|list`, seat verbs (`scout discover|pipeline`, `risk audit`, `chief pickup`, `rug watch`, `journal rollup`) | owned by other nodes; listed for completeness | - |

### 8.3 Report content

Both reports have the same sections; the weekly one adds a per-day table and the live-gate threshold status.

```
# PumpGrok paper report - daily - 2026-10-20 (UTC)
Mode: paper | Autonomy: autonomous-paper | Ledger: <ledger_id> seq <n> | Equity: 10.213 SOL (+2.13 % since start)

## Summary            trades (buys/sells), closed, win rate, realized PnL, unrealized PnL, fees (venue/network), equity start/end, max drawdown (day and since start), daily loss vs halt
## Trades             table per closed position: ticket, mint (short), entry/exit price, size, hold, reason, pnl_sol, pnl_pct, fees, correlation_id
## Open positions     table: mint, entry, mtm, unrealized, age, mtm_source
## Rejected signals   table: reason -> count (every OrderRejected.reason); top 5 mints by rejections
## Safety outcomes    RUG verdicts CLEAR/CONDITIONAL/KILL/BLIND counts (from JournalNote refs), post-fill alerts
## Risk events        HaltSet/HaltCleared, KillSwitchSet/Cleared, BreakerTripped/Reset with timestamps and who cleared
## Bot health         per seat: cycles, crashes, restarts, observe-only periods, p50/p95 cycle seconds
## Data freshness     per source: max age, stale seconds total, DataStale trips
## Live gate          (weekly only) each threshold with current value and OK/unmet
## Unverified         anything computed from last_good prices, or days with ledger_inconsistent
```

Rendering is pure: `ReportModel` is built from ledger views and the renderer has no I/O, so `tests/test_reporting_render.py` can snapshot-test the markdown from a fixture ledger.

## 9. Test list

All tests are pytest with `asyncio_mode = auto` (D5), use `FixtureClock` and the seeded RNG, and never touch the network (`tests/conftest.py` installs an `httpx` transport that raises on any un-mocked request, plus a `websockets.connect` monkeypatch, the vendor test pattern `tests/test_filter.py` FakeWebSocket).

| File | What it asserts |
|---|---|
| `tests/execution/test_paper_fill_model.py` | `curve_math` invariants (`k` constant after buy and sell, `impact_buy == x/S`, `buy_out` then `sell_out` round-trips within fee); the worked example of section 2.9 to 6 significant figures (full fill at S1=42.1, `slippage_exceeded` at S1=42.5, partial at size 1.5); `below_liquidity_floor` when `S0 < 10 * size`; `tx_dropped` when the seeded draw says so, with no cash change; fee split equals `venue_fee + base + priority + tip`; `cancel` succeeds in ACCEPTED and fails after latency; `simulate` writes no ledger events |
| `tests/ledger/test_ledger_restart_reconcile.py` | append N events, kill the writer mid-way (simulated by closing the connection), reopen: chain verifies, snapshot + tail equals full replay; tamper one `payload_json` via a raw connection with triggers dropped -> `INCONSISTENT`, `HaltSet(ledger_inconsistent)` appended, `RiskEngine.check` rejects; duplicate `idempotency_key` -> `IntegrityError` surfaced as a refused order; views (cash, positions, realized, unrealized, equity curve, drawdown) match hand-computed numbers from a 6-event fixture; JSONL export resumes from `meta.export_seq` without duplicates; vendor-shape `trades.jsonl` lines validate against the key sets of `log.py:98-183` |
| `tests/replay/test_replay_determinism.py` | two runs over `smoke-10m` give identical `events.hash` sha256, identical JSONL bytes, identical final state; a run with a different seed differs (so the seed is actually wired); a fixture with a 180 s hole trips `DataStale` at the right virtual time |
| `tests/risk/test_kill_switch_one_cycle.py` | set env / create file / inject alert command in three parametrised cases; advance `FixtureClock` by one risk cadence (5 s); assert zero `FillRecorded side=buy` after the set time, `KillSwitchSet` present with the correct source; with `flatten=true` every open position has a `PositionClosed reason=kill_flatten`; `killswitch clear --by bot-02-risk` refused, `--by human:alice` accepted only after all sources are clear |
| `tests/execution/test_live_gate_fails_fast.py` | parametrised over each of the 9 preconditions removed one at a time: `cli.main(["run", "--mode", "live"])` exits `3` and stderr lists exactly that line as `[ ]`; all present -> `LiveAdapter` is constructed and `place` still raises `LiveGateError` when the gate object is given a stale confirmation; default config (`pumpgrok run` with no `--mode`) yields `mode == "paper"` and the gate is never evaluated; `LiveWriteAttempted` appended on every `place`/`cancel` |
| `tests/supervisor/test_supervisor_bounded_restart.py` | a seat whose `cycle` raises every time is restarted 5 times within a virtual hour with backoff 1,2,4,8,16 (+jitter in [0,1)), then latched observe-only with one `Escalation(bot_restart_exhausted)`; other seats keep ticking (heartbeats advance); SIGTERM handler: stop event -> drain -> snapshot written -> `health.json status=stopped` -> return 0; `/healthz` 503 while a seat is stale and 200 after it recovers |
| `tests/risk/test_breaker_trip_and_cooldown.py` | for each breaker: trip condition met -> `BreakerTripped`, buys rejected `breaker_open:<name>`, sells allowed; clock advanced past cooldown -> half-open admits exactly one probe; probe failure re-opens without a new cooldown reset; `reset_after_ok` successes -> `BreakerReset`; breaker state survives a ledger restart (reconstructed from events) |
| `tests/soak/test_soak_multiday_replay.py` (marked `slow`, nightly) | replay `soak-3d`: `tracemalloc` samples every virtual hour, peak RSS growth after the first hour is under 20 MB (REVIEW); `sys.excepthook` and `loop.set_exception_handler` wired to fail the test on any unhandled exception; at least one `DailyRollover` per day; ledger verifies at the end; report renders for each day |
| `tests/reporting/test_reporting_render.py` | daily and weekly markdown snapshot from a fixture ledger; ASCII only; every section header present; rejected-reason table sums to `count(OrderRejected)` |
| `tests/characterization/test_vendor_ports.py` | vendor behaviour pinned before porting: `price_from_reserves` on the three payload shapes (executor.py:85-97), `exit_signal` priority and boundaries (risk.py:238-280), `RiskManager.position_size` (risk.py:145-149), `CircuitBreaker` half-open (ops.py:131-182), `parse_create_event` timestamp heuristics (monitor.py:61-83); the same cases run against the ported modules |

## 10. Shared interfaces this design depends on

Defined in `src/pumpgrok/core/interfaces.py` (docs/design/interfaces.md, node n3): `Tool`, `Skill`, `Bot` (`cycle(ctx)`), `ExecutionAdapter`, `DataSource`, `ToolRegistry.find(capability, max_side_effect, bot_permissions)`, `Notifier` (`alert(severity, text, **fields)`, `notify(event, ...)`, inbound `commands()` async iterator for the alert-channel kill command). This document adds `PriceSource`, `Clock` and `LedgerStore` and expects n3 to re-export them from `core/interfaces.py`.

## 11. Contradictions found with D1-D9 (reported, not resolved)

1. D9 / vendor halt semantics: the vendor auto-clears the daily-loss halt at the next UTC day (`risk.py:106-117`, `:131-134`); the constitution requires an explicit human reset (`rules/pumpgrok-team.mdc:34`). This design follows D9; the characterization test for `RiskManager.halted` must therefore be marked as "vendor behaviour, intentionally not ported".
2. D6 "5% daily loss halt" vs vendor `daily_loss_limit_sol = 2.0` absolute SOL (`models.py:319`): the vendor limit is absolute, D6 is a percentage of equity. Design uses the percentage; the absolute SOL knob is dropped.
3. D6 "10x liquidity floor" and "partial fill above 2 % of pool liquidity" interact (section 2.6): only sizes up to `S/50` fill fully; sizes in `(S/50, S/10]` always partially fill. With 10 SOL equity and 2 % sizing (0.2 SOL) a full fill needs `S >= 10 SOL`; pump.fun curves start at 30 SOL virtual so this is workable, but the operator should know most early-curve orders will be partial if the equity is raised.
4. Writing contract (ASCII only) vs constitutional strings: `FLOOR HALTED <U+2013> DAILY LOSS LIMIT` (`rules/pumpgrok-team.mdc:34`) and `UNKNOWN RESULT <U+2013> reconcile by signature` (`:30`) contain an en dash (U+2013), which cannot be reproduced in this ASCII-only document. The code constants must carry the constitution's bytes; `scripts/check.sh` only rejects emoji ranges, not dashes, so the source files pass.
5. D8 "venues kept exactly as integrated today" vs post-graduation CPMM fills: no current data source exposes Raydium/PumpSwap reserves, so post-graduation paper fills cannot be modelled from live data; the design rejects such orders (`post_graduation_no_reserves`) rather than add a venue client. Positions that graduate while open are marked `last_good` for MTM until EXIT closes them on the last pre-graduation tick or by `max_hold`.
6. D5 lists no templating library; section 8 therefore uses `str.format` templates, not jinja2.
7. `tools/pipeline_evidence.py --candidates` filters `tx_hash == "dry_run"` (equality); the ledger's `venue_tx_ref` is `dry_run:<ULID>` to keep paper refs unique. The tools port (n2) must change the filter to a prefix match, or the export must emit the bare `dry_run` string and put the ULID in a new field. Design chooses the latter for the vendor-shape export (bare `dry_run` in `tx_hash`, ULID in `venue_tx_ref`) so no tool change is forced.

## Unverified Items

| # | Unknown | Default assumed in this design |
|---|---|---|
| 1 | pump.fun venue fee is exactly 100 bps on both buy and sell for the current program version | `venue_fee_bps = 100` (REVIEW) |
| 2 | pump.fun initial virtual reserves (30 SOL / 1,073,000,000 tokens) used in the worked example | used only for the example; the adapter reads reserves from the data source |
| 3 | pump.fun REST `/coins/{mint}` exposes a `complete` boolean for graduation; the vendor only reads `virtual_sol_reserves`, `virtual_token_reserves`, `market_cap`, `usd_market_cap` (executor.py:86-96) | graduation detected by `complete` if present, else by `S >= CURVE_COMPLETION_SOL = 85` (monitor.py:30) |
| 4 | PumpPortal trade frames carry `vTokensInBondingCurve` alongside `vSolInBondingCurve` (vendor reads only the SOL side, monitor.py:155) | recorder captures the raw frame; `ticks.jsonl` falls back to REST `virtual_token_reserves` when the WS field is absent |
| 5 | Compute units consumed by a pump.fun buy/sell for the priority-fee cost | `compute_units = 200_000` (REVIEW) |
| 6 | Post-graduation pool fee (Raydium 25 bps vs PumpSwap) | `cpmm_fee_bps = 25` (REVIEW); fills rejected anyway for lack of reserves (section 11.5) |
| 7 | Confirmation latency distribution on Solana mainnet for priority-fee'd pump.fun swaps | lognormal median 1.2 s, sigma 0.5, clip [0.4, 20] s; `p_drop = 0.02` (REVIEW) |
| 8 | Whether a `slippage_exceeded` failure on-chain still pays base + priority fee | charged (REVIEW); `tx_dropped` not charged |
| 9 | Telegram inbound command availability: `hermes/profiles.yaml:16,29` give only chief a token and inbound; the Notifier inbound path for `KILL` assumes that bot can receive commands | alert-command source enabled only when `alerts.telegram.allowed_chat_ids` is non-empty; env and file sources always work |
| 10 | Nightly CI artifact store for `soak-3d` | named in `.github/workflows/ci.yml` by n5/n8; the soak test skips with a clear reason if the dataset is absent |
| 11 | Exact event-count scale per day for snapshot cadence | 500 events / 300 s (REVIEW) |
| 12 | Live-gate performance thresholds (`min_closed_trades 50`, `win_rate 0.45`, `profit_factor 1.10`, `max_drawdown 15 %`, `daily_loss_halts 0`) | as listed (REVIEW); they gate nothing in paper mode |
| 13 | HMAC vs asymmetric signature for the human confirmation record | HMAC-SHA256 with `PUMPGROK_CONFIRMATION_KEY` (REVIEW) |
| 14 | `daily_loss_basis` total (realized + unrealized) vs realized-only (vendor) | total (REVIEW) |
| 15 | Soak memory bound | 20 MB growth after warm-up over three virtual days (REVIEW) |
