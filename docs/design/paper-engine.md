# Paper Engine, Ledger, Replay, Risk, Supervisor and Live Gate Design

Tracker: SPE-17998 https://linear.app/swcstudio/issue/SPE-17998/n4-paper-engine-ledger-replay-riskbreakers-supervisor-live-gate-design | Notion https://app.notion.com/p/3ffbc1a0c7ae81fd8a30fb490682c0c2?pvs=204

Node n4 of ultrathink graph ut-mvgfr96y-be17fc96. Steps SPE-18025 (extend-vs-build), SPE-18024 (PaperAdapter), SPE-18026 (ledger), SPE-18029 (replay), SPE-18028 (risk and breakers), SPE-18030 (supervisor), SPE-18035 (live gate).

This document is a design only. It names module paths under `src/pumpgrok/`, data schemas, formulas, state machines, failure handling and the tests that prove each subsystem. Every repository fact cites `file:line` of the current tree (branch `feat/grokbot-desk-merge`). Inferences are tagged `[INFERENCE]`. Every numeric default that a human must confirm before the first paper run is tagged `REVIEW`.

Fixed decisions D1-D9 from the orchestrator are taken as given. Where the vendored engine behaves differently from a decision, the difference is recorded in section 11 and in the closing summary; it is not resolved here.

## 0. Scope and reading order

| Section | Subsystem | Module root (R31) | Owner | Primary tests |
|---|---|---|---|---|
| 1 | Existing code: what to extend, what to build | (survey) | | characterization tests |
| 2 | PaperAdapter fill model | `src/pumpgrok/execution/{paper_adapter,curve_math,fees,latency}.py` | bot-04-sniper | `test_paper_fill_model.py` |
| 3 | Ledger (sqlite WAL, hash chain, snapshots, reconcile, JSONL export) | `src/pumpgrok/ledger/{store,events,reducer,views,reconcile,export,desk_bus}.py` | bot-02-risk | `test_ledger_restart_reconcile.py`, `test_single_writer_concurrent_appends.py` |
| 4 | Replay (Clock, RNG, fixtures, recorder, determinism) | `src/pumpgrok/replay/{clock,rng,fixtures,sources,recorder,runner}.py` | bot-02-risk | `test_replay_determinism.py` |
| 5 | Risk engine, breakers, kill switch | `src/pumpgrok/risk/{engine,limits,sizing,breakers,killswitch}.py` (class `RiskEngine`) | bot-02-risk | `test_kill_switch_one_cycle.py`, `test_kill_switch_in_flight.py`, `test_breaker_trip_and_cooldown.py` |
| 6 | Supervisor | `src/pumpgrok/supervisor/{scheduler,seat_task,health,metrics}.py` | bot-00-chief | `test_supervisor_bounded_restart.py` |
| 7 | Live gate and autonomy level | `src/pumpgrok/config/`, `src/pumpgrok/execution/live/{live_adapter,live_gate}.py` | bot-02-risk (rule after `execution/**`) | `test_live_gate_fails_fast.py`, `test_live_gate_rejects_replay_ledger.py` |
| 8 | Reporting | `src/pumpgrok/reporting/{daily,weekly,render}.py` | bot-09-journal | `test_reporting_render.py` |
| 9 | Test list | `tests/` | | all |
| 10 | Shared interfaces and the full module placement table | `src/pumpgrok/core/{interfaces,registry,ids,approvals}.py` | bot-02-risk | (owned by docs/design/interfaces.md) |
| 11 | Contradictions found with D1-D9 | | | |
| 12 | Unverified Items | | | |

Exit rules (`src/pumpgrok/engine/exits.py`, `ExitSignal`, owned by bot-06-exit) and the position watcher (`src/pumpgrok/engine/watcher.py`, `PositionWatcher`, owned by bot-05-rug) are referenced here but designed under the engine port (R31).

Shared vocabulary used throughout:

- `S` = virtual SOL reserve of a pump.fun bonding curve, an integer in lamports. `T` = virtual token reserve, an integer in token base units (6 decimals). `k = S * T`. Prices are `Decimal` lamports per token base unit (R28). SOL figures in prose are for readability only.
- `equity` = cash + sum of mark-to-market value of open positions, in lamports. Paper equity starts at `paper_equity_sol = 10` (D6, R20, REVIEW), converted once to 10_000_000_000 lamports.
- `cycle` = one scheduled run of one seat's `Bot.cycle()` under the supervisor.
- `correlation_id` = ULID from `core/ids.py` (`IdFactory(clock, rng)`, R29) assigned when a candidate token first enters the desk; every downstream event (signal, safety report, order, fill, exit, journal) carries it (D5 contextvars). `decision_id` = ULID minted per trading decision (R23); `order_id` = ULID per order.
- `source` = the ledger provenance column, one of `paper` (live-paper run), `replay` (fixture run), `manual` (CLI-originated human records) (R21, R32).

## 1. Existing code: extend vs build (SPE-18025)

The vendored engine is a complete dry-run screening loop with a position watcher, a day-scoped risk manager and ops primitives. The root `tools/` are stateless CLIs over a markdown file bus. Neither has a fill model, a ledger, a replay harness, a supervisor or a live gate. The table below is the authoritative extend-vs-build decision for n4; every "extend" row lands as a port into `src/pumpgrok/` with a characterization test that pins the vendor behaviour before any change (D2: vendor removed only when zero inbound refs remain). Target modules follow R31.

| Capability | Vendor / root code today | Evidence | Decision | Target module |
|---|---|---|---|---|
| Spot price from curve reserves | `price_from_reserves` divides `virtual_sol_reserves/1e9` by `virtual_token_reserves/1e6`, falls back to `market_cap/TOTAL_SUPPLY` | `vendor/grokbot-pumpfun/src/executor.py:85-97`, `TOTAL_SUPPLY = 1_000_000_000.0` at `:28` | EXTEND: port as `CurveQuote.spot()` on integer reserves (R28); add the constant-product fill on top | `execution/curve_math.py` |
| Dry-run buy | `token_amount = size_sol / price`, no fee, no impact, no latency, `tx_hash = "dry_run"` | `executor.py:103-124`, `DRY_RUN_TX = "dry_run"` at `:30` | REPLACE with PaperAdapter (section 2). Keep `"dry_run"` as the bare `tx_hash` of the vendor-shape export so `tools/pipeline_evidence.py --candidates` (filters `tx_hash == dry_run`) keeps matching | `execution/paper_adapter.py` |
| Dry-run sell | `proceeds = token_amount * price if price > 0 else 0.0` | `executor.py:126-134` | REPLACE (same) | `execution/paper_adapter.py` |
| Live executor | `LiveExecutor.buy/sell` raise `NotImplementedError` with a six-step TODO; `build_executor` selects it when `config.is_live` | `executor.py:137-172`, `:175-180` | REPLACE with `LiveAdapter` stub raising `LiveGateError` (section 7). No solders/solana imports exist in executor.py today; none are added | `execution/live/live_adapter.py` |
| Position model | `Position(mint, symbol, creator, entry_price, peak_price, sol_spent, token_amount, opened_at, tx_hash, score)` | `vendor/grokbot-pumpfun/src/models.py:243-255` | EXTEND: ledger `Position` view adds `fees_lamports`, `cost_basis_lamports`, `filled_fraction`, `correlation_id`, `ticket_id`, `mtm_frozen`; vendor fields kept with the same names for the export mapping (section 3.7), float money replaced by integers (R28) | `ledger/views.py` |
| Day-scoped risk state | `RiskManager` holds `day, trades_today, realized_pnl_sol, positions, grok_calls_today`; `roll_day_if_needed` zeroes counters at UTC midnight; `halted` = `daily_loss >= daily_loss_limit_sol` and auto-clears on the next day | `vendor/grokbot-pumpfun/src/risk.py:39-134`, roll at `:106-117`, `halted` at `:131-134` | EXTEND the limit checks (`evaluate` at `:151-178`) into `RiskEngine.check` (class renamed, R31); REPLACE the state holder with ledger-derived views; REPLACE auto-clear of the halt with human-only clear (D9, R5, constitution `rules/pumpgrok-team.mdc:34`) | `risk/engine.py` |
| Position sizing | `min(max_sol_per_trade * score, remaining_loss_budget * 0.30)`, `MIN_TRADE_SOL = 0.01` | `risk.py:145-149`, constants `:33,:36` | EXTEND: keep as the proposal sizer in lamports; `RiskEngine.check` caps it by the R20 fractions | `risk/sizing.py` |
| Exit rules | `exit_signal` priority stop_loss -> take_profit -> trailing_stop -> max_hold; trailing only above entry | `risk.py:216-280`, defaults `RiskConfig` at `models.py:318-328` (stop 30 %, TP 120 %, trail 35 %, hold 3600 s, poll 15 s) | EXTEND: port verbatim into the exit seat's rule engine (owned by bot-06-exit; out of n4 scope except that EXIT's paper sells flow through PaperAdapter and each rule needs a per-ticket `exit_rule` approval under manual-ticket, R17) | `engine/exits.py` |
| Position watcher | polls `price_fn` every `stop_loss_poll_seconds`, persists peak every +1 %, `BLIND_AFTER = 3` misses | `risk.py:283-382` | EXTEND: becomes the exit seat's cycle under the supervisor; `blind` feeds the DataStale breaker and the `blind_flatten` policy (R25) | `engine/watcher.py` |
| Persistence | `PipelineState` JSON written atomically (tmp + fsync + `os.replace`), corrupt file moved to `.corrupt` | `vendor/grokbot-pumpfun/src/state.py:32-45`, `:48-92` | REPLACE with sqlite WAL ledger (section 3). The atomic-write helper is ported into `ledger/store.py` and reused for `var/health.json`, JSONL export and every markdown export (R26) | `ledger/store.py` |
| Trade log JSONL | `TradeLog.buy/skip/close` records with `ts`, `mode`; size rotation | `vendor/grokbot-pumpfun/src/log.py:90-183` | EXTEND: the JSONL export writes the same three record shapes so `tools/pipeline_evidence.py` and vendor `scripts/dashboard.py` keep reading them | `ledger/export.py` |
| Rate limiter | token bucket `RateLimiter(per_minute, burst)` | `vendor/grokbot-pumpfun/src/ops.py:90-128` | EXTEND: port into `core/ratelimit.py`; used per data source and per LLM client; waits via `clock.sleep` (R27) | `core/ratelimit.py` |
| Circuit breaker | `CircuitBreaker(failures, cooldown)`: consecutive failures open it, cooldown elapsed -> half-open with one probe | `ops.py:131-182` | EXTEND: port as the base class for the three risk breakers; add hysteresis (section 5.3) | `risk/breakers.py` |
| Daily call budget | `CallBudget(max_per_day)` resets at UTC midnight | `ops.py:187-229` | EXTEND: port into `core/budget.py` for the LLM client budget; unchanged | `core/budget.py` |
| Metrics | in-memory counters/gauges with hand-rolled Prometheus text | `ops.py:41-86` | REPLACE with `prometheus_client` (D5); keep the metric names as a compatibility layer | `supervisor/metrics.py` |
| Health server | raw asyncio HTTP `/healthz` (200/503 on `status == "ok"`) and `/metrics` | `ops.py:299-358` | EXTEND: keep the two routes and the status contract, add `/readyz`, serve `prometheus_client` text | `supervisor/health.py` |
| Heartbeat, drain, signals | log heartbeat; `drain(tasks, grace)`; `install_signal_handlers` for SIGINT/SIGTERM; `cancel_and_wait` | `ops.py:372-404`, `:406-417`, `:420-431`, `:434-440` | EXTEND: supervisor reuses drain/signal/cancel helpers; heartbeat becomes per-seat in the task wrapper | `supervisor/scheduler.py`, `supervisor/seat_task.py` |
| Edge-triggered alerts | `_check_transitions` alerts once on breaker/halted/stalled/blind edges | `vendor/grokbot-pumpfun/src/pipeline.py:334-368` | EXTEND: same edge semantics for the supervisor's escalation events and the Escalation -> notify.alert relay | `supervisor/seat_task.py` |
| Status snapshot | `Pipeline.status()` JSON with `status`, `mode`, `stalled`, `open_positions`, `halted`, `breaker`, ... | `pipeline.py:392-419`, `STALL_SECONDS = 600` | EXTEND: superset, same keys kept | `supervisor/health.py` |
| Live warning and flag | `LIVE_WARNING` printed; `SystemExit` without `--i-understand-the-risk`; `Config.problems` requires wallet key + https RPC | `pipeline.py:490-543` | REPLACE with the live gate (section 7, the nine R21 preconditions); the vendor flag and the wallet-key requirement are not carried (D4: no key material) | `execution/live/live_gate.py` |
| Monitor create/trade events | reads `vSolInBondingCurve`, `marketCapSol`, `traderPublicKey`, `txType`; `CURVE_COMPLETION_SOL = 85.0` | `vendor/grokbot-pumpfun/src/monitor.py:61-83` (create), `:155-159` (trade updates), `:30` | EXTEND: the recorder (section 4.4) captures the raw payloads this parser consumes | `engine/monitor.py`, `replay/recorder.py` |
| Paper fill logger | `append_paper_fill` appends a markdown bullet block to `<desk>/journal/paper-YYYY-MM-DD.md`; price and size are CLI arguments; slippage recorded, not applied | `tools/paper_sim.py:25-43` | REPLACE: becomes `pumpgrok paper buy|sell --ticket --mint --size-sol --slippage-bps --approval-id` (thin wrapper over `exec.place` via PaperAdapter; `--size-sol` is converted to lamports at the CLI boundary) over the ledger; the markdown block format is kept as one export target (section 3.6) | `cli.py`, `ledger/export.py` |
| Desk halt | `write_halt` rewrites `desk.md` `Halt: true` and appends `FLOOR HALTED - <reason> @ <ts>` plus a journal line | `tools/desk_state.py:195-210`; `HALT_RE` at `:36`; `parse_desk_md` treats any `FLOOR HALTED` text as halt at `:76-77` | EXTEND: `HaltSet` ledger events also write this file (tmp + `os.replace`, R26) so Hermes cron prompts (which gate on `desk_state.py status`) go `[SILENT]` | `ledger/desk_bus.py` |
| Jupiter quote fields | `otherAmountThreshold`, `priceImpactPct`, `slippageBps` passed through | `tools/jupiter_quote.py:45-48` | EXTEND: the core `Quote` model keeps the same names (snake_case); Jupiter quotes are informational, never the fill price (R38) | `core/interfaces.py` (`Quote`) |
| Priority fee | `recommended_micro_lamports` = percentile fee x multiplier; note says micro-lamports per compute unit | `tools/priority_fee.py:75-81` | EXTEND: fee model consumes this field, capped by `max_micro_lamports` | `execution/fees.py` |
| Scheduler | none in code; Hermes cron prompts every 15-60 min | `hermes/cron/jobs.yaml` (6 jobs) | BUILD supervisor (section 6) | `supervisor/` |
| Ledger, replay, kill switch, live gate | none | (grep `sqlite|replay|kill|LiveGate` in vendor src and tools: no hits besides `scripts/replay.py`, which summarises the JSONL log and does not replay events) | BUILD | sections 3, 4, 5.4, 7 |

## 2. PaperAdapter (SPE-18024)

### 2.1 Module layout

```
src/pumpgrok/execution/
  __init__.py
  curve_math.py      pure integer functions: spot, buy_out, sell_out, impact (no I/O)
  fees.py            FeeModel: venue fee, base fee, priority fee (lamports)
  latency.py         LatencyModel: seeded confirmation latency
  paper_adapter.py   PaperAdapter(ExecutionAdapter): quote, simulate, place, cancel, positions; in-flight barrier
  live/
    live_adapter.py  LiveAdapter(LiveAdapterStub): every method raises LiveGateError (section 7.4)
    live_gate.py     LiveGate.check() (section 7.2)
```

Four files plus the `live/` subpackage, exactly as R31 places them; `Quote` and the `ExecutionAdapter` protocol live in `core/interfaces.py` (docs/design/interfaces.md 2.7), so there is no `quote.py` or `adapter.py` here. `ExecutionAdapter` has five methods: `quote(input_mint, output_mint, amount, slippage_bps) -> Quote`, `simulate(order) -> SimulationResult`, `place(order) -> Fill`, `cancel(order_id, ticket_id, decision_id) -> bool`, `positions(mint) -> Sequence[Position]`. PaperAdapter implements all five; `simulate` and `place` share one code path, the only difference being that `place` appends ledger events and `simulate` does not.

Both adapters consume prices through one interface (all integers; `Decimal` only for the derived price):

```python
class PriceSource(Protocol):
    async def curve(self, mint: str) -> CurveState | None: ...
    # CurveState(mint, s_lamports: int, t_units: int, complete: bool, source_ts: float, source: str)
    async def spot(
        self, mint: str
    ) -> Decimal | None: ...  # lamports per token base unit; None if unknown
```

Live-paper mode binds `PriceSource` to the pump.fun REST client (`/coins/{mint}` fields `virtual_sol_reserves`, `virtual_token_reserves`, executor.py:85-90) with the PumpPortal trade stream as a faster update path (`vSolInBondingCurve`, monitor.py:155-157). Replay mode binds it to the fixture feed (section 4). PaperAdapter does not know which.

### 2.2 Curve math (pure, `curve_math.py`)

Pre-graduation pump.fun is a constant-product curve on virtual reserves. All inputs and outputs are integers in base units (R28): `S` is `virtual_sol_reserves` in lamports, `T` is `virtual_token_reserves` in token base units (6 decimals), `x` is lamports in, `t` is token units in; divisions floor (`//`), and the only `Decimal` values are the derived price and impact.

```
spot(S, T)            = Decimal(S) / Decimal(T)                lamports per token base unit
buy_out(S, T, x)      = T * x // (S + x)                       token units received for x lamports (net of venue fee)
price_avg(S,T,x)      = Decimal(x) / Decimal(buy_out(S,T,x))
impact_buy(S, x)      = Decimal(x) / Decimal(S)                fraction
sell_out(S, T, t)     = S * t // (T + t)                       lamports received (gross of venue fee) for t token units
impact_sell(T, t)     = Decimal(t) / Decimal(T + t)
post_buy(S, T, x)     = (S + x, T - buy_out(S,T,x))            reserves after the fill
```

The vendor divides `virtual_sol_reserves/1e9` by `virtual_token_reserves/1e6` to get SOL per token (executor.py:89-91); the ported `CurveQuote.spot()` characterization test converts the integer `spot` back to that unit (`x 1e3`) and matches the vendor to 12 significant figures. The fallback `market_cap / TOTAL_SUPPLY` (executor.py:93-96) is used only to produce a `spot` for mark-to-market when reserves are absent; it never produces a fill, because a fill without reserves has no impact model (`OrderRejected reason=no_reserves`).

Graduation (R8, R38): the vendor treats the curve as complete at `CURVE_COMPLETION_SOL = 85.0` (monitor.py:30) and the REST payload carries `complete` [INFERENCE: field name from pump.fun frontend API, not read by vendor code]. Post-graduation venues are not modelled: D8 keeps data sources exactly as integrated today and none of them exposes post-graduation pool reserves. Therefore:

- a BUY whose `CurveState.complete` is true at decision time or at `CONFIRMING` is rejected `OrderRejected reason=post_graduation_no_reserves`;
- an OPEN position whose token graduates (the first tick with `complete == true`, or `S >= CURVE_COMPLETION_SOL` when `complete` is absent) is force-closed by the adapter at the last pre-graduation curve price (`sell_out` on the last `complete == false` reserves, net of venue fee) with `PositionClosed reason=graduated`; its MTM is frozen at that value (`mtm_frozen = true`) and no further `MarkToMarket` entry is produced for it. No order and no approval is involved; the close is adapter-internal and appends `Escalation(kind=graduated)`;
- a SELL on a graduated token is impossible because the position no longer exists.

This is a documented limitation (section 11.5): paper results stop at graduation.

### 2.3 Fee model (`fees.py`)

All lamports, integer arithmetic with flooring:

```
venue_fee_lamports    = size_lamports * venue_fee_bps // 10_000           pump.fun: 100 bps (REVIEW)
base_fee_lamports     = 5_000                                             one signature (REVIEW)
priority_fee_lamports = micro_lamports_per_cu * compute_units // 1_000_000
                        micro_lamports_per_cu from tools.priority_fee `recommended_micro_lamports`
                        (tools/priority_fee.py:78), capped by the `max_micro_lamports` field; compute_units default 200_000 (REVIEW)
network_cost_lamports = base_fee_lamports + priority_fee_lamports
```

There is no tip term: vendor `JitoConfig` (`models.py:291-294`) is not carried (R3; section 11.9).

Buy: `x_net = size_lamports - venue_fee_lamports` enters the curve; cash debit = `size_lamports + network_cost_lamports`.
Sell: `gross = sell_out(S, T, t)`; `proceeds = gross - gross * venue_fee_bps // 10_000 - network_cost_lamports`.

All fee inputs are recorded on the `FillRecorded` event (section 3.3) so reports can split PnL into price, venue fee and network cost.

### 2.4 Quote source and slippage cap (`otherAmountThreshold` semantics)

One quote source per fill (R38): the fill basis is ALWAYS the bonding-curve quote synthesised by the adapter from the reserves at decision time `(S0, T0)`. The Jupiter lite-api quote (`exec.quote` with `source="jupiter"`; fields passed through by `tools/jupiter_quote.py:45-48`: `outAmount`, `otherAmountThreshold`, `slippageBps`, `priceImpactPct`) is informational only (route, priority) and never the fill price; it is recorded on `OrderPlaced.quote` as `source="curve"` with the Jupiter `quote_id` in `detail` when one was fetched. The field names of the curve quote follow Jupiter's so the sniper checklist reads the same either way:

```
quote.out_amount              = buy_out(S0, T0, x_net)                                ExactIn
quote.other_amount_threshold  = out_amount * (10_000 - slippage_bps) // 10_000
quote.price_impact_pct        = impact_buy(S0, x_net) * 100
```

For sells (ExactIn token units): `out_amount = sell_out(S0,T0,t) * (10_000 - venue_fee_bps) // 10_000`, `other_amount_threshold = out_amount * (10_000 - slippage_bps) // 10_000`.

At confirmation time (after latency, section 2.5) the fill is recomputed on the reserves observed then, `(S1, T1)`. If `out_at_confirmation < other_amount_threshold` the order is rejected with `reason=slippage_exceeded` and the ledger records both numbers. For a partial fill (section 2.6) the threshold is recomputed for the executed size, `filled_lamports` (or `filled_units`), before the comparison, so a partial outcome is never compared against a full-size threshold (R38, F-m3). This mirrors what the on-chain program would do with `max_sol_cost` / `min_sol_output` (vendor TODO at executor.py:151-156,170-171). There is no retry: the single-send rule (`rules/pumpgrok-team.mdc:30`) is implemented as PaperAdapter idempotency on `(ticket_id, side, decision_id)` (R18, R23), so a rejected order ends the order; a new order needs a new `decision_id` (and, under `manual-ticket`, a fresh approval).

`slippage_bps` comes from the order (the ticket's approved max slippage) and is capped by `limits.max_slippage_bps` (default 300, REVIEW).

### 2.5 Confirmation latency (`latency.py`)

```
latency_s = clip(lognormal(mu = ln(1.2), sigma = 0.5), 0.4, 20.0)     seeded (REVIEW)
dropped   = rng.random() < p_drop                                      p_drop = 0.02 (REVIEW)
```

Both draws come from the single injected `random.Random` (section 4.2) so replay is deterministic. The adapter awaits `clock.sleep(latency_s)` (virtual in replay, R27), then re-reads `PriceSource.curve(mint)` and re-runs the stop checks (section 2.8). If `dropped`, the order is rejected with `reason=tx_dropped` (the paper analogue of "UNKNOWN RESULT - reconcile by signature", `rules/pumpgrok-team.mdc:30`); the adapter never resubmits.

### 2.6 Partial fill and liquidity floor

Evaluated against the reserves at decision time with the R20 keys `liquidity_floor_multiple` (10) and `partial_fill_fraction` (0.02), in this order:

```
if S0 < liquidity_floor_multiple * size_lamports:          # D6: floor 10x order size (REVIEW)
    reject reason=below_liquidity_floor
fill_cap_lamports = S0 * partial_fill_fraction              # D6: 2 % of pool liquidity (REVIEW), floored to int
if size_lamports > fill_cap_lamports:
    filled_lamports = fill_cap_lamports; filled_fraction = Decimal(fill_cap_lamports) / Decimal(size_lamports)
    other_amount_threshold is recomputed for filled_lamports (sec 2.4)
    remainder is cancelled (not queued): OrderPartial semantics are a FillRecorded with filled_fraction < 1
else:
    filled_lamports = size_lamports; filled_fraction = 1
```

Note 10x floor means `size <= S0 / 10` and 2 % fraction means full fill only when `size <= S0 / 50`; sizes between `S0/50` and `S0/10` fill partially (R6). Sells use `T0` with the same two parameters (`t <= T0 / 10` to proceed, `t <= T0 / 50` for a full fill); partial sells leave the remainder in the position and EXIT's next cycle decides again with a fresh `decision_id`.

### 2.7 Mark-to-market

Each open position is valued at liquidation value, not spot:

```
mtm_lamports(pos)   = sell_out(S, T, pos.token_units) * (10_000 - venue_fee_bps) // 10_000
unrealized_lamports = mtm_lamports - pos.cost_basis_lamports     cost_basis = cash debited incl. all fees
```

This is deliberately conservative for thin curves: spot x quantity overstates what a sell would return. `MarkToMarket` events are written by the journal seat every `ledger.mtm_interval_s` (60 s, REVIEW) and whenever RiskEngine needs fresh equity (it reads the cached value if younger than `mtm_interval_s`). Positions with `mtm_frozen = true` (`graduated`, `blind_flatten`) keep their last value and are excluded from the refresh.

Each per-mint mark entry also records the venue fee it netted: `gross = mtm_lamports + venue_fee_lamports`. A forced close that values from the last mark (a complete curve, or an unreadable curve as in `blind_flatten`) books that stored venue fee on its `FillRecorded` and deducts only the network cost from the mark, so cash moves by `mtm_lamports - network_cost_lamports`. A mark written before this field existed has no venue fee: such a close reports `venue_fee_lamports = 0` (disclosed); its cash is unchanged.

### 2.8 State machine of one paper order

```
            quote ok                      latency elapsed           re-check passed
 NEW ------------------> ACCEPTED ----------------------------> CONFIRMING ------------+--> FILLED (filled_fraction 1)
  |  reject:no_reserves      |  reject:below_liquidity_floor        |                   +--> PARTIAL (filled_fraction < 1)
  |  reject:<R34 step id>    |  (exec.cancel -> REJECTED cancelled) |                   +--> REJECTED slippage_exceeded | tx_dropped
  |  reject:post_graduation_no_reserves                             |
  v                          v                                      v  re-check failed
 REJECTED               REJECTED                                 REJECTED kill_switch | halted | breaker_open | post_graduation_no_reserves
```

Every transition is one ledger event (section 3.3). At `CONFIRMING`, immediately before the fill is computed, the adapter re-runs the stop checks of `RiskEngine.check` (kill switch, halts, breakers, position limits and risk limits; steps 1-4 and 10-19 of section 5.2) against the state at that instant (R22): an order accepted before a kill switch, halt or breaker trip is rejected with `reason=kill_switch` / `halted` / `breaker_open` and never fills, so "no order decided before the switch can fill after it" holds across the latency window (F-B5). A buy that lost its position slot or its mint to another fill during the latency window is rejected `max_open_positions` / `already_open` / `creator_already_open`. A sell whose holding closed during the latency window (for example a flatten) is rejected `no_position`, so the same tokens are never sold twice. The adapter keeps an in-flight barrier (the set of orders in `ACCEPTED`/`CONFIRMING`); the supervisor's kill-switch flatten (section 5.4) waits on it until the set is empty, then calls `PaperAdapter.place` in-process for every open position, so a buy in flight can never open after a flatten was requested. `exec.cancel(order_id, ticket_id, decision_id)` succeeds only in `ACCEPTED` (before the latency sleep completes) and appends `OrderRejected(reason=cancelled, stage=ACCEPTED)`; after that it returns `False` and appends nothing, matching a real chain where a sent transaction cannot be recalled.

### 2.9 Worked numeric example

Inputs (ledger values are the integers in the right column; SOL figures are shown for readability only):

| Quantity | Value | Integer form | Source |
|---|---|---|---|
| Paper equity | 10.000000 SOL | 10_000_000_000 lamports | D6, `paper_equity_sol = 10` |
| Order size (2 % of equity) | 0.200000 SOL | 200_000_000 lamports | `max_trade_fraction = 0.02` |
| Curve at decision `S0`, `T0` | 42.000000 SOL, 766,428,571.4 tokens | 42_000_000_000 lamports, 766_428_571_428_571 units | `k = 30 * 1,073,000,000 = 3.219e10` [INFERENCE: pump.fun initial virtual reserves 30 SOL / 1.073e9 tokens] |
| `venue_fee_bps` | 100 | | section 2.3 |
| `recommended_micro_lamports` | 20,000 | | `tools/priority_fee.py:78` output for this example |
| `compute_units` | 200,000 | | section 2.3 |
| `slippage_bps` (ticket) | 100 | | ticket |
| `liquidity_floor_multiple`, `partial_fill_fraction` | 10, 0.02 | | section 2.6, R20 |

Step 1, liquidity checks: `S0 = 42 >= 10 * 0.2 = 2` passes the floor. `fill_cap = 0.02 * 42 = 0.84 >= 0.2`, so the order is eligible for a full fill.

Step 2, fees: `venue_fee = 0.2 * 0.01 = 0.002000 SOL` (2_000_000 lamports); `x_net = 0.198000 SOL` (198_000_000). `priority_fee = 20,000 * 200,000 // 1e6 = 4_000 lamports = 0.000004 SOL`; `base_fee = 5_000 lamports`; `network_cost = 9_000 lamports = 0.000009 SOL`.

Step 3, quote at `(S0, T0)`:

```
spot0       = 42 / 766,428,571.4             = 5.4800e-8 SOL/token   (Decimal 5.4800e-5 lamports per unit)
out_amount  = 766,428,571.4 * 0.198 / 42.198 = 3,596,210 tokens      (3_596_210_xxxxxx units; floored)
price_avg   = 0.198 / 3,596,210              = 5.5058e-8 SOL/token
impact      = 0.198 / 42                     = 0.4714 %   (check: 5.4800e-8 * 1.004714 = 5.5058e-8)
threshold   = out_amount * 9_900 // 10_000   = 3,560,247 tokens
```

Step 4, latency: seeded draw `latency_s = 1.4`, `dropped = False`. The adapter sleeps 1.4 s (virtual in replay), re-reads the curve and re-runs the stop checks (no kill switch, halt or breaker: proceed).

Step 5a, confirmation with a small move (`S1 = 42.1`, a 0.1 SOL buy landed first): `T1 = 3.219e10 / 42.1 = 764,608,076.0`; `out1 = 764,608,076.0 * 0.198 / 42.298 = 3,579,186 tokens`; `3,579,186 >= 3,560,247` so the order FILLS. Recorded fill (lamports / units; SOL shown in parentheses):

```
FillRecorded: filled_lamports=200000000 (0.200000)  filled_fraction=1  filled_units=3579186000000 (3,579,186 tokens)
              price_avg=5.5320e-5 lamports/unit (5.5320e-8 SOL/token)  venue_fee_lamports=2000000  network_cost_lamports=9000
              cash_delta_lamports=-200009000 (-0.200009)  cost_basis_lamports=200009000
              quote_out=3596210000000 threshold=3560247000000 confirm_out=3579186000000 latency_s=1.4
post-fill curve: S=42.298 SOL, T=761,028,890 tokens   (T1 - out1)
immediate MTM:   sell_out(42.298, 761,028,890, 3,579,186) * 0.99
               = 42.298 * 3,579,186 / 764,608,076 * 0.99 = 0.198 * 0.99 = 0.196020 SOL  (196_020_000 lamports)
unrealized:      196_020_000 - 200_009_000 = -3_989_000 lamports (-0.003989 SOL, -1.99 %: round-trip venue fee plus network cost)
```

Step 5b, confirmation with a larger move (`S1 = 42.5`): `T1 = 757,411,764.7`; `out1 = 757,411,764.7 * 0.198 / 42.698 = 3,512,285 < 3,560,247` so the order is REJECTED `reason=slippage_exceeded` with `quote_out=3,596,210 threshold=3,560,247 confirm_out=3,512,285`. No cash moves; `fees_lamports` on the rejection is `network_cost_lamports = 9_000` because a failed transaction still pays the base and priority fee (REVIEW: charge network cost on `slippage_exceeded`; do not charge on `tx_dropped`).

Step 5c, kill switch during latency: if `var/desk/KILLSWITCH` appears while the order sleeps, the re-check at `CONFIRMING` rejects it `reason=kill_switch`, `stage=CONFIRMING`; no cash moves and no fee is charged (nothing was sent).

Step 6, partial fill variant: size 1.5 SOL on the same curve. Floor: `42 >= 15` passes. `fill_cap = 0.84 < 1.5`, so `filled_lamports = 840_000_000`, `filled_fraction = 0.56`, and the remaining 0.66 SOL is cancelled, not queued. The threshold is recomputed for 0.84 SOL: `x_net = 0.8316`, `out_amount = 766,428,571.4 * 0.8316 / 42.8316 = 14,880,603`, `threshold = 14,731,797`; confirmation compares `out1` for 0.8316 SOL against that figure, not against the 1.5 SOL quote (R38).

## 3. Ledger (SPE-18026)

### 3.1 Module layout

```
src/pumpgrok/ledger/
  __init__.py
  store.py        LedgerStore: sqlite3 WAL, append(event) -> seq inside BEGIN IMMEDIATE, hash chain, snapshots,
                  atomic_write(path, bytes) helper (tmp + fsync + os.replace, vendor state.py:76-89 port)
  events.py       pydantic v2 models for the 18 event types (R32); EventType enum; snake_case mapping
  reducer.py      pure reduce(state, event) -> state; LedgerState model
  views.py        positions(), cash(), pnl(), equity_curve(), drawdown(), fees()
  reconcile.py    restart = snapshot + tail replay + verify; Reconciler
  export.py       JSONL journal export; vendor trades.jsonl shape; paper-YYYY-MM-DD.md block
  desk_bus.py     mirrors HaltSet/HaltCleared/KillSwitchSet into $PUMPGROK_DESK/desk.md
```

Location: `var/ledger.sqlite` for live-paper runs (gitignored, D2); replay runs write `var/replay/<dataset>/ledger.sqlite` (R21). Single writer (R26): every append, whether from the supervisor or from a CLI process (`pumpgrok paper buy|sell`, `killswitch clear`, `state halt --clear`, `live confirm`), goes through `LedgerStore.append` which opens `BEGIN IMMEDIATE`, reads the chain head, computes `(seq, prev_hash, hash)` and commits; sqlite's write lock serialises concurrent writers, so the chain never forks and no supervisor IPC is needed. Readers (reporting, `status`) open read-only connections (`?mode=ro`), which WAL permits concurrently. Markdown exports (`desk.md`, `paper-YYYY-MM-DD.md`, reports, `health.json`) are written with `atomic_write` (tmp file + `os.replace`).

### 3.2 Schema

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = FULL;            -- every append is durable before the caller sees seq
PRAGMA busy_timeout = 5000;           -- CLI writers wait for the supervisor's BEGIN IMMEDIATE (REVIEW)

CREATE TABLE events (
  seq             INTEGER PRIMARY KEY,          -- monotonic, no gaps
  ts_utc          TEXT    NOT NULL,             -- ISO-8601 with microseconds and Z, from Clock (replay: from the fixture, R27)
  source          TEXT    NOT NULL,             -- 'paper' | 'replay' | 'manual' (R21, R32); 'manual' = CLI-originated human records
  correlation_id  TEXT    NOT NULL,             -- root ULID (core/ids.py); "desk" for process-level events
  idempotency_key TEXT    NOT NULL UNIQUE,      -- sha256(type|correlation_id|caller-supplied scope), e.g. (ticket_id, side, decision_id) for orders
  type            TEXT    NOT NULL,             -- EventType value (CamelCase, R32)
  payload_json    TEXT    NOT NULL,             -- canonical JSON (sorted keys, no whitespace, ints and strings only, R28)
  prev_hash       TEXT    NOT NULL,             -- hash of seq-1; 64 zeros for seq 1
  hash            TEXT    NOT NULL UNIQUE       -- sha256 over canonical JSON of the row (below)
);
CREATE TRIGGER events_append_only_u BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER events_append_only_d BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;

CREATE TABLE snapshots (
  seq         INTEGER PRIMARY KEY,              -- last event folded into this snapshot
  ts_utc      TEXT    NOT NULL,
  state_json  TEXT    NOT NULL                  -- LedgerState canonical JSON; its sha256 and events.hash at seq are inside state_json.meta
);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- keys: schema_version ("1"), ledger_id (ULID), initial_equity_lamports, created_ts_utc, source, autonomy_level, export_seq
```

Hash chain rule (R28): `hash = sha256(canonical_json({"prev_hash", "seq", "ts_utc", "source", "correlation_id", "idempotency_key", "type", "payload_json"}))` with the values of the row, computed inside the same `BEGIN IMMEDIATE` transaction as the insert (R26). `idempotency_key` is part of the hash input because the column is NOT NULL UNIQUE and must be covered by the chain (locked Q3). Verification walks `events` in `seq` order and recomputes; any mismatch makes the ledger `INCONSISTENT` (section 3.5). Because `ts_utc` comes from the injected `Clock` and every id from `core/ids.py`, replay runs produce byte-identical chains (section 4.5).

Snapshot cadence: every `ledger.snapshot_every_events` (500, REVIEW) events or `ledger.snapshot_every_s` (300 s, REVIEW), whichever first; plus on `DailyRollover`, on graceful shutdown, and on `HaltSet`. Old snapshots are kept (they are small; the table is append-only like `events`).

### 3.3 Event types and payloads

All payloads carry no secrets and no wallet keys. Money is integer base units (R28): `<x>_lamports: int` for SOL, `<x>_units: int` for token base units (6 decimals); prices are `Decimal` strings in lamports per token base unit and are named with a `price_` prefix (`price_entry`, `price_peak`, `price_mark`, `price_avg`, `price_expected`, `price_exit`); impacts and fractions are `Decimal` strings. The 18 types below are defined once in `ledger/events.py` and are the complete vocabulary (R32); `contracts/events/<snake>.schema.json` carries one JSON Schema per type (`order_placed.schema.json` ... `approval_recorded.schema.json`) and nothing else: the D2 `signal`, `safety_report`, `verdict` and `alert` shapes are folded into the `journal_note` (payload `note_kind`), `escalation`, `order_placed` and `fill_recorded` payload schemas; there is no separate `signal.schema.json` or `alert.schema.json`. `desk.event_emit` and `journal.append` `kind` use the snake_case form of the same type, generated from the registry; seats may only write `journal_note` and `escalation` (registry invariant I5, docs/design/interfaces.md 2.10); every other type is appended by library code (PaperAdapter, RiskEngine, supervisor, CLI). Seat messages (LEAD, whale, social, signal, verdict, safety_report) are `JournalNote` payloads discriminated by `note_kind` (signal literal `signal`, R40); RUG alerts are `Escalation` payloads. There is no third vocabulary.

| type | correlation_id | payload fields | written by |
|---|---|---|---|
| `OrderPlaced` | token's | `order_id, decision_id, ticket_id, side(buy/sell), mint, size_lamports or token_units, slippage_bps, quote{out_amount, other_amount_threshold, price_impact_pct, source="curve"}, approval{kind, approval_id}, risk_check{passed, caps}` | PaperAdapter.place |
| `OrderRejected` | token's | `order_id, decision_id, reason (R34 ids + section 2.8 reasons), detail, fees_lamports, quote_out, threshold, confirm_out, stage(ACCEPTED/CONFIRMING)` | PaperAdapter / RiskEngine / LiveGate |
| `FillRecorded` | token's | `order_id, decision_id, side, mint, filled_lamports, filled_units, filled_fraction, price_avg, venue_fee_lamports, network_cost_lamports, cash_delta_lamports, latency_s, curve_before{S,T}, curve_after{S,T}, venue_tx_ref ("dry_run:<ULID>")` | PaperAdapter.place |
| `PositionOpened` | token's | `mint, symbol, creator, ticket_id, price_entry, token_units, cost_basis_lamports, score, opened_ts_utc` | adapter after the first buy fill |
| `PositionClosed` | token's | `mint, price_exit, proceeds_lamports, realized_pnl_lamports, pnl_pct, hold_seconds, reason, venue_tx_ref`; `reason` in `{stop_loss, take_profit, trailing_stop, max_hold, rug_alert, kill_flatten, blind_flatten, graduated, manual}` (R32) | adapter after a sell fill that zeroes the position, or the `graduated` / `blind_flatten` force-close |
| `MarkToMarket` | `desk` | `ts_source, prices{mint: {spot, S, T, mtm_lamports, venue_fee_lamports, source, age_s, frozen}}, cash_lamports, equity_lamports, unrealized_lamports`; `venue_fee_lamports` is the venue fee netted in `mtm_lamports` (absent on marks written before it was added) | journal seat / RiskEngine |
| `HaltSet` | `desk` | `reason (daily_loss/drawdown/ledger_inconsistent/manual), detail, set_by="risk_engine", equity_lamports, day_start_equity_lamports`; idempotency per `(reason, utc_day)` | RiskEngine only (R24) |
| `HaltCleared` | `desk` | `reason, cleared_by ("human:<name>" required), approval_id (ApprovalRecorded kind=halt_clear), note` | CLI only |
| `KillSwitchSet` | `desk` | `source (env/alert_command/file/tool), reason, flatten_requested, set_by`; an alert line that engages the latch is recorded as `alert_command`, later polls of the same latch as `file` | RiskEngine / risk.kill_switch |
| `KillSwitchCleared` | `desk` | `cleared_by ("human:<name>"), approval_id (ApprovalRecorded kind=killswitch_clear), sources_now_clear[]` | CLI only |
| `BreakerTripped` | `desk` | `breaker (data_stale/loss_velocity/exec_errors), metric, threshold, cooldown_s`; idempotency per `(breaker, occurrence)`, where occurrence is the n-th trip row of that breaker (a trip, reset and re-trip on one UTC day are three transitions) | RiskEngine breakers |
| `BreakerReset` | `desk` | `breaker, after_s, probe_ok` | RiskEngine breakers |
| `DailyRollover` | `desk` | `day_utc, day_start_equity_lamports, prior_day{realized_lamports, unrealized_lamports, fees_lamports, trades}, open_positions[]` | RiskEngine |
| `ConfigChanged` | `desk` | `keys_changed[], old_hash, new_hash, by` | startup (diff vs `meta`), `state autonomy` |
| `LiveWriteAttempted` | token's or `desk` | `adapter, method, caller_seat, gate_result{unmet[]}, stack_hash` | LiveAdapter / registry |
| `Escalation` | `desk` | `kind (bot_restart_exhausted/heartbeat_stale/persistence_down/clock_skew/ledger_inconsistent/blind_flatten/graduated/rug_alert), seat, detail` | supervisor, RiskEngine, seats via `desk.event_emit kind=escalation` |
| `JournalNote` | token's or `desk` | `seat, note_kind (lead/whale/social/signal/verdict/safety_report/review/ticket/note), text, refs[]` | seats via `journal.append kind=journal_note` |
| `ApprovalRecorded` | token's or `desk` | the `ApprovalRecord` fields (docs/design/interfaces.md 2.9: `id, kind, ticket_id, mint, size_lamports, max_slippage_bps, exit_rule_id, approved_by, raw_message, at, consumed`); consumption is a second row with `consumed=true` written inside the order's transaction (R23, R33) | CLI (`paper buy`, `killswitch clear`, `state halt --clear`, `live confirm`), Telegram approval parser, RiskEngine (autonomous_paper), EXIT (exit_rule under manual-ticket) |

`OrderPartial` from the spec is represented as `FillRecorded` with `filled_fraction < 1`; `FeeCharged` and `CashAdjusted` are folded into `FillRecorded.cash_delta_lamports` and `OrderRejected.fees_lamports` so that cash has exactly one source of truth per order.

### 3.4 Reducer and derived views

`reduce(state, event)` is pure and total: unknown event types are recorded in `state.unknown_events` and otherwise ignored, so a newer process can read an older ledger and vice versa.

```
LedgerState:
  seq, source, day_utc, day_start_equity_lamports, peak_equity_lamports
  cash_lamports
  positions{mint: Position(mint, symbol, creator, ticket_id, correlation_id, price_entry, price_peak,
                           token_units, cost_basis_lamports, fees_lamports, opened_ts_utc, last_mtm_lamports, last_mtm_venue_fee_lamports, last_mtm_ts, mtm_source, mtm_frozen)}
  halt{active, reason, since}  kill_switch{active, source, since, flatten_requested}  breakers{name: {state, until}}
  approvals{approval_id: {kind, consumed}}
  counters{trades_today, rejected_today{reason: n}, fees_today_lamports, realized_today_lamports}
  last_mtm_ts_utc
```

Views (`views.py`), all computed from `LedgerState` plus the event tail where needed; every money view returns `int` lamports, every ratio returns `Decimal`:

```
cash_lamports         = state.cash_lamports
positions()           = state.positions (filter token_units > 0)
realized_pnl(from,to) = sum(PositionClosed.realized_pnl_lamports in range)
unrealized_pnl()      = sum(pos.last_mtm_lamports - pos.cost_basis_lamports)
fees(from,to)         = sum(FillRecorded.venue_fee_lamports + network_cost_lamports) + sum(OrderRejected.fees_lamports)
equity()              = cash_lamports + sum(pos.last_mtm_lamports)
equity_curve()        = [(MarkToMarket.ts, equity_lamports)]  plus a point after every FillRecorded
drawdown()            = Decimal(peak_equity - equity()) / peak_equity
daily_pnl_fraction()  = Decimal(equity() - day_start_equity) / day_start_equity
win_rate(from,to)     = closed with realized_pnl_lamports > 0 / closed
profit_factor         = Decimal(sum(gains)) / abs(sum(losses))   (inf if no losses; reported as "n/a")
```

Views used by the live gate (`min_paper_days`, `performance_thresholds`) take a `source` filter and refuse any ledger whose `events.source` contains `replay` (R21).

### 3.5 Restart: snapshot + tail replay + reconcile

```
1. open the ledger path for the run (var/ledger.sqlite, or var/replay/<dataset>/ledger.sqlite); if missing -> fresh ledger: write meta, write ConfigChanged, state = initial (cash = initial_equity_lamports)
2. s = latest snapshot (or empty state at seq 0)
3. tail = SELECT * FROM events WHERE seq > s.seq ORDER BY seq
4. verify chain: for each event in tail recompute hash; first event's prev_hash must equal s.chain_hash
5. state = fold(reduce, s.state, tail)
6. integrity checks (all must hold):
   a. state.cash_lamports == initial_equity_lamports + sum(FillRecorded.cash_delta_lamports) - sum(OrderRejected.fees_lamports)   over the FULL event table
   b. for each open position: token_units == sum(buy fills) - sum(sell fills) for that mint; cost_basis == sum(buy cash) - proportional reductions on sells
   c. no open position whose PositionOpened predates a PositionClosed with the same mint without a newer PositionOpened
   d. the full-replay state (fold over all events from seq 1) equals `state` field-for-field  [cheap at paper scale: tens of thousands of events; computed on every start]
   e. snapshots.state_json.meta.chain_hash matches events.hash at snapshots.seq for the latest snapshot
   f. every event's source equals meta.source (a replay ledger never contains paper rows and vice versa)
7. PriceSource probe for every open position: curve() reachable -> MarkToMarket appended; unreachable -> position.mtm_source = "last_good", DataStale breaker pre-armed, blind timer started (R25)
8. status: CONSISTENT -> normal start; INCONSISTENT -> append HaltSet(reason=ledger_inconsistent, detail=<which check>), Escalation(kind=ledger_inconsistent) relayed as a critical alert, process continues in observe-only (all seats run, RiskEngine refuses every order with reason=ledger_inconsistent); `pumpgrok verify --ledger` prints the diff
```

What "mismatch" means concretely: any of 4, 6a-6f failing, or an `UNIQUE` violation on `idempotency_key` during tail replay (duplicate write detected). Nothing is auto-repaired. A human runs `pumpgrok verify --ledger --explain`, decides, and clears with `pumpgrok state halt --clear --by human:<name> --reason "<text>"` which appends `HaltCleared` plus `ApprovalRecorded(kind=halt_clear)`; the next start re-runs the checks. If checks still fail, the halt is re-set immediately (the clear cannot override a persistent inconsistency).

Unwritable store (disk full, permission): `LedgerStore.append` raises `LedgerUnavailable`; RiskEngine refuses orders (`reason=ledger_inconsistent`, detail `persistence_down`), the supervisor buffers at most `ledger.buffer_max_events` (1000, REVIEW) non-order events in memory, emits `Escalation(kind=persistence_down)`, and retries the append with the jittered tenacity policy (`sleep=clock.sleep`, D5, R27). If the buffer fills, the oldest `MarkToMarket` events are dropped first; `FillRecorded`/`PositionClosed`/`ApprovalRecorded` are never dropped (if they cannot be written, the order is not considered placed, which is why the ledger append happens before the adapter returns the fill).

### 3.6 JSONL journal export

Export runs after every event batch and on shutdown; files are append-only and idempotent (each line carries `seq`; the exporter resumes from the last exported `seq` stored in `meta.export_seq`). Every file is written through `atomic_write` (R26).

| Target | Path | Shape | Consumer |
|---|---|---|---|
| Canonical JSONL | `var/journal/YYYY-MM-DD.jsonl` | one line per ledger event: `{seq, ts_utc, source, correlation_id, type, payload}` | reporting, `pumpgrok journal rollup` |
| Vendor-compatible trades log | `var/journal/trades.jsonl` | `type: buy / skip / close` records with the exact keys of `vendor/grokbot-pumpfun/src/log.py:98-183` (`ts`, `mode` stamped per `log.py:91-92`), `tx_hash` = bare `dry_run`, ULID in `venue_tx_ref`; lamports rendered as SOL floats only in this compatibility file | `tools/pipeline_evidence.py` (`--candidates` filters `tx_hash == dry_run`), vendor `scripts/dashboard.py`, `scripts/replay.py` |
| Desk markdown | `$PUMPGROK_DESK/journal/paper-YYYY-MM-DD.md` | the `### PAPER BUY | <ticket>` bullet block of `tools/paper_sim.py:31-40`, extended with `Fill price`, `Fees SOL`, `Correlation` lines | humans, Hermes `chief-journal-rollup` cron, `desk_state.py` (ticket id scan at `tools/desk_state.py:93-104`) |
| Desk halt mirror | `$PUMPGROK_DESK/desk.md` | `Halt: true` + `FLOOR HALTED - <reason> @ <ts>` exactly as `tools/desk_state.py:199-205` writes it, via tmp + `os.replace` (the in-place write of `desk_state.py` is not carried) | Hermes cron prompts (`[SILENT]` gate), `desk_state.py status` |

`/workspace/trading-desk` compatibility is therefore preserved without the LLM seats parsing sqlite.

### 3.7 Mapping from vendor fields

| Vendor field | Source | Ledger equivalent |
|---|---|---|
| `PipelineState.day` | state.py:36 | `LedgerState.day_utc` (set by `DailyRollover`) |
| `PipelineState.trades_today` | state.py:37 | `counters.trades_today` (count of `FillRecorded side=buy` since rollover, by fill timestamp) |
| `PipelineState.realized_pnl_sol` | state.py:38 | `counters.realized_today_lamports` (sum of `PositionClosed.realized_pnl_lamports` since rollover) |
| `PipelineState.grok_calls_today` | state.py:39 | not a ledger concern; `core/budget.py` `CallBudget` persists its own counter in `var/budget.json` |
| `PipelineState.positions{mint: Position}` | state.py:40 | `LedgerState.positions` |
| `Position.entry_price` | models.py:247 | `Position.price_entry` = `FillRecorded.price_avg` of the opening fill (Decimal, lamports per token base unit; export converts to SOL per token) |
| `Position.peak_price` | models.py:248 | `Position.price_peak`, updated by `MarkToMarket` (vendor persisted it every +1 %, risk.py `PEAK_PERSIST_STEP`; the ledger records it on every MTM event, 60 s cadence) |
| `Position.sol_spent` | models.py:249 | `Position.cost_basis_lamports` (includes fees; vendor excluded fees because it had none) |
| `Position.token_amount` | models.py:250 | `Position.token_units` (integer base units; vendor float tokens; export divides by 1e6) |
| `Position.opened_at` (epoch float) | models.py:251 | `Position.opened_ts_utc` (ISO string; export converts) |
| `Position.tx_hash` | models.py:252 | `FillRecorded.venue_tx_ref` |
| `Position.score` | models.py:253 | `PositionOpened.score` (signal seat's total score) |
| trades.jsonl `buy.size_sol` | log.py:113 | `FillRecorded.filled_lamports / 1e9` at export |
| trades.jsonl `close.pnl_sol / pnl_pct / hold_seconds / reason` | log.py:176-179 | `PositionClosed.realized_pnl_lamports / pnl_pct / hold_seconds / reason` |
| trades.jsonl `skip.stage / reason` | log.py:146-147 | `OrderRejected.reason` for stage `risk`/`executor`; pre-order skips (monitor/analyzer/scoring/checker) are `JournalNote` events emitted by the owning seat with `refs=[stage, reason]` |

## 4. Replay (SPE-18029)

### 4.1 Module layout

```
src/pumpgrok/replay/
  __init__.py
  clock.py        Clock protocol; WallClock; FixtureClock; the only module allowed to import time / asyncio.sleep / asyncio.timeout
  rng.py          make_rng(seed) -> random.Random; the only RNG constructor in the package
  fixtures.py     FixtureReader: merges dataset streams by ts; FixtureManifest; trim() for the CI smoke dataset
  sources.py      FixturePriceSource, FixtureEventStream, FixtureHttpTransport (httpx.MockTransport), FixtureWebSocket, FixtureLlm
  recorder.py     Recorder: wraps live transports and writes the dataset format
  runner.py       run_replay(dataset, config) -> ReplayResult(ledger_hash, events, equity_curve)
```

### 4.2 Clock and RNG

```python
class Clock(Protocol):
    def now(self) -> float: ...  # epoch seconds (UTC)
    def monotonic(self) -> float: ...
    def utc_iso(self) -> str: ...  # ts_utc for ledger events
    async def sleep(self, seconds: float) -> None: ...
    def timeout(
        self, seconds: float
    ) -> AbstractAsyncContextManager[None]: ...  # replaces asyncio.timeout
```

`WallClock` delegates to `time.time`, `time.monotonic`, `asyncio.sleep`, `asyncio.timeout`. `FixtureClock` holds a virtual time that only advances when (a) the runner delivers the next fixture event, or (b) a task calls `sleep(s)` or a `timeout(s)` deadline is the earliest pending wake; sleeping tasks and deadlines are queued in one heap and woken in `(wake_time, enqueue_seq)` order so scheduling is deterministic regardless of asyncio's internal ordering and of host CPU speed. All sleeps, timeouts and retry waits go through the Clock: `clock.sleep`, `clock.timeout`, and every tenacity retrier is built with `sleep=clock.sleep` (R27). Direct `asyncio.timeout`, `asyncio.wait_for`, `asyncio.sleep`, `time.time`, `time.monotonic` and `datetime.now` are forbidden outside `replay/clock.py` by the static test `tests/safety/test_virtual_time_only.py`. The vendor already injects `clock` into `RiskManager` (`risk.py:45`), `RateLimiter` (`ops.py:93-98`), `CircuitBreaker` (`ops.py:139-143`), `CallBudget` (`ops.py:191-196`), `Metrics` (`ops.py:44`); the port keeps that style and extends it to every module that reads time.

One RNG: `rng.make_rng(config.replay.seed)` is called exactly once in `cli.py` and passed down by constructor injection (PaperAdapter latency, breakers' jitter, tenacity jitter, the LLM-fallback tie-breaks, `IdFactory`). `random.random()`, `random.Random()` without an argument and `secrets` are banned in `src/pumpgrok/` by a static test (`tests/safety/test_no_ambient_randomness.py`, owned by n7); the `uuid` module is banned by `tests/safety/test_no_uuid.py` (R29). ULIDs (correlation_id, decision_id, order_id, event ids, approval ids) come from `core/ids.py` `IdFactory(clock, rng)`.

Default seed: `20260101` (config `replay.seed`, REVIEW). In live-paper mode the seed is still fixed (latency draws need no entropy), which makes a live-paper day re-runnable from its recording.

### 4.3 Fixture format

```
tests/fixtures/replay/<dataset>/
  manifest.json      {"dataset", "recorded_from_utc", "recorded_to_utc", "seed_hint", "sources": {...}, "sha256": {file: digest}, "notes"}
  pumpportal.jsonl   {"ts": 1767225600.123, "kind": "ws", "stream": "pumpportal", "payload": {... raw message ...}}
  pumpfun_rest.jsonl {"ts": ..., "kind": "http", "method": "GET", "url": "/coins/<mint>", "status": 200, "body": {...}}
  jupiter.jsonl      {"ts": ..., "kind": "http", "method": "GET", "url": "https://lite-api.jup.ag/swap/v1/quote?...", "status": 200, "body": {...}}
  rpc.jsonl          {"ts": ..., "kind": "rpc", "method": "getAccountInfo|getTokenLargestAccounts|getRecentPrioritizationFees", "params_hash": "...", "result": {...}}
  ticks.jsonl        {"ts": ..., "kind": "tick", "mint": "...", "S": 42100000000, "T": 764608076000000, "complete": false, "source": "pumpportal|rest"}   (integer lamports / base units)
  llm.jsonl          {"ts": ..., "kind": "llm", "canonical_request_hash": "...", "model": "...", "outcome": "ok|timeout|error", "latency_s": 1.9, "response": {...}}
```

Every line is one JSON object with a leading `ts` (epoch seconds, float) stamped by the recorder's Clock (R27). Streams are merged by `(ts, file_order, line_no)`. The raw PumpPortal payloads are the ones `parse_create_event` and `handle_event` consume (`txType`, `mint`, `vSolInBondingCurve`, `vTokensInBondingCurve`, `marketCapSol`, `traderPublicKey`, monitor.py:61-83 and :149-159). `ticks.jsonl` is derived at record time from both streams so `FixturePriceSource.curve()` can answer without re-parsing; the derivation is deterministic and `pumpgrok replay rebuild-ticks --dataset <name>` regenerates it.

HTTP and RPC lookups are keyed by `(method, url-or-params_hash)`; when the desk asks for something the fixture does not contain, the fixture transport returns a synthetic `503` and the normal degradation path runs (this is a feature: a trimmed dataset exercises breakers). LLM lookups are keyed by `canonical_request_hash` (the prompt with timestamps, correlation ids and ULIDs stripped before hashing); `FixtureLlm` sleeps the recorded virtual `latency_s` on the Clock and then returns the recorded `outcome` (`ok` with `response`, `timeout`, or `error`). A request whose hash has no record FAILS the replay with `ReplayMissingRecord`; there is no silent rule-based fallback in replay (R27, F-M4). The rule-based fallback exists only for live-paper degradation (section 6.7).

### 4.4 Recorder

`pumpgrok run --mode paper --record <dataset> --duration <s> [--mints <list>]` runs the normal live-paper desk with every outbound transport wrapped (`--record` and `--replay <dir>` are mutually exclusive options of the one `run` command; `--once` runs a single supervisor tick, which is what Hermes cron wrappers use):

- httpx: a recording `httpx.AsyncBaseTransport` that forwards to the real transport, then writes the request/response line (API keys in headers are dropped; query parameters named `api-key`, `key`, `token` are replaced by `REDACTED`; this list is the G-3 secret regex set applied to URLs).
- websockets: a `RecordingWebSocket` wrapper that writes every received frame before yielding it.
- JSON-RPC: the `tools/onchain/rpc.py` client has a `recorder` hook (R31).
- LLM: the x.ai client (`core/llm.py`) records `canonical_request_hash`, `outcome` in `{ok, timeout, error}`, the measured `latency_s` (which becomes the virtual latency on replay) and the `response` (R27).

The recorder stamps its own Clock's `ts` into every fixture line, and on replay the ledger `ts_utc` comes from the fixture (the `FixtureClock` is driven by those stamps), so the recorded ledger and the replayed ledger carry the same timestamps (R27, F-M5). The recorder uses the same supervisor, bots and PaperAdapter, so a recording session is itself a paper-trading session (`source=paper`) whose ledger is copied next to the dataset (`ledger.sqlite.recorded`) as the reference for the determinism test. The replay of that dataset writes `var/replay/<dataset>/ledger.sqlite` with `source=replay` (R21).

### 4.5 Determinism test

`tests/replay/test_replay_determinism.py` runs `run_replay("smoke-10m", config)` twice in fresh temp dirs and asserts:

1. `sha256` of the concatenated `events.hash` column is identical;
2. `sha256` of `var/replay/smoke-10m/journal/YYYY-MM-DD.jsonl` bytes is identical;
3. the final `LedgerState` dumps are identical, including every ULID;
4. with `--compare-recorded`, both match `ledger.sqlite.recorded` from the recording session on every column except `source` (`paper` vs `replay`) and the `hash`/`prev_hash` chain recomputed with that one column difference; this proves the live-paper path and replay path are one code path, and it is possible only because the recorder stamped its Clock `ts` into the fixture and replay takes `ts_utc` from the fixture (R27).

Sources of non-determinism that the design removes: wall clock (FixtureClock), timeouts (`clock.timeout`), retry waits (tenacity `sleep=clock.sleep`), RNG (single seeded), asyncio task ordering (FixtureClock's heap plus the supervisor running seats in roster order within a tick), dict ordering (canonical JSON), money formatting (integers; Decimal strings for ratios), ULIDs (from clock + rng), LLM responses, latency and failures (recorded outcome; missing record fails).

### 4.6 CI smoke dataset

`smoke-10m` is produced once by an operator: `pumpgrok run --mode paper --record smoke-10m --duration 600`, then `pumpgrok replay trim --dataset smoke-10m --max-events 2000 --keep-mints-with-fills` which keeps every event for mints that produced an order and a random (seeded) 5 % of the rest, then `pumpgrok verify --fixture smoke-10m` which replays it (`pumpgrok run --mode paper --replay tests/fixtures/replay/smoke-10m`) and checks the manifest digests. Target size under 1 MB so it is committed. It must contain: at least one full fill, one partial fill, one `slippage_exceeded`, one `below_liquidity_floor`, one DataStale gap (the trimmer inserts a 180 s hole), one LLM `timeout` outcome, and one exit by `stop_loss` or `take_profit`. `tests/fixtures/replay/README.md` lists the datasets and how to regenerate them. A longer `soak-3d` dataset (three recorded days, trimmed to about 50 MB) is not committed; nightly CI downloads it from the artifact store named in `.github/workflows/ci.yml` (owned by n5/n8). The batch-1 `smoke` dataset (R37) is a hand-written two-line fixture (one `ticks.jsonl` line, one manifest) that exercises the skip-only cycle before any engine exists.

## 5. Risk engine, breakers, kill switch (SPE-18028)

### 5.1 Module layout

```
src/pumpgrok/risk/
  __init__.py
  engine.py     RiskEngine.check(order) -> RiskDecision; evaluate_halts(); daily rollover
  limits.py     RiskBudget ([risk], R20 keys) and EngineLimits ([limits]) pydantic-settings models (all REVIEW defaults)
  sizing.py     proposal sizer (vendor position_size port)
  breakers.py   Breaker base (vendor CircuitBreaker port from vendor src/ops.py) + DataStale, LossVelocity, ExecErrors
  killswitch.py KillSwitch: env, file and alert-channel sources (the channel writes the latch file), set/flatten_request, audit
```

`RiskEngine` (the class is `RiskEngine`, never `RiskManager`; R31) is owned by bot-02-risk as code (D3), but it is library code (R24): `PaperAdapter.place` calls `RiskEngine.check(order)` in-process for every order regardless of the RISK seat's health, and `RiskEngine` owns every `HaltSet` and `BreakerTripped` append (idempotent per `(reason, utc_day)` / `(breaker, occurrence)` through the ledger `idempotency_key`). The RISK seat monitors, alerts and sets the kill switch; it never appends `HaltSet` itself (F-m2). It is the only component that may say "no" to an order; `PaperAdapter` refuses to proceed without a passed `RiskDecision` whose `order_hash` matches, and re-runs the stop checks at `CONFIRMING` (section 2.8, R22).

### 5.2 Limits and `RiskEngine.check`

The `[risk]` block is the ONLY risk-budget schema (R20): the same nine keys appear in `RiskBudget` (docs/design/interfaces.md 2.9), every seat's `risk_budget` in docs/ROSTER.md, and `risk.check_limits` output. Fractions are of equity in 0..1, never percent.

```toml
[risk]                                   # every value REVIEW (D6)
max_trade_fraction        = 0.02         # per-order size cap, fraction of equity
max_token_fraction        = 0.05         # cost basis of open position + this order, fraction of equity
daily_loss_halt_fraction  = 0.05         # constitution: rules/pumpgrok-team.mdc:34 (FLOOR)
drawdown_halt_fraction    = 0.15         # D6
max_open_positions        = 3            # vendor RiskConfig.max_open_positions (models.py:321)
max_trades_per_day        = 20           # vendor RiskConfig.max_trades_per_day (models.py:320)
liquidity_floor_multiple  = 10           # D6: S0 >= 10 x order size
partial_fill_fraction     = 0.02         # D6: full fill only up to 2 % of pool liquidity
paper_equity_sol          = 10           # D6; the one SOL-denominated key, converted to lamports at load

[limits]                                 # engine knobs that are not part of the risk budget (REVIEW)
min_trade_lamports        = 10000000     # vendor MIN_TRADE_SOL = 0.01 (risk.py:36)
max_slippage_bps          = 300
one_position_per_creator  = true         # vendor FilterConfig (pipeline.py:376-384)
daily_loss_basis          = "total"      # total = realized + unrealized (conservative); "realized" = vendor behaviour
blind_max_s               = 300          # R25
```

`check(order)` runs these steps in order and stops at the first failure; the step id IS the `risk.check_limits` rule id and the `OrderRejected.reason` (one vocabulary, R34). The decision carries every evaluated cap so the rejection is explainable:

```
 1. ledger_inconsistent     ledger status must be CONSISTENT (sec 3.5)
 2. kill_switch             no active kill switch (file and alert channel re-polled now, env read at start, sec 5.4)
 3. halted                  no active halt (daily_loss / drawdown / ledger_inconsistent / manual); detail carries the reason
 4. breaker_open            no breaker open (any of the three); detail carries the breaker name
 5. live_gate               order.adapter == "paper" or LiveGate.check() empty (and LiveWriteAttempted appended on failure)
 6. approval_missing        manual-ticket: an unconsumed ApprovalRecorded for this ticket exists (buy: human_buy; sell: exit_rule / human_sell / kill-flatten); autonomous-paper: mint ApprovalRecord(kind=autonomous_paper)
 7. approval_mismatch       the approval matches ticket, mint, size, slippage token-for-token (ApprovalRecord.matches)
 8. seat_may_trade          buys only from bot-04-sniper, sells only from bot-06-exit; neither seat latched observe-only; bot-02-risk not latched observe-only for buys (R24)
 9. max_trades_per_day      counters.trades_today < max_trades_per_day
10. max_open_positions      len(open positions) < max_open_positions (buy only)
11. already_open            mint not already open (buy only)
12. creator_already_open    creator has no open position if one_position_per_creator (buy only)
13. max_trade_fraction      size_lamports <= max_trade_fraction * equity   else size is CAPPED (not rejected) and decision.capped = true
14. max_token_fraction      cost_basis(mint) + size_lamports <= max_token_fraction * equity   else cap, or reject if cap < min_trade_lamports
15. daily_loss_halt         evaluate_halts(): (day_start_equity - equity) / day_start_equity < daily_loss_halt_fraction, else HaltSet(daily_loss) is appended and the order is rejected daily_loss_halt
16. drawdown_halt           evaluate_halts(): (peak_equity - equity) / peak_equity < drawdown_halt_fraction, else HaltSet(drawdown) and rejected drawdown_halt
17. data_stale              the equity used by 13-16 came from a MarkToMarket younger than mtm_interval_s (a refresh is requested first; if PriceSource fails the order is rejected data_stale and the decision is discarded)
18. size_too_small          size_lamports >= min_trade_lamports after caps
19. below_liquidity_floor   S0 >= liquidity_floor_multiple * size_lamports (adapter re-checks at fill time)
20. pass -> RiskDecision(passed=True, size_lamports=final, caps={...}, order_hash, approval_id)
```

Sells with `reason` in an exit rule, `rug_alert`, `kill_flatten`, `blind_flatten` or `graduated` are never blocked by 2-4 and 9-19: reducing risk is always allowed. Sells are blocked only by 1 (ledger inconsistent means we do not know what we hold), 5 and 6-8. `graduated` and `blind_flatten` closes are adapter-internal force-closes (sections 2.2, 5.3) and carry no order; they still append `PositionClosed`.

Halts (`RiskEngine.evaluate_halts()`, called at step 15-16 of every check, at the start of every risk-seat cycle, and after every `PositionClosed`/`MarkToMarket`):

```
equity         = views.equity() per daily_loss_basis
daily_loss     = (day_start_equity - equity) / day_start_equity
if daily_loss >= daily_loss_halt_fraction and not halt.active:
    append HaltSet(reason=daily_loss, idempotency_key=sha256("HaltSet|daily_loss|<utc_day>"))
    Notifier.alert(critical, "FLOOR HALTED - DAILY LOSS LIMIT"); desk_bus.write_halt(...) via tmp + os.replace (R26)
drawdown       = (peak_equity - equity) / peak_equity
if drawdown >= drawdown_halt_fraction and not halt.active:
    append HaltSet(reason=drawdown, idempotency_key=sha256("HaltSet|drawdown|<utc_day>"))
```

The idempotency key makes a second observer of the same breach a no-op at the ledger (`UNIQUE` on `idempotency_key`), so there is exactly one `HaltSet` per reason per day whichever call path sees it first (F-m2). Halts are cleared by a human only: `pumpgrok state halt --clear --by human:<name> --reason "<text>"` appends `HaltCleared` together with `ApprovalRecorded(kind=halt_clear)`; no auto-clear at UTC rollover (R5, R22).

The constitutional alert text is a single constant `FLOOR_HALTED_DAILY` in `risk/engine.py` copied byte-for-byte from `rules/pumpgrok-team.mdc:34` (that line uses an en dash, U+2013, between `HALTED` and `DAILY`; this document is ASCII-only and writes a hyphen, the code must use the constitution's bytes (R7); `tools/desk_state.py:76` matches case-insensitively on `FLOOR HALTED` only, so either dash satisfies the file bus).

### 5.3 Breakers

All three subclass the vendor `CircuitBreaker` port (`ops.py:131-182`, ported to `risk/breakers.py`: consecutive-failure threshold, `opened_at`, cooldown, half-open probe) with two additions: an explicit `half_open` state that admits exactly one probe, and hysteresis (`reset_after_ok` consecutive successes before `closed`). States: `closed -> open -> half_open -> closed | open`. Every wait and window uses the injected `Clock` (R27).

| Breaker | Trip condition (REVIEW) | Cooldown | Reset (hysteresis) | While open |
|---|---|---|---|---|
| `DataStale` | no PumpPortal frame AND no successful REST curve read for `data_stale_s = 120` (vendor `STALL_SECONDS = 600`, pipeline.py, is for the launch stream only; 120 s is for prices), OR any open position with 3 consecutive missing prices (vendor `BLIND_AFTER = 3`, risk.py) | 60 s after the first fresh tick | 3 consecutive fresh ticks within 30 s | no new buys; EXIT keeps evaluating stop rules on `last_good` prices for at most `blind_max_s = 300`; at `blind_max_s` without a price EXIT force-closes the position at `last_good` (conservative MTM) with `PositionClosed reason=blind_flatten`, freezes its MTM and appends `Escalation(kind=blind_flatten)` (R25). Missing data never leaves a position unprotected |
| `LossVelocity` | `(equity_15m_ago - equity) / equity_15m_ago >= loss_velocity_fraction = 0.02` over a rolling 15 min window of MTM points | 30 min | window loss below 0.5 % for 5 min | no new buys; exits allowed |
| `ExecErrors` | 3 `OrderRejected` with reason in `{tx_dropped, slippage_exceeded, quote_unavailable, rpc_error}` within 10 min | 15 min | one probe order fills (half-open admits one) | no new buys; exits allowed |

Each transition appends `BreakerTripped`/`BreakerReset` (idempotent per `(breaker, occurrence)`, R24: every trip and every reset is its own row, so a restart after a same-day trip, reset and re-trip still sees the breaker open) and emits an edge-triggered Notifier alert (vendor `_check_transitions` semantics, pipeline.py:334-368). Breaker state is derived from the ledger on restart so a restart cannot be used to bypass a cooldown: the reducer reconstructs `breakers{name: {state, until}}` from the last `BreakerTripped` without a later `BreakerReset`, and the supervisor's clock decides whether `until` has passed.

### 5.4 Kill switch

```
sources:
  env   : PUMPGROK_KILLSWITCH set and not in {"", "0", "false"}  -> source=env, reason=env value
          READ ONCE AT PROCESS START (an env var cannot change inside a running process, F-m1); it starts the desk already switched
  file  : var/desk/KILLSWITCH exists (any size)                       -> source=file, reason=first line; with env also set, a FLATTEN first line still requests the flatten (source stays env)
          LIVE: polled once per supervised cycle (RiskEngine.poll_kill_sources), by the desk gateway owner loop every KILL_POLL_INTERVAL_S (5 s) on an idle desk, on every RiskEngine.check and at CONFIRMING of every order
          the one latch path; every writer resolves it through killswitch_file(data_dir)
  alert : the alert channel, a live source (RISK-004). Telegram getUpdates with a 2 s timeout, accepting text only
          from allowlisted chat ids (a bot token in PUMPGROK_TELEGRAM_TOKEN and at least one chat id in
          notify.allowlist; otherwise the channel is empty and polls nothing). Polled once per supervised cycle by
          RiskEngine.poll_kill_sources (env, then file, then alert) and at the start of every RiskEngine.check.
          A valid "KILL <reason>" line writes the latch file through latch_from_alert when neither env nor the file
          is engaged (origin alert_command while that latch is in force). A "KILL FLATTEN <reason>" arriving while
          the switch is engaged escalates it: the latch file is rewritten as "FLATTEN <reason>" and the flatten runs
          from the same poll, closing open positions with reason kill_flatten. The next update offset is committed
          under the desk data dir after each poll is handled, so a restart never re-reads a consumed KILL. A
          getUpdates failure returns no lines and is logged without the token; the file source does not depend on it.
  tool  : risk.kill_switch (RISK-only grant) with action in {set, flatten_request}; it writes var/desk/KILLSWITCH; there is no clear action (R22)
```

Semantics:

- Set: first observation appends `KillSwitchSet(source, reason, flatten_requested)`; `RiskEngine.check` rejects every buy with `reason=kill_switch` from that instant. Orders already in `ACCEPTED` are re-checked at `CONFIRMING` (section 2.8) and rejected `kill_switch` (likewise `halted` / `breaker_open`), so no order decided before the switch can fill after it (F-B5).
- Flatten outcome (G7): a position the flatten cannot value (no live curve, no ledger mark, no reserves) is reported `not_flattened` with detail `status=no_mark` and stays open. The CLI `killswitch flatten` exits 6 and names each open mint on stderr, and its JSON reports `flatten_status` `incomplete`; the gateway and alert-poll hook log each one at ERROR. The latch is set regardless. There is no reserves fallback in the CLI.
- Flatten: `risk.kill_switch.flatten = false` (REVIEW). When `flatten_request` is used, the file first line is `FLATTEN` (written by `risk.kill_switch` flatten_request, or by the alert command `KILL FLATTEN <reason>`), the supervisor executes the flatten in-process: it waits on the adapter's in-flight barrier (every `ACCEPTED`/`CONFIRMING` order reaches `REJECTED`), then calls `PaperAdapter.place` directly for one sell per open position with `reason=kill_flatten` and an `ApprovalRecord(kind=autonomous_paper)` minted by `RiskEngine` (one order per `(ticket_id, sell, decision_id)`; a partial fill leaves a remainder that the supervisor sells with a fresh `decision_id` on the next tick, R23). The EXIT seat is not in the path, so the flatten completes even when EXIT is observe-only.
- Clear: CLI-only, human only. `env` unset and file removed are necessary but not sufficient; the switch stays logically active until `pumpgrok killswitch clear --by human:<name> --reason "<text>"` appends `KillSwitchCleared` together with `ApprovalRecorded(kind=killswitch_clear)` (R22). `pumpgrok killswitch set --reason "<text>" [--flatten]` writes `var/desk/KILLSWITCH`; `pumpgrok killswitch status` prints every source and the ledger state. The CLI refuses `--by` values that do not start with `human:` or that match `SEAT_RE`, the same rule G-2 applies to `approved_by`. If any live source is still set, the clear is refused and lists which. No seat, tool or skill can clear (D9: RISK KILL non-overridable).
- Audit: `KillSwitchSet`, `KillSwitchCleared`, `ApprovalRecorded(kind=killswitch_clear)`, every `OrderRejected reason=kill_switch`, and a `JournalNote` with the operator's reason are all in the ledger; the desk markdown mirror writes `FLOOR HALTED - KILL SWITCH (<source>)` via tmp + `os.replace`.

### 5.5 Daily rollover (UTC)

At the first risk cycle after `00:00:00Z` (`clock.utc_day() != state.day_utc`):

1. `MarkToMarket` is forced (fresh prices; if PriceSource fails, `last_good` is used and the rollover is still recorded with `mtm_source=last_good`);
2. `DailyRollover` is appended with `day_start_equity_lamports = equity()` including open positions at MTM and `open_positions[]`;
3. `counters.trades_today`, `rejected_today`, `fees_today_lamports`, `realized_today_lamports` reset;
4. open positions are untouched (vendor behaviour, risk.py:106-117: "open positions are not touched");
5. `halt` is NOT cleared. The vendor auto-resumes at the next day (`halted` recomputes from `daily_loss`, risk.py:131-134); the constitution requires an explicit human reset (`rules/pumpgrok-team.mdc:34`, R5), so `HaltCleared` must come from the CLI. Open risk therefore carries across the rollover and counts against the new day's loss from the new `day_start_equity`.

Day attribution uses the fill timestamp (R38, F-m4): an order decided on day N whose `FillRecorded.ts_utc` is on day N+1 counts in day N+1's `trades_today`, fees and realized PnL; `day_start_equity` of day N+1 is taken after the rollover MTM and before that fill. Reports (section 8) use the `DailyRollover` boundaries, so a position opened on day 1 and closed on day 2 contributes unrealized PnL to day 1 and realized minus day-1 unrealized to day 2; the two days sum to the trade's realized PnL.

## 6. Supervisor (SPE-18030)

### 6.1 Module layout

```
src/pumpgrok/supervisor/
  __init__.py
  scheduler.py    Supervisor: builds seats from the roster, runs task-per-seat, per-seat cadence, tick alignment,
                  roster-order execution within a tick, install_signal_handlers / drain / cancel_and_wait (vendor ports), shutdown,
                  kill-switch flatten executor (waits on the PaperAdapter in-flight barrier, then calls PaperAdapter.place in-process, 5.4)
  seat_task.py    SeatTask wrapper: heartbeat (last_cycle_started/finished, staleness), RestartPolicy (token bucket 5/h,
                  exponential backoff with jitter, observe-only latch), edge-triggered Escalation events -> ledger + Notifier relay
  health.py       HealthServer (vendor port) + var/health.json writer + readiness; serves /metrics from metrics.py
  metrics.py      prometheus_client registry and text exposition (cycle latency histograms, freshness gauges;
                  vendor metric names kept); batch 5 (Phase 5 Hardening, R37)
```

Three modules per R31; the eight-file layout of the earlier draft is folded into them.

### 6.2 Cadence per seat

| Seat | Cycle trigger | Cadence (REVIEW) | Write tools | Notes |
|---|---|---|---|---|
| bot-00-chief | timer | 60 s | none (ledger `JournalNote`, ticket files) | ticket creation, human relay; never trades |
| bot-01-scout | event-driven (PumpPortal stream) + sweep timer | stream; sweep 10 s (vendor `sweeper_delay`, monitor.py stream loop) | none | emits candidates with `correlation_id` |
| bot-02-risk | timer | 5 s | `risk.kill_switch` (set / flatten_request), `desk.event_emit kind=escalation` | shortest cadence: kill-switch and breaker monitoring; `HaltSet` / `BreakerTripped` are appended by `RiskEngine` library code, not by the seat (R24) |
| bot-03-whale | timer, per candidate | 120 s | none | holder/flow |
| bot-04-sniper | queue (approved signals) | immediate, serialised | `exec.place` (side buy) | one order in flight at a time (single-send via `(ticket_id, side, decision_id)`, R23) |
| bot-05-rug | timer | 30 s | `desk.event_emit kind=escalation` | pre-trade safety + post-fill monitor (`engine/watcher.py`); RUG holds no `notify.alert` (R35): its alerts are `Escalation` events relayed by the supervisor |
| bot-06-exit | timer | 15 s (vendor `stop_loss_poll_seconds`, models.py:323) | `exec.place` (side sell) | exit rules (`engine/exits.py`); `blind_flatten` and `graduated` closes are adapter-internal and kill-switch flatten is executed by the supervisor (5.4), so none of them depend on this seat being healthy |
| bot-07-shill | timer | 300 s | none | detection only |
| bot-08-signal | queue (candidates with safety report) | immediate | none | scoring; LLM-backed with rule fallback in live-paper, recorded outcome in replay |
| bot-09-journal | timer + daily | 300 s; `00:05Z` daily, Monday `00:15Z` weekly (R40) | `MarkToMarket` every 60 s, `JournalNote`, reports | export + reports |

Within one supervisor tick (`supervisor.tick_s = 1`), due seats are started in roster order (00..09) so replay ordering is stable. Each seat runs `await bot.cycle(ctx)` inside its own `asyncio.Task` under `clock.timeout(seat.cycle_timeout_s)` (default 4 x cadence, min 30 s; virtual in replay, R27, F-M3); a timed-out cycle counts as a crash. `asyncio.timeout` / `asyncio.wait_for` are never called directly in `src/pumpgrok` (static test `tests/safety/test_virtual_time_only.py`).

### 6.3 Heartbeats and staleness

`seat_task.py` records `(started_at, finished_at, ok, duration_s)` per seat from the task wrapper, not from the bot (a bot cannot fake its own heartbeat). Staleness: `clock.now() - finished_at > 3 * cadence` (event-driven seats: `3 * sweep`) marks the seat `stale`; health goes `degraded`; an `Escalation(kind=heartbeat_stale, seat)` is emitted once (edge-triggered) and cleared when a cycle completes.

### 6.4 Bounded restarts, crash isolation, observe-only

```
on exception in bot.cycle (anything except CancelledError):
  log with correlation ids; metrics pumpgrok_bot_crashes_total{seat}
  if restart_bucket[seat].try_take():                 # capacity 5, refills 1 per 12 min (5/h)
      backoff = min(16, 2 ** attempt) + rng.uniform(0, 1)   # 1,2,4,8,16 s + jitter from the seeded rng, attempt resets after 1 h clean
      await clock.sleep(backoff); reschedule seat
  else:
      seat.mode = observe_only                        # registry stops resolving its write tools; cycle still runs
      append Escalation(kind=bot_restart_exhausted, seat); relay to Notifier.alert(critical)
      if seat == bot-04-sniper: no new buys desk-wide (nobody else can buy)
      if seat == bot-06-exit:   RiskEngine appends HaltSet(reason=manual, detail="exit seat observe-only") because open positions would be unmanaged;
                                the PositionWatcher blind/graduated force-closes (adapter-internal) still run
      if seat == bot-02-risk:   desk enters observe-only for BUYS: RiskEngine.check step seat_may_trade rejects every buy;
                                exits continue; RiskEngine.check keeps running inside PaperAdapter.place for every order
                                and keeps owning HaltSet / BreakerTripped appends (R24, F-B4); the seat's monitoring and
                                kill-switch setting are lost until `state resume`, which is why the file and the alert channel
                                are polled by RiskEngine itself (sec 5.4)
```

A crash never propagates: the wrapper owns the task, the supervisor loop awaits `asyncio.wait(..., return_when=FIRST_COMPLETED)` over seat tasks plus the stop event (vendor pattern, pipeline.py:144-147; `asyncio.wait` without a timeout is not a time source), and a seat task finishing with an exception only triggers the policy above. Observe-only is cleared by `pumpgrok state resume --seat <seat> --by human:<name>`.

Escalation relay: seats that hold no `notify.alert` (RISK, RUG per R35) escalate with `desk.event_emit kind=escalation`, which appends an `Escalation` event; `seat_task.py` watches the ledger tail and relays every new `Escalation` (and every `HaltSet`, `KillSwitchSet`, `BreakerTripped`, `LiveWriteAttempted`) to `notify.alert` with the alert kind equal to the escalation kind. `notify.alert` destinations are restricted to the configured allowlist (Telegram chat ids, webhook URLs; R39). The alert kind enum therefore includes the escalation kinds `bot_restart_exhausted`, `heartbeat_stale`, `persistence_down`, `clock_skew`, `ledger_inconsistent` (R40) plus `blind_flatten`, `graduated`, `rug_alert`, `halt`, `breaker`, `killswitch`, `live_write_attempted`.

### 6.5 Graceful shutdown

SIGTERM/SIGINT -> `request_stop` (vendor semantics: second signal logs and does not force, pipeline.py:159-165) -> stop event set -> scheduler stops launching cycles -> `drain(running_cycles, grace = ops.shutdown_grace_seconds = 30)` (vendor default, models.py:382; `ops.py:406-417`; the grace wait is `clock.sleep`) -> ledger snapshot -> JSONL export flush -> `var/health.json` `status=stopped` -> HealthServer stop -> Notifier `stopped` (vendor `notify("stopped")`, pipeline.py:181-186) -> exit 0. If open positions remain, the shutdown log and alert say so (vendor warning, pipeline.py:187-190), because stop rules do not run while the process is down. A hard kill mid-append is safe: sqlite WAL with `synchronous=FULL`, `BEGIN IMMEDIATE` and the append-before-return rule mean the ledger holds either the whole event or nothing.

### 6.6 Health signals

- `GET /healthz` -> JSON, `200` if `status == "ok"` else `503` (vendor contract, ops.py:349-355); keys are the vendor `status()` keys (pipeline.py:392-419: `status, mode, uptime_seconds, stalled, open_positions, blind_positions, trades_today, realized_pnl_sol, halted, breaker, ...`; `realized_pnl_sol` is rendered from `realized_today_lamports` for compatibility) plus `autonomy_level, ledger_status, ledger_source, kill_switch, breakers{...}, seats{seat: {state, last_ok_ts, stale}}, equity_lamports, drawdown_pct, data_age_s`.
- `GET /readyz` -> `200` only after the ledger reconciled CONSISTENT and every seat completed one cycle.
- `pumpgrok run --mode paper --serve` replays a recorded dataset in a loop and serves `/healthz` and `/metrics` on `PUMPGROK_HEALTH__PORT`; `--once` and `--replay` force port `0` so CI never binds a socket (INV-C-11). While serving a recording the health body carries `ledger_source=replay`.
- `GET /metrics` -> `prometheus_client` text (D5) from `supervisor/metrics.py`, metric families: `pumpgrok_cycle_seconds{seat}` histogram, `pumpgrok_bot_crashes_total{seat}`, `pumpgrok_orders_total{side,outcome}`, `pumpgrok_equity_lamports`, `pumpgrok_drawdown_pct`, `pumpgrok_data_age_seconds{source}`, `pumpgrok_breaker_state{breaker}` (0 closed, 1 half-open, 2 open), `pumpgrok_kill_switch`, `pumpgrok_ledger_seq`.
- `var/health.json`: the `/healthz` body written atomically (tmp + `os.replace`, the helper in `ledger/store.py`, R26) every `health.file_interval_s = 10`; Hermes cron prompts and `desk_state.py` can read it without HTTP.

### 6.7 Degraded modes

| Failure | Detection | Behaviour | Recovery |
|---|---|---|---|
| LLM (x.ai) down, 5xx, 429, budget exhausted | vendor `GrokOps.precheck` + breaker (ops.py:235-297) ported into `core/llm.py` | live-paper: bot-08-signal falls back to rule-based scoring (metrics-only component weights, vendor `compute_scores` with missing components = 0.0, scoring.py); if `signal.require_llm = true` (REVIEW default false for paper) the desk is observe-only for new buys; exits unaffected. Replay: the recorded `outcome` (`ok` / `timeout` / `error`) is returned after the recorded virtual `latency_s`; a missing record fails the replay, never a silent fallback (R27) | breaker half-open probe succeeds |
| RPC down | tenacity retries (`sleep=clock.sleep`) with jitter, then failover to the next `rpc.endpoints[]` entry (D8 failover list) in `tools/onchain/rpc.py` | after all endpoints fail: `ExecErrors` breaker counts `rpc_error`; safety checks that need RPC return `BLIND` and RISK treats BLIND as KILL for that token (constitution: missing data = KILL, agents/risk.md) | endpoint health probe every 30 s |
| PumpPortal WS down | reconnect backoff 1 -> 60 s (vendor monitor.py stream loop, `clock.sleep`) | `DataStale` trips after 120 s; REST polling of open positions continues at 15 s | fresh frames |
| pump.fun REST down | httpx errors | prices from last PumpPortal tick; `DataStale` if both silent; `blind_flatten` at `blind_max_s` (R25) | first successful read |
| Ledger unwritable | `LedgerUnavailable` | refuse orders, bounded buffer, `Escalation(persistence_down)` (section 3.5) | append succeeds; buffer drains in order |
| Seat restart budget exhausted | seat_task.py | observe-only + escalation (section 6.4); RISK seat -> buys off, exits on | human `state resume` |
| Clock skew / NTP jump backwards | `clock.now() < last_event_ts - 5 s` | refuse to append (hash chain would be non-monotonic in ts), `Escalation(clock_skew)`, observe-only | clock catches up |

## 7. Live gate and autonomy level (SPE-18035)

### 7.1 Config keys (pydantic-settings, in-package TOML overlays, env `PUMPGROK_*`)

Overlays live in-package at `src/pumpgrok/config/overlays/{dev,paper,live}.toml`, selected by `PUMPGROK_PROFILE` (default `paper`); an optional `PUMPGROK_CONFIG=<file>` is applied last as the operator overlay; secrets only via env. There is no `config/` directory at the repo root (R30, R4). Effective mode precedence: CLI `--mode` > env `PUMPGROK_MODE` > TOML `execution.mode`; the live gate evaluates the merged effective mode (R30), so `pumpgrok run --mode live` with a paper overlay still runs the gate.

```toml
[execution]
mode            = "paper"              # "paper" | "live"; default paper (D4); overridden by PUMPGROK_MODE then --mode
autonomy_level  = "autonomous-paper"   # "manual-ticket" | "autonomous-paper"; config validation forces manual-ticket when the effective mode is live

[live]                                  # evaluated only when the effective mode is live (section 7.2)
enabled            = false            # D4, R21 (1): precondition 1 reads this alongside the effective mode; overlays keep it false
min_paper_days      = 14               # D4, R21 (3); the window starts at the first source=paper event in var/ledger.sqlite (R41), never a config value
wallet_allowlist    = []               # base58 public keys only; never private material (R21 (5))
notional_cap_sol    = 0.0              # per-order cap; 0 < value <= 1.0 required (R21 (6)); the one SOL-denominated live key, converted to lamports at load
confirmation_record = "var/live_confirmation.json"   # HMAC-signed human confirmation written by `pumpgrok live confirm` (7.3, R21 (7))
adapter             = ""               # must name a registered live adapter implementation; none ships (R21 (8))

[live.thresholds]                      # R21 (4), computed over ledger events with source=paper only (REVIEW)
closed_trades       = 50
profit_factor       = 1.2
max_drawdown        = "drawdown_halt_fraction"   # bound to [risk].drawdown_halt_fraction (0.15)
```

`PUMPGROK_LIVE_ENABLE` is env-only (never a TOML key) so that a committed overlay can never satisfy precondition 2.

### 7.2 Preconditions and startup error

`LiveGate.check() -> Sequence[str]` (`src/pumpgrok/execution/live/live_gate.py`, R31) runs in `cli.py` before anything else starts whenever the effective mode is `live`. It collects every unmet precondition id (it does not stop at the first) and, if the list is non-empty, prints the block below to stderr and exits `3` (distinct from `1` config parse errors and `2` ledger inconsistent). The same exit code is documented in docs/FOUNDATION_STACK.md.

The ONE precondition list (R21), identical to the `LiveGate` docstring in docs/design/interfaces.md:

```
  1. mode_live: effective execution.mode == live AND [live] enabled = true (R30 precedence for the mode: CLI --mode > env PUMPGROK_MODE > TOML execution.mode; every overlay ships enabled = false)
  2. live_enable_env: env PUMPGROK_LIVE_ENABLE=1
  3. min_paper_days: live.min_paper_days >= 14 elapsed, measured ONLY on ledger events with source=paper (never replay)
  4. performance_thresholds: on the same source=paper events: closed_trades >= 50, profit_factor >= 1.2, max_drawdown <= drawdown_halt_fraction
  5. wallet_allowlist: live.wallet_allowlist non-empty (public addresses only)
  6. notional_cap: 0 < live.notional_cap_sol <= 1.0
  7. confirmation_record: live.confirmation_record = HMAC-signed human confirmation produced by `pumpgrok live confirm` with an operator secret that no seat/tool can read, bound to the config hash
  8. adapter_registered: live.adapter explicitly named AND an implementation registered (none ships -> always unmet)
  9. no_active_stop: no active kill switch, halt, or open breaker
```

Any unmet -> startup exits 3 printing every unmet item. Replay runs write `var/replay/<dataset>/ledger.sqlite`; every ledger event carries `source` in `{paper, replay, manual}`; `LiveGate` refuses any ledger containing `source=replay` for its metrics (ids 3 and 4 report `unmet: replay ledger`), so a `FixtureClock` can never fabricate the paper window (F-B1, F-m8). The paper window start is not a config key: `paper_started_at` = `ts_utc` of the first `source=paper` event in `var/ledger.sqlite` (R41), and the elapsed days for id 3 are `clock.utc_day - paper_started_at.utc_day`.

Sample stderr (lines are generated from the precondition list, so the count and the `[x]/[ ]` marks are always consistent; the sample shows the shape):

```
LIVE GATE: refusing to start in mode=live. 6 of 9 preconditions unmet:
  [x] 1 mode_live                 OK (effective mode live, from --mode)
  [ ] 2 live_enable_env           PUMPGROK_LIVE_ENABLE unset
  [ ] 3 min_paper_days            9 of 14 days on source=paper events
  [x] 4 performance_thresholds    OK (closed 73, pf 1.32, dd 8.4 % <= 15 %)
  [ ] 5 wallet_allowlist          empty
  [x] 6 notional_cap              OK (0.1 SOL)
  [ ] 7 confirmation_record       var/live_confirmation.json missing
  [ ] 8 adapter_registered        live.adapter="" and no implementation registered
  [ ] 9 no_active_stop            halt active: daily_loss
Fix every unmet line or run in mode=paper. No transaction was sent.
```

When the effective mode is `paper` the gate is not evaluated; `LiveAdapter` construction re-runs `check()` anyway (section 7.4).

### 7.3 Signed human confirmation record

```json
{
  "ledger_id": "<ULID from meta>",
  "config_hash": "<sha256 of the canonical merged effective config>",
  "confirmed_by": "human:<name>",
  "confirmed_at": "2026-10-30T09:12:00Z",
  "expires_at": "2026-10-31T09:12:00Z",
  "notional_cap_lamports": 100000000,
  "wallet_allowlist_sha256": "<sha256 of sorted allowlist>",
  "statement": "I confirm live trading with the listed wallet and cap. I have read SECURITY.md and RISK_POLICY.md.",
  "signature": "<base64 HMAC-SHA256 over the canonical JSON of the fields above, keyed by PUMPGROK_CONFIRMATION_KEY>"
}
```

`PUMPGROK_CONFIRMATION_KEY` is an operator-held secret that no seat or tool can read (it is in `forbidden_env_keys` and the registry denies it); only `pumpgrok live confirm` (which writes the file) and `LiveGate.check` read it. The record is bound to the config hash (R21 (7)): any change to the merged effective config invalidates it. An HMAC rather than an asymmetric signature is sufficient because the goal is "a human with the key did this on purpose", not third-party verification (REVIEW: switch to ed25519 if external auditability is required). The confirmation is also appended to the ledger as `ApprovalRecorded(kind=live_gate)` with the signature, so the decision is auditable (R33).

### 7.4 `LiveAdapter` stub and `LiveGateError`

`src/pumpgrok/execution/live/live_adapter.py` defines `LiveAdapter(LiveAdapterStub)`; the base class and `LiveGateError` are the ones in docs/design/interfaces.md section 2.7 (`LiveGateError` subclasses `PermissionDenied` and carries `unmet: list[str]`). Every method raises, including `quote` and `simulate`; construction itself raises when `LiveGate.check()` is non-empty and raises `unmet=["adapter_registered"]` even when it is empty, because no venue implementation ships (R21 (8)).

```python
class LiveAdapter(LiveAdapterStub):
    async def place(self, order):
        await self._audit(order, "place")
        raise LiveGateError("live place disabled", unmet=list(self._gate.check()))

    async def cancel(self, order_id, ticket_id, decision_id):
        await self._audit(None, "cancel")
        raise LiveGateError("live cancel disabled", unmet=list(self._gate.check()))
```

`_audit` appends `LiveWriteAttempted(adapter="live", method, caller_seat, gate_result)` before raising, so an attempt is recorded even though nothing happened. Under D3 no seat can resolve a live-write tool from the registry in the first place, so reaching `LiveAdapter.place` already means a registry bug; the ledger event plus a critical Notifier alert makes that visible. There is no code path in `LiveAdapter` that builds, signs or sends a transaction (D4); the six-step vendor TODO (executor.py:151-162) is not carried over. No live auto-exit exists: an EXIT sell in live mode hits the same `LiveGateError` (R17).

### 7.5 Autonomy level: manual-ticket vs autonomous-paper

Both exist in paper mode; config validation forces `manual-ticket` when the effective mode is live. Switching: `pumpgrok state autonomy <manual-ticket|autonomous-paper> --by human:<name>` appends `ConfigChanged` and a `JournalNote` (satisfying "writes a higher autonomy level in the journal", agents/sniper.md:27); setting it back is immediate.

| | `manual-ticket` | `autonomous-paper` |
|---|---|---|
| Who approves a buy | the human, by posting the exact phrase | `RiskEngine.check` passing is the approval; it mints `ApprovalRecord(kind=autonomous_paper, approved_by="risk_engine")` (R24: library code, not the seat) |
| Exact phrase | `approve <ticket> <mint> <size> <slippage>` where ticket matches `SOL-\d{8}-\d{3}` (`tools/desk_state.py:32`), mint is the base58 CA, size in SOL (converted to lamports once, in `core/approvals.py`), slippage in bps; constitution: `rules/pumpgrok-team.mdc:28`, `agents/chief.md:49`, `agents/sniper.md:27` | not required; the ticket is still created with `Status: AUTO_APPROVED_PAPER` |
| Who approves a sell | the EXIT seat's rule engine (`engine/exits.py`) is the autonomous paper-write path, but each exit rule must be approved per ticket by the human: `ApprovalRecord(kind=exit_rule, ticket_id, exit_rule_id, approved_by="human:<name>")` (R17); `rug_alert` and `kill_flatten` sells carry the kill-switch / escalation approval id | the rule engine is always on; sells carry `kind=autonomous_paper` |
| Where the approval is recorded | `ApprovalRecorded` ledger event (R33; never a `JournalNote`) plus `OrderPlaced.approval{kind, approval_id}`; the phrase is matched token-for-token against the ticket, mismatch -> `OrderRejected reason=approval_mismatch` | `ApprovalRecorded(kind=autonomous_paper)` then `OrderPlaced.approval{kind=autonomous_paper, approval_id}` |
| Purpose | the Telegram human-in-the-loop desk as it exists today | the 2-4 week unattended paper run that produces the live-gate statistics |

Everything else (sizing caps, kill switch, breakers, halts, single-send, ledger) is identical between the two levels; `autonomy_level` only changes the `approval_missing` step of `RiskEngine.check`. "Auto-exit pre-authorised in writing" prose in the existing agent files is replaced by this table (R17).

## 8. Reporting

### 8.1 Module layout and CLI

```
src/pumpgrok/reporting/
  __init__.py
  daily.py      DailyReport.build(ledger, day_utc) -> ReportModel
  weekly.py     WeeklyReport.build(ledger, iso_week) -> ReportModel
  render.py     markdown renderer (ASCII tables, no emoji; passes scripts/check.sh); str.format templates (R9, no jinja2)
```

CLI (`src/pumpgrok/cli.py`, exposed as `pumpgrok`):

```
pumpgrok report --daily  [--day 2026-10-20] [--out var/reports] [--desk]
pumpgrok report --weekly [--week 2026-W43]  [--out var/reports] [--desk]
```

`--desk` additionally copies the file to `$PUMPGROK_DESK/journal/report-daily-YYYY-MM-DD.md` (or `report-weekly-YYYY-Www.md`), resolved exactly as `tools/desk_state.py:50-57` resolves the desk, written via tmp file + `os.replace` (R26). bot-09-journal runs the daily build at `00:05Z` and the weekly at Monday `00:15Z` (R40) and posts a five-line summary through the Notifier.

### 8.2 CLI surface used by this design (canonical names)

Every subcommand is a thin wrapper over a registry tool (`<ns>.<verb>` names per docs/TOOL_CATALOG.md) or over `ledger/store.py`; the CLI adds no logic of its own. Every verb below is in the canonical list of docs/FOUNDATION_STACK.md (R12, R40).

| Subcommand | Wraps | Section |
|---|---|---|
| `pumpgrok run --mode paper [--once] [--replay <dir>] [--record <dataset> --duration <s>]` | supervisor start; `--once` = one tick (Hermes cron wrappers); `--replay` binds FixtureClock + fixture sources and writes `var/replay/<dataset>/ledger.sqlite` with `source=replay`; `--record` wraps transports | 4.4, 6 |
| `pumpgrok verify --ledger [--explain]` / `pumpgrok verify --fixture <dataset>` | `ledger.verify`, `replay.verify` | 3.5, 4.6 |
| `pumpgrok doctor` / `pumpgrok audit` | health + readiness probe; receipt/ownership checks (programming-desk `desk_cli.py` precedent) | 6.6 |
| `pumpgrok report --daily|--weekly [--day|--week] [--out] [--desk]` | `journal.render_report` | 8.1 |
| `pumpgrok paper buy|sell --ticket --mint --size-sol --slippage-bps --approval-id` | `exec.place` through PaperAdapter (manual-ticket path); `--size-sol` is SOL at the CLI boundary only and is converted to lamports before the request is built (R40) | 2 |
| `pumpgrok killswitch set --reason <text> [--flatten]` / `status` / `clear --by <human> --reason <text>` | `set` writes `var/desk/KILLSWITCH`; `clear` is CLI-only and appends `KillSwitchCleared` with `ApprovalRecorded(kind=killswitch_clear)` (R22) | 5.4 |
| `pumpgrok state status` / `state halt --clear --by <human> --reason <text>` / `state autonomy <manual-ticket|autonomous-paper>` / `state resume --seat <seat> --by <human>` | ledger views; `HaltCleared` with `ApprovalRecorded(kind=halt_clear)`; `ConfigChanged` | 5.2, 5.5, 6.4, 7.5 |
| `pumpgrok replay trim|rebuild-ticks --dataset <name>` | `replay.trim`, `replay.rebuild_ticks` | 4.3, 4.6 |
| `pumpgrok live confirm` | writes the signed confirmation record (operator-only; needs `PUMPGROK_CONFIRMATION_KEY`) | 7.3 |
| `pumpgrok ticket next|create|list`, seat verbs (`scout discover|pipeline`, `risk audit`, `chief pickup`, `rug watch`, `journal rollup`) | owned by other nodes; listed for completeness | - |

### 8.3 Report content

Both reports have the same sections; the weekly one adds a per-day table and the live-gate threshold status.

```
# PumpGrok paper report - daily - 2026-10-20 (UTC)
Mode: paper | Autonomy: autonomous-paper | Ledger: <ledger_id> seq <n> | Equity: 10.213 SOL (+2.13 % since start)

## Summary            trades (buys/sells), closed, win rate, realized PnL, unrealized PnL, fees (venue/network), equity start/end, max drawdown (day and since start), daily loss vs halt
## Trades             table per closed position: ticket, mint (short), entry/exit price, size, hold, reason, pnl_lamports (rendered as SOL), pnl_pct, fees, correlation_id
## Open positions     table: mint, entry, mtm, unrealized, age, mtm_source, mtm_frozen
## Rejected signals   table: reason -> count (every OrderRejected.reason); top 5 mints by rejections
## Safety outcomes    RUG verdicts CLEAR/CONDITIONAL/KILL/BLIND counts (from JournalNote note_kind=verdict), post-fill escalations
## Risk events        HaltSet/HaltCleared, KillSwitchSet/Cleared, BreakerTripped/Reset, ApprovalRecorded(kind in {killswitch_clear, halt_clear}) with timestamps and who cleared
## Bot health         per seat: cycles, crashes, restarts, observe-only periods, p50/p95 cycle seconds
## Data freshness     per source: max age, stale seconds total, DataStale trips, blind_flatten closes
## Live gate          (weekly only) each of the nine precondition ids with current value and OK/unmet, computed on source=paper events only
## Unverified         anything computed from last_good prices, or days with ledger_inconsistent
```

Rendering is pure: `ReportModel` is built from ledger views and the renderer has no I/O, so `tests/test_reporting_render.py` can snapshot-test the markdown from a fixture ledger. Lamport integers are rendered as SOL with 9 decimals only at render time.

## 9. Test list

All tests are pytest with `asyncio_mode = auto` (D5), use `FixtureClock` and the seeded RNG, and never touch the network (`tests/conftest.py` installs an `httpx` transport that raises on any un-mocked request, plus a `websockets.connect` monkeypatch, the vendor test pattern `tests/test_filter.py` FakeWebSocket). The static safety tests (`test_virtual_time_only`, `test_no_uuid`, `test_money_is_int`) are listed in docs/design/interfaces.md section 4 and are not repeated here.

| File | What it asserts |
|---|---|
| `tests/execution/test_paper_fill_model.py` | `curve_math` invariants on integer reserves (`k` constant after buy and sell up to integer flooring, `impact_buy == x/S`, `buy_out` then `sell_out` round-trips within fee); the worked example of section 2.9 (full fill at S1=42.1, `slippage_exceeded` at S1=42.5, partial at size 1.5 with the threshold recomputed for the executed size); `below_liquidity_floor` when `S0 < 10 * size`; `tx_dropped` when the seeded draw says so, with no cash change; fee split equals `venue_fee + base + priority`; `cancel` succeeds in ACCEPTED and fails after latency; `simulate` writes no ledger events; a BUY on a `complete` curve is rejected `post_graduation_no_reserves`; an open position whose curve turns `complete` gets `PositionClosed reason=graduated` at the last curve price and `mtm_frozen=true` (R8, R38) |
| `tests/ledger/test_ledger_restart_reconcile.py` | append N events, kill the writer mid-way (simulated by closing the connection), reopen: chain verifies, snapshot + tail equals full replay; tamper one `payload_json` via a raw connection with triggers dropped -> `INCONSISTENT`, `HaltSet(ledger_inconsistent)` appended, `RiskEngine.check` rejects; duplicate `idempotency_key` -> `IntegrityError` surfaced as a refused order; views (cash, positions, realized, unrealized, equity curve, drawdown) match hand-computed lamport integers from a 6-event fixture; JSONL export resumes from `meta.export_seq` without duplicates; vendor-shape `trades.jsonl` lines validate against the key sets of `log.py:98-183`; every event row carries `source` |
| `tests/ledger/test_single_writer_concurrent_appends.py` | two processes (supervisor and `pumpgrok paper buy` CLI) append 200 events each through `ledger/store.py`; the chain verifies, `seq` has no gaps, every `prev_hash` matches, no `UNIQUE` violation on `hash` (R26 `BEGIN IMMEDIATE`) |
| `tests/replay/test_replay_determinism.py` | two runs over `smoke-10m` give identical `events.hash` sha256, identical JSONL bytes, identical final state and identical ULIDs; a run with a different seed differs (so the seed is actually wired); a fixture with a 180 s hole trips `DataStale` at the right virtual time; a replay whose `llm.jsonl` lacks a record for a request the desk makes FAILS with `ReplayMissingRecord` (R27); the run is repeated with `FixtureClock` while the host sleeps 2 s of real time inside a cycle and the events are byte-identical (F-M3) |
| `tests/risk/test_kill_switch_one_cycle.py` | create the latch file, or send a KILL line through the alert channel (fake transport; it writes the same file), in two parametrised cases (env `PUMPGROK_KILLSWITCH` is a third case that starts the process already switched, since env is read at start only); advance `FixtureClock` by one risk cadence (5 s); assert zero `FillRecorded side=buy` after the set time, `KillSwitchSet` present with the correct source; with `flatten_request` every open position has `PositionClosed reason=kill_flatten`; `risk.kill_switch(action="clear")` is a validation error; `pumpgrok killswitch clear --by bot-02-risk` refused, `--by human:alice` accepted only after all sources are clear and appends `KillSwitchCleared` plus `ApprovalRecorded(kind=killswitch_clear)` |
| `tests/risk/test_kill_switch_in_flight.py` | an order in `ACCEPTED` (latency sleep pending) when the switch is set is rejected at `CONFIRMING` with `reason=kill_switch` and no `FillRecorded`; the same for `halted` and `breaker_open`; `flatten_request` waits on the in-flight barrier before closing positions, so no buy opens after a flatten was requested (R22, F-B5) |
| `tests/execution/test_live_gate_fails_fast.py` | parametrised over each of the 9 preconditions removed one at a time: `cli.main(["run", "--mode", "live"])` exits `3` and stderr lists exactly that id as `[ ]`; `--mode live` with a paper overlay runs the gate (R30, F-M8); all present except 8 -> construction raises `LiveGateError(unmet=["adapter_registered"])`; default config (`pumpgrok run` with no `--mode`) yields effective mode `paper` and the gate is never evaluated; `LiveWriteAttempted` appended on every `place`/`cancel` |
| `tests/safety/test_live_gate_rejects_replay_ledger.py` | a ledger with one `source=replay` row is refused for metrics (ids 3 and 4 unmet with `replay ledger`); `source=paper` only is accepted (R21, F-B1) |
| `tests/supervisor/test_supervisor_bounded_restart.py` | a seat whose `cycle` raises every time is restarted 5 times within a virtual hour with backoff 1,2,4,8,16 (+jitter in [0,1) from the seeded RNG), then latched observe-only with one `Escalation(bot_restart_exhausted)`; other seats keep ticking (heartbeats advance); bot-02-risk latched observe-only -> `RiskEngine.check` still runs inside `PaperAdapter.place`, buys are rejected `seat_may_trade` desk-wide, an EXIT sell still fills (R24, F-B4); SIGTERM handler: stop event -> drain -> snapshot written -> `health.json status=stopped` -> return 0; `/healthz` 503 while a seat is stale and 200 after it recovers; `Escalation` events are relayed to `notify.alert` with allowlisted destinations only (R39) |
| `tests/risk/test_breaker_trip_and_cooldown.py` | for each breaker: trip condition met -> `BreakerTripped`, buys rejected `breaker_open`, sells allowed; clock advanced past cooldown -> half-open admits exactly one probe; probe failure re-opens with a fresh cooldown and appends a `BreakerTripped` row; `reset_after_ok` successes -> `BreakerReset`; breaker state survives a ledger restart (reconstructed from events); `BreakerTripped` is idempotent per `(breaker, occurrence)` (R24) |
| `tests/engine/test_blind_flatten.py` | an open position with no price for `blind_max_s = 300` virtual seconds is force-closed at `last_good` with `PositionClosed reason=blind_flatten`, `mtm_frozen=true`, and an `Escalation` is appended (R25, F-M1) |
| `tests/risk/test_daily_rollover.py` | an order decided at 23:59:58Z that fills at 00:00:01Z counts against day N+1's `trades_today` and realized PnL (fill timestamp attribution, R38, F-m4); `HaltSet(daily_loss)` is not cleared by the rollover (R5); `HaltSet` is idempotent per `(reason, utc_day)` |
| `tests/soak/test_soak_multiday_replay.py` (marked `slow`, nightly) | replay `soak-3d`: `tracemalloc` samples every virtual hour, peak RSS growth after the first hour is under 20 MB (REVIEW); `sys.excepthook` and `loop.set_exception_handler` wired to fail the test on any unhandled exception; at least one `DailyRollover` per day; ledger verifies at the end; report renders for each day |
| `tests/reporting/test_reporting_render.py` | daily and weekly markdown snapshot from a fixture ledger; ASCII only; every section header present; rejected-reason table sums to `count(OrderRejected)`; nine live-gate ids in the weekly report |
| `tests/characterization/test_vendor_ports.py` | vendor behaviour pinned before porting: `price_from_reserves` on the three payload shapes (executor.py:85-97), `exit_signal` priority and boundaries (risk.py:238-280), `RiskManager.position_size` (risk.py:145-149), `CircuitBreaker` half-open (ops.py:131-182), `parse_create_event` timestamp heuristics (monitor.py:61-83); the same cases run against the ported modules; owned by the owner of the module each case pins (R36) |

## 10. Shared interfaces and module placement

Defined in `src/pumpgrok/core/interfaces.py` (docs/design/interfaces.md, node n3): `Tool`, `Skill`, `Bot` (`cycle(ctx)`), `ExecutionAdapter` (five methods: `quote`, `simulate`, `place`, `cancel`, `positions`), `DataSource`, `ToolRegistry.find(capability, max_side_effect, bot)`, `Notifier` (`alert(severity, text, **fields)`, `notify(event, ...)`, inbound `commands()` async iterator for the alert-channel kill command), `LiveGateError` (subclass of `PermissionDenied`; this document does not define its own). Ids come from `src/pumpgrok/core/ids.py` (`IdFactory`, `CorrelationId`), approvals from `src/pumpgrok/core/approvals.py` (`ApprovalRecord`). This document adds `PriceSource`, `Clock` and `LedgerStore` and n3 re-exports them from `core/interfaces.py`.

`src/pumpgrok/core/interfaces.py` is the module that defines these names; `src/pumpgrok/core/__init__.py` is a re-export facade only (`from .interfaces import *`, plus `ids`, `approvals`, `registry`) and defines nothing itself. Both documents state this so that imports in `src/pumpgrok/**` target `pumpgrok.core` while the definitions have exactly one home.

Module placement (R31, single truth; every module appears in exactly one R37 batch):

| Module | Contents | Owner | Batch |
|---|---|---|---|
| `src/pumpgrok/core/{interfaces,registry,ids,approvals}.py` | section 10 above | bot-02-risk | 1 |
| `src/pumpgrok/config/overlays/{dev,paper,live}.toml`, `src/pumpgrok/config/settings.py` | pydantic-settings models, precedence (R30), live-gate config validation | bot-02-risk | 1 |
| `src/pumpgrok/logging/` | JSON formatter, contextvars correlation stamping | bot-02-risk | 1 |
| `src/pumpgrok/ledger/store.py` | `LedgerStore`: sqlite WAL, `BEGIN IMMEDIATE` append, hash chain, snapshots, tmp+`os.replace` atomic writer | bot-02-risk | 1 (skeleton), 4 (reducer/views/reconcile) |
| `src/pumpgrok/ledger/events.py` | the 18 event types (R32), `EventType` enum, snake_case mapping | bot-02-risk | 1 |
| `src/pumpgrok/ledger/{reducer,views,reconcile}.py` | section 3.4, 3.5 | bot-02-risk | 4 |
| `src/pumpgrok/ledger/{export,desk_bus}.py` | section 3.6 | bot-02-risk | 4 |
| `src/pumpgrok/replay/{clock,rng,fixtures}.py` | section 4.2, 4.3 | bot-02-risk | 1 |
| `src/pumpgrok/replay/{sources,recorder,runner}.py` | section 4.3, 4.4, 4.5 | bot-02-risk | 2 |
| `src/pumpgrok/tools/onchain/rpc.py` | shared JSON-RPC client, failover, recorder hook | bot-05-rug | 2 |
| `src/pumpgrok/engine/{monitor,analyzer,scoring,agents,llm,ops}.py` | vendor engine port; `llm.py` x.ai client; `ops.py` RateLimiter and CallBudget ports | bot-08-signal (engine), bot-01-scout (monitor) | 2 |
| `src/pumpgrok/engine/exits.py` | `ExitSignal`, exit rules | bot-06-exit | 2 |
| `src/pumpgrok/engine/watcher.py` | `PositionWatcher` | bot-05-rug | 2 |
| `src/pumpgrok/execution/{paper_adapter,curve_math,fees,latency}.py` | section 2 | bot-04-sniper | 4 |
| `src/pumpgrok/execution/live/{live_adapter,live_gate}.py` | section 7 | bot-02-risk (ownership rule placed after `src/pumpgrok/execution/**`) | 4 |
| `src/pumpgrok/risk/{engine,limits,sizing,breakers,killswitch}.py` | section 5; the class is `RiskEngine` | bot-02-risk | 4 |
| `src/pumpgrok/supervisor/{scheduler,seat_task,health}.py` | section 6 | bot-00-chief | 4 |
| `src/pumpgrok/supervisor/metrics.py` | `prometheus_client` registry and text exposition (metric families of 6.6); `health.py` serves it on `/metrics` | bot-00-chief | 5 |
| `src/pumpgrok/reporting/{daily,weekly,render}.py` | section 8 | bot-09-journal | 4 |
| `src/pumpgrok/cli.py` | section 8.2 | bot-00-chief | 1 (skeleton), 4 |

## 11. Contradictions found with D1-D9 (reported, not resolved)

1. D9 / vendor halt semantics: the vendor auto-clears the daily-loss halt at the next UTC day (`risk.py:106-117`, `:131-134`); the constitution requires an explicit human reset (`rules/pumpgrok-team.mdc:34`). This design follows D9 and R5; the characterization test for `RiskManager.halted` must therefore be marked as "vendor behaviour, intentionally not ported".
2. D6 "5% daily loss halt" vs vendor `daily_loss_limit_sol = 2.0` absolute SOL (`models.py:319`): the vendor limit is absolute, D6 is a fraction of equity. Design uses `daily_loss_halt_fraction` (R20); the absolute SOL knob is dropped.
3. D6 "10x liquidity floor" and "partial fill above 2 % of pool liquidity" interact (section 2.6): only sizes up to `S/50` fill fully; sizes in `(S/50, S/10]` always partially fill (R6). With 10 SOL equity and 2 % sizing (0.2 SOL) a full fill needs `S >= 10 SOL`; pump.fun curves start at 30 SOL virtual so this is workable, but the operator should know most early-curve orders will be partial if the equity is raised.
4. Writing contract (ASCII only) vs constitutional strings: `FLOOR HALTED <U+2013> DAILY LOSS LIMIT` (`rules/pumpgrok-team.mdc:34`) and `UNKNOWN RESULT <U+2013> reconcile by signature` (`:30`) contain an en dash (U+2013), which cannot be reproduced in this ASCII-only document. The code constants carry the constitution's bytes (R7); `scripts/check.sh` only rejects emoji ranges, not dashes, so the source files pass.
5. D8 "venues kept exactly as integrated today" vs post-graduation fills: no D8 data source exposes post-graduation pool reserves, so post-graduation venues are not modelled (R8, R38). A BUY on a graduated token is rejected `post_graduation_no_reserves`; an OPEN position whose token graduates is force-closed at the last curve price with `PositionClosed reason=graduated` and its MTM frozen. Documented limitation; no venue client is added.
6. D5 lists no templating library; section 8 therefore uses `str.format` templates, not jinja2 (R9).
7. `tools/pipeline_evidence.py --candidates` filters `tx_hash == "dry_run"` (equality); the ledger's `venue_tx_ref` is `dry_run:<ULID>` to keep paper refs unique. The vendor-shape export emits the bare `dry_run` string in `tx_hash` and the ULID in `venue_tx_ref`, so no tool change is forced.
8. D5 "tenacity (jittered retries)" vs replay determinism: tenacity's default sleeper is real time. Every retrier is constructed with `sleep=clock.sleep` and jitter from the seeded RNG (R27); a static test enforces it.
9. Vendor `JitoConfig` / `tip_lamports` (`models.py:291-294`) is not carried: Jito is dead config, not a D8 venue, and no key material exists in paper mode (R3). The fee model has no tip term.

## Unverified Items

| # | Unknown | Default assumed in this design |
|---|---|---|
| 1 | pump.fun venue fee is exactly 100 bps on both buy and sell for the current program version | `venue_fee_bps = 100` (REVIEW) |
| 2 | pump.fun initial virtual reserves (30 SOL / 1,073,000,000 tokens) used in the worked example | used only for the example; the adapter reads reserves from the data source |
| 3 | pump.fun REST `/coins/{mint}` exposes a `complete` boolean for graduation; the vendor only reads `virtual_sol_reserves`, `virtual_token_reserves`, `market_cap`, `usd_market_cap` (executor.py:86-96) | graduation detected by `complete` if present, else by `S >= CURVE_COMPLETION_SOL = 85` (monitor.py:30) |
| 4 | PumpPortal trade frames carry `vTokensInBondingCurve` alongside `vSolInBondingCurve` (vendor reads only the SOL side, monitor.py:155) | recorder captures the raw frame; `ticks.jsonl` falls back to REST `virtual_token_reserves` when the WS field is absent |
| 5 | Compute units consumed by a pump.fun buy/sell for the priority-fee cost | `compute_units = 200_000` (REVIEW) |
| 6 | Whether Jupiter lite-api quotes graduated pump.fun tokens | irrelevant to fills: the Jupiter quote is informational only (R38); a graduated token is never bought |
| 7 | Confirmation latency distribution on Solana mainnet for priority-fee'd pump.fun swaps | lognormal median 1.2 s, sigma 0.5, clip [0.4, 20] s; `p_drop = 0.02` (REVIEW) |
| 8 | Whether a `slippage_exceeded` failure on-chain still pays base + priority fee | charged (REVIEW); `tx_dropped` not charged |
| 9 | Telegram inbound command availability: `hermes/profiles.yaml:16,29` give only chief a token and inbound; the alert channel (sec 5.4) polls getUpdates only for allowlisted chats | Verified against a fake transport only (`tests/risk/test_alert_channel.py`); a live bot has not been exercised. Env (start-time) and file sources always work and do not depend on Telegram |
| 10 | Nightly CI artifact store for `soak-3d` | named in `.github/workflows/ci.yml` by n5/n8; the soak test skips with a clear reason if the dataset is absent |
| 11 | Exact event-count scale per day for snapshot cadence | 500 events / 300 s (REVIEW) |
| 12 | Live-gate performance thresholds (`closed_trades >= 50`, `profit_factor >= 1.2`, `max_drawdown <= drawdown_halt_fraction`) | as fixed by R21 (REVIEW); they gate nothing in paper mode |
| 13 | HMAC vs asymmetric signature for the human confirmation record | HMAC-SHA256 with `PUMPGROK_CONFIRMATION_KEY` (REVIEW) |
| 14 | `daily_loss_basis` total (realized + unrealized) vs realized-only (vendor) | total (REVIEW) |
| 15 | Soak memory bound | 20 MB growth after warm-up over three virtual days (REVIEW) |
| 16 | sqlite `BEGIN IMMEDIATE` contention between the supervisor and a CLI writer under WAL | `busy_timeout = 5000 ms` (REVIEW); a timed-out CLI append is reported, never retried silently |
