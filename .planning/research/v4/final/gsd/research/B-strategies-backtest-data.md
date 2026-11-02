# DESIGN B: live market data, recorder, strategy framework, backtest v2 (milestone v4)

Tags: [V] verified in repo or official doc, [O] observed live by scout (research2.md), [U] unverified or inferred. Interface agreements with Design C (risk, promotion, live) are marked (C).

## 0. Verified findings that shape the design

1. [V] `curve_layout.py` unpacks `<8sQQQQQB` as (disc, vsol, vtok, rsol, rtok, supply, complete) and requires `len(data) == 49`. Official BondingCurve (research2 §4) is token-first: virtual_token, virtual_sol, real_token, real_sol, supply, complete at offset 48, then more fields (166 bytes). The repo swaps both pairs and rejects every current account; `encode_curve_fixture` writes the same swapped order, so existing curve tests pass against a wrong layout; the discriminator (17b7f83760d8ac60) is never checked.
2. [V] `rpc_curve_price_allowed` returns True for every source except "rpc" (fail-open for new names); called at `paper_adapter/buy.py:250` and `confirm.py:127`.
3. [V] `CurveSnapshot` S and T are VIRTUAL reserves (`curve_math.py`), exactly what TradeEvent carries post-trade: a decoded TradeEvent is a full integer tick with no account read.
4. [V] `tick_to_candidate` divides tick `S` (virtual) by the 85 SOL bar; virtual SOL starts at 30 SOL, so live progress is overstated by about 0.35 (the 0.40 default would admit about 4 SOL of real inflow). Hand-authored fixtures are unaffected.
5. [V] `run_replay` and `evaluate_candidates` treat EVERY events.jsonl line as a tick candidate (no `kind` filter) and `run_replay` raises DataStale on any gap over `STALE_GAP_S` = 120 s: non-tick data needs other listed files and gapped recordings need segmentation (§3).
6. [V] `RiskEngine._step_data_stale` fails ALL buys if any held mint's MarkToMarket is older than `mtm_interval_s` (60 s): silent mints need marks too.
7. [V] `ExitRules` is typed on `FixtureCurveSource` but uses only `curve`, `reserves`, `last_open_reserves`, and skips a graduated position while `last_open_reserves` is None: a live source with those methods fails closed in the migration gap with no behavior change.
8. [V] `scripts/probe_curve_layout.py` repeats the swapped layout, requires exactly 49 bytes and writes VERIFIED for any account that decodes (no cross-check, no human review). Tests pin the state across seats: `CURVE_ACCOUNT_SIZE` is imported by tests of four seats, `LAYOUT_STATUS == "ASSUMED"` is asserted in tests/execution (sniper) and tests/docs (risk), and tests/docs drives the probe script.
9. [V] tests/conftest.py blocks websocket `connect` and patches `pumpgrok.engine.monitor.connect`; each new websocket module needs its own patch line and an injectable `connect` factory. Ownership (via `resolve_owner`): cli/** and tests/** default to bot-02-risk (only `cli.py` is chief); supervisor/**, scripts/**, tests/desk/** are chief.

## 1. Live data pipeline (package `src/pumpgrok/datafeed/`, bot-02-risk)

**Typed events** (frozen pydantic v2, integer lamports/units, `ts` from the injected Clock = knowledge time): `NewTokenSeen`, `CurveTick`, `CurveCompleted`, `MigrationSeen`, `FeedGap`, `FeedResynced`, `MintEvicted`, published through one `Publisher` protocol (the bus is Design A's). `CurveTick`: mint, ts, S, T (virtual), rS, rT (real), complete, slot, bt (block time), source, plus integer aggregates since the mint's previous tick: nb, ns, bv, sv (buy/sell counts and lamports), ub (cumulative unique buyers, None unless observed since creation), cs (creator-sold lamports), topb_ppm (largest buyer share of buy lamports), mm (mayhem).

**Sources, one connection each.**
- `PortalSource`: wss://pumpportal.fun/api/data, ONE connection [V FAQ], `subscribeNewToken` and `subscribeMigration`, free and keyless [O]; paid trade streams are never subscribed (R45). Create frames parse the observed fields (mint, bondingCurveKey, solAmount, name, symbol, uri, is_mayhem_mode); the migration schema is [U], so only `mint` and `signature` are required and the rest is dropped and counted. Frames are hints; logs are authoritative. `LaunchMonitor.stream` is not started in live-paper (one-connection rule); its `passes_filter` stays reusable.
- `LogsSource`: `logsSubscribe` `{mentions: [curve PDA]}` at confirmed, one websocket [V docs] (that a curve-PDA mention sees every trade is [U] until the probe). Per notification: skip `err != null`; walk log lines with an invoke stack and decode `Program data:` only when the top frame is the pump program 6EF8rrec...; base64, match the 8-byte discriminator (TradeEvent bddb7fd34ee661ee, CreateEvent 1b72a94ddeeb6376, CompleteEvent 5f72619cd42e9808, CompletePumpAmmMigrationEvent bde95db95c94ea94, PostCompleteBuyEvent), parse Borsh little-endian in `tools/onchain/pump_events.py` (bot-05-rug). TradeEvent decoding reads sequentially to `mayhem_mode` and ignores appended fields; truncation raises typed `EventDecodeError` (counted, fail closed); unknown discriminators are counted, never guessed. emit_cpi events are invisible to logs; pump uses emit! [O]. One subscription per curve, not the program-wide stream (high volume against the 100 MB per 30 s public cap [V]); keyed providers may use `logs_mode=program` [U].

**Bounded watch set** (`watchset.py`). Admission on NewTokenSeen: prefilter (name, symbol, uri present; SOL quote; mayhem excluded unless allowed), then PROBATION `probation_s` = 180; promotion to LONG watch needs ub ≥ 3 or rS ≥ 2 SOL within probation. Evict on completion, 900 s without trades, or age over 7200 s; held mints are pinned. `watch_max` default 128, ceiling 256; overflow drops the newest token and counts `overflow_dropped`, a coverage bias the recorder writes to the manifest (§3). Subscribe and unsubscribe pass a core `RateLimiter` at 30 per 10 s (public cap 40 per 10 s per method [V]). Every admitted token is recorded from creation whatever its outcome (survivorship, §6).

**Resync.** Connection loss emits `FeedGap`. On reconnect, per mint (held first, then newest): `getSignaturesForAddress(curve PDA, until=last_seen_signature, limit=100, confirmed)` then `getTransaction(maxSupportedTransactionVersion=0)` per missed signature, replayed in slot order flagged `resynced`. More than 3 pages re-baselines the mint (gap-marked) from `getAccountInfo` once LAYOUT_STATUS is VERIFIED, else from the newest decoded TradeEvent. Resync shares the limiter (40 per 10 s per method) with seeded jitter; `FeedResynced` closes the gap.

**REST fallback (poll on change).** `tools/social/client.py` (`fetch_coin`, `fetch_recent_trades`, `fetch_top_holders`) runs only for held mints while the logs feed is degraded (one fetch per mint per 30 s, source "rest") and for event-triggered holder enrichment when a strategy declares `needs` at entry-ready (TTL cache). Idle mints are never polled.

**LivePriceSource** (`price.py`) implements `curve`, `reserves` and `last_open_reserves` over an in-memory `MintBook`. A price is returned iff the feed is connected, the mint's subscription is acknowledged and no resync is pending (silence on a healthy feed is real: curve state changes only on trades); otherwise None (fail closed). Snapshots: `source="logs"` or "rest", `ts=None`, slot set. The adapter's CONFIRMING step already sleeps the seeded latency on the Clock and re-reads, so wall-clock paper fills see real post-latency prices.

**Mark-to-market refresh.** The only timer exists while positions are open: every `mtm_refresh_s` = 45 s (limit 60 s) the runtime writes MarkToMarket for each held mint, plus on PositionOpened and after each fill. Feed down means no mark and `data_stale` blocks buys (intended fail-closed). An idle system has no timer.

**Graduation** per mint: OPEN, COMPLETE (CompleteEvent, TradeEvent with real_token = 0, or complete flag), MIGRATING, POOLED (migration event carries the pool; vaults read by `getMultipleAccounts`; price = quote vault over base vault [U fees]). COMPLETE: snapshot `complete=True`, so the adapter refuses entries. COMPLETE and MIGRATING: `last_open_reserves` is None, so the exit book holds the position (no sell on a completed curve) while marks continue at last open reserves tagged `complete_unmigrated` in `prices_json`; after `migration_gap_timeout_s` = 600 the position is marked 0 and a JournalNote `graduation_stuck` is written. POOLED: `last_open_reserves` returns pool reserves, the existing graduated close runs (curve fee model, conservative against the lower pool fee), then the mint is unwatched. No strategy trades PumpSwap in v4. A synthetic migration (PostCompleteBuyEvent) is COMPLETE then POOLED from the event's reserves.

## 2. Curve layout fix and mainnet probe

**Fix** (`tools/onchain/curve_layout.py`, bot-05-rug): keep struct `<8sQQQQQB` but unpack as (disc, vtok, vsol, rtok, rsol, supply, complete); accept `len ≥ 49`; require discriminator 17b7f837...; parse extended fields (creator at 49, mayhem at 81, quote_mint at 83) as optional `CurveState` fields, None for short legacy accounts. `encode_curve_fixture` keeps its keyword signature and 49-byte output (official order, real discriminator) and `CURVE_ACCOUNT_SIZE` keeps its name (now "legacy prefix size"), so tests of four seats need no edit. Completion is `complete` or real_token = 0; the 85 SOL bar stays only as a documented approximation in `curve_progress`. `rpc_curve_price_allowed` becomes an allowlist: fixture, rest, pumpportal always; "rpc" needs `LAYOUT_STATUS == VERIFIED`; "logs" needs `EVENT_DECODE_STATUS == VERIFIED`; "pool" needs `POOL_STATUS == VERIFIED`; unknown names False. Replay is unaffected (FixtureCurveSource snapshots are source "fixture").

**Probe** (new `scripts/probe_pump_accounts.py`, bot-00-chief, tested in tests/desk): read-only `getAccountInfo` of at least 5 live curves (mints from PumpPortal create frames, no key) plus a completed curve if found. Per account it records base64, length, owner (pump program), discriminator, official decode and invariants (vsol ≥ 30e9, vtok ≤ 1,073,000,000,000,000, rtok ≤ 793,100,000,000,000, vsol × vtok ≥ 0.999 of initial k, complete false for live), and cross-checks the newest transaction: `getSignaturesForAddress`, `getTransaction`, decoded TradeEvent post-trade reserves equal the account's when slots match. It captures one transaction per event type as decoded fixtures (first: TradeEvent in tx 62e3T1C7...WS3c [O]). The record is `decoded_pending_review`, never VERIFIED, with a `reviewed_by` a human sets to `human:NAME`. Old tests pin ASSUMED and the old script, so the order is: (1) chief adds the script; (2) risk commits artifacts and makes tests/docs, tests/safety, tests/cli status-agnostic; (3) sniper does the same for tests/execution; (4) chief deletes `scripts/probe_curve_layout.py`; (5) after human review, rug flips the statuses with tests that the fixtures decode and `reviewed_by` is human-set. Without the review statuses stay ASSUMED.

## 3. Recorder (`replay/live_recorder.py`, bot-02-risk)

A bus subscriber with one writer task (`ts_utc` clamped non-decreasing, since `load_dataset` rejects regressions). Files are listed in manifest.json with sha256 (`FixtureManifest` unchanged; its `sources` map carries machine keys):
- `events.jsonl`: ONLY `kind: tick` rows (existing readers treat every row as a tick). Row = `CurveTick` fields above plus name, image_uri, created_ts_utc, unique_buyers (= ub) so `tick_to_candidate` works unchanged; legacy keys S, T, complete, source keep meaning. Compaction: first tick per mint, last tick per mint per `tick_min_interval_s` = 1 s window with aggregates summed, every completion, and every held-mint mark.
- `trades.jsonl` (optional, off by default): every decoded TradeEvent, lossless, for `rebuild-ticks`.
- `lifecycle.jsonl`: create, complete, migrate, evict rows.
- `gaps.jsonl`: `{from_ts_utc, to_ts_utc, source, reason}` for every FeedGap, reconnect, resync overflow, writer fault.
- `llm.jsonl` (optional): subscriber on Design A's `LlmCallCompleted` event writing `{request_hash, outcome, latency_s, response}` via `canonical_request_hash`; in an idle system it stays empty or absent.
- `manifest.sources`: `coverage` (all_launches | watchset | traded_only | fixture), `overflow_dropped`, `gap_seconds`, `recorder_version`, `layout` statuses.

Sealing: writes go to `var/replay/.recording/NAME/`; at `rotate_s` = 3600, on a FeedGap over 120 s, on size cap, SIGTERM or `--duration` expiry the recorder fsyncs, hashes, writes manifest.json atomically (`core/atomic_write.py`), renames to `var/replay/NAME-sNNN` and emits `DatasetSealed`. Startup recovery seals any `.recording` dir after truncating a torn last line. v1 `run_replay` works on gap-free segments and fails DataStale on gapped ones (unchanged).

CLI (cli/**, bot-02-risk): `run --record NAME --duration S` (replaces the exit-5 stub; record-only, no trading, exit 0); `replay trim --dataset D --from TS --to TS [--mints FILE]` (new digests, gaps clipped); `replay rebuild-ticks --dataset D --tick-min-interval S` (deterministic, from trades.jsonl); `replay import --from replay:DIR | ledger:PATH --name N`. Replay import normalizes to v2 files (lifecycle synthesized from first ticks, gaps computed, coverage=fixture for hand-authored sets). Ledger import emits ticks only for traded mints from FillRecorded `curve_before/after_s/t`, MarkToMarket `prices_json` and PositionOpened (source "ledger_import", coverage=traded_only). Imports never fabricate evidence (ub stays absent) or back-fill later knowledge.

## 4. Strategy framework (`src/pumpgrok/strategies/`, bot-02-risk)

```python
class StrategyParams(BaseModel):  # frozen, extra="forbid"; subclasses declare BOUNDS
class Intent(BaseModel):          # frozen
    kind: Literal["enter", "exit"]; strategy_id: str; mint: str
    size_lamports: int | None     # enter; None = runtime sizing
    reason: ExitRuleReason | None # exit; one of the 4 existing reasons
    rule: str; max_slippage_bps: int; ttl_s: int
    score: Decimal; features: Mapping[str, int | str]   # ints and strings only
class Strategy(Protocol):
    id: ClassVar[str]; version: ClassVar[str]
    params_model: ClassVar[type[StrategyParams]]; needs: ClassVar[frozenset[str]]
    def on_start(ctx); def on_new_token(ctx, ev); def on_tick(ctx, tick)
    def on_fill(ctx, fill); def on_deadline(ctx, mint); def on_stop(ctx)  # last four return Sequence[Intent]
```
Hooks are synchronous and pure. `StrategyContext` is a read-only view (`now()`, bounded `tape(mint)`, own `position(mint)`, `slice_equity_lamports`, resolved enrichment) with no clock, sleep, ledger, registry or network, so a strategy cannot trade, wait or call Grok; strategies without `needs` make zero LLM calls. A raising hook is caught and counted; after 5 faults the strategy is disabled (JournalNote for non-legacy).

Ids match `[a-z][a-z0-9_]{2,31}`; legacy is `legacy_screening` (C). `strategy_version_id = sha256(canonical_json({id, version, params_hash, code_sha256}))`; `params_hash` follows the `CandidateParams.content_hash` convention (legacy keeps CandidateParams, one identity per PR 17). Registry: static dict of `StrategySpec`, no dynamic plugins. Settings `[strategies]`: `runtime_enabled=false`, `enabled=["legacy_screening"]`, `weights` (Decimal, sum ≤ 1, required when more than one enabled; violations are ConfigError). Bounds live in `upgrade_bounds.toml` sections `[strategy.ID.PARAM]`; a test asserts declared BOUNDS and TOML sections match exactly.

**Allocator.** `strategies/allocation.py: slice_lamports(desk_equity_lamports: int, weight: Decimal) -> int` (floor; leaf module, no risk imports) (C). Slice, kill, staleness and entry checks run inside `RiskEngine._evaluate`, mapped onto existing R34 rows by Design C; the 19 STEP_IDS and risk_json shape are unchanged. Desk D6 limits (2 percent per trade, 5 percent per token, 5 percent daily floor, 15 percent drawdown) stay on desk equity; slices only tighten.

**Sizing helper.** `size = clamp(floor(slice_equity × risk_per_trade / stop_fraction), MIN_TRADE_LAMPORTS, floor(slice_equity × max_position_fraction))`, then the risk engine caps by desk fractions. Exits reuse stop_loss, take_profit, trailing_stop, max_hold with the true rule in `Intent.rule`: no OrderRequest or contract change.

**Attribution without payload changes** (C). A non-legacy buy allocates its ticket via `allocate_ticket(..., strategy_id=, param_set_hash=)`, appending refs `strategy:ID` and `param_set:HASH` after `refs[0]`. `strategy_of(store, ticket_id)` (`risk/strategy_slice.py`) reads them; unbound tickets are `legacy_screening`. Per-strategy P&L folds OrderPlaced(ticket, decision_id), FillRecorded(decision_id), PositionOpened(ticket), PositionClosed. Hash safety: `legacy_screening` writes no refs, `runtime_enabled=false` in the smoke config and `run_once_replay` never constructs StrategyRuntime, so smoke-10m rows, counts and payload bytes are identical; new rows exist only on paths the smoke fixture cannot reach, and no existing payload gains a field. Checked by `pumpgrok verify --fixture smoke-10m`; if the hash ever must move, CHANGELOG records before and after.

**Exits.** `StrategyRuntime` builds one `ExitRules` per strategy from its ExitsSettings-compatible params, with a new optional `ticket_filter` on `ExitRules`/`LedgerExitBook` (default None, bot-00-chief) so the global book never double-sells strategy positions. Strategy-specific exits (stall, graduation proximity, reversion target) return as exit Intents; time exits use per-position Clock deadline timers (Design A pattern), not polling.

**Backtest sub-ledgers.** Each strategy backtest runs on its own scratch sqlite ledger (the `evaluate_window` pattern) with budget = slice; isolated slices sum to the desk view.

## 5. Baseline strategies

Common memecoin filters (`strategies/memefilters.py`, integer math): curve open and real_token above 0; SOL quote only; mayhem excluded by default; ub observed (None fails closed); creator not sold (`cs` = 0); `topb_ppm` ≤ cap; rS ≥ `min_real_sol`; modeled buy impact `x / S` (`curve_math.impact_buy`) ≤ `max_entry_impact_bps`; creator block from `engine/reputation.py` (read only); the 10× liquidity floor stays in the risk engine. Price P = S / T (Decimal); progress = rS / 85 SOL (approximation, `complete` authoritative). Features come from `MintTape`, a bounded ring of ticks with aggregates.

| Strategy | Entry | Exits | Sizing |
|---|---|---|---|
| `legacy_screening` | Wraps `tick_to_candidate` / `decide_token` unchanged; judges every tick as today; LLM stages only after a filter pass via Design A's gate. Param `filter_reserve_basis`: `tick_S` for pre-v4 datasets, `real_S` when ticks carry rS (finding 4) | Existing ExitRules with its ExitsSettings (stop 30, take 120, trail 35, hold 3600) | `buy_lamports`, default REPLAY_BUY_LAMPORTS (0.01 SOL) |
| `momentum_breakout` | All of: age and progress inside window (30 to 3600 s; 0.05 to 0.70); P ≥ highest P over `lookback_s` (excluding the last tick) × (1 + breakout_pct); buy volume over `vol_window_s` ≥ `vol_mult` × baseline window volume; buy share ≥ `min_buy_share`; new unique buyers in window ≥ `min_window_buyers`; not extended: P ≤ lookback low × (1 + max_run_pct); memefilters | stop `stop_loss_pct`; trail `trail_pct` once up `trail_arm_pct`; `take_profit_pct`; stall: no new high for `stall_s` and buy share under `fade_buy_share` (reason trailing_stop, rule `momentum_fade`); progress ≥ `exit_progress` (reason take_profit, rule `graduation_proximity`); `max_hold_s` | sizing helper, `risk_per_trade` 0.01 |
| `new_launch_sniper` | On NewTokenSeen then ticks: age ≤ `max_age_s`; dev initial buy within `[dev_buy_min, dev_buy_max]`; name, symbol, uri present; symbol not among the last `dup_window` creates (copycat); creator not blocked; inside `confirm_window_s`, ub ≥ `min_early_buyers` and rS growth ≥ `min_early_inflow`; topb_ppm ≤ cap; memefilters | creator sell (cs above 0): immediate exit (reason stop_loss, rule `creator_sell`); stop, take, trail as parameters; `max_hold_s` | sizing helper, `risk_per_trade` 0.005; latency-bound, so the seeded paper latency (median 1.2 s) applies |
| `mean_reversion` | Demand shown: peak P over `lookback_s` ≥ first P × (1 + `run_min_pct`); drawdown from peak within `dd_min_pct` to `dd_max_pct`; reversal: P ≥ local low over `bounce_window_s` × (1 + `bounce_pct`) and sell volume under `sell_exhaust` × prior window; ub ≥ `min_buyers`; age 300 to 7200 s; progress ≤ 0.80; memefilters | target P ≥ low + `target_frac` × (peak − low) (take_profit, rule `revert_target`); stop below local low by `stop_pct` (stop_loss); `max_hold_s` (max_hold) | sizing helper, `risk_per_trade` 0.005 |

Parameters with bounds (min..max; defaults in parentheses), exported to `upgrade_bounds.toml` under `[strategy.ID.PARAM]`:
- momentum_breakout: lookback_s 30..600 (90); breakout_pct 2..50 (8); vol_window_s 10..120 (30); vol_mult 1..10 (2); min_buy_share 0.5..0.95 (0.6); min_window_buyers 1..50 (4); max_run_pct 20..500 (150); stop_loss_pct 5..40 (15); trail_arm_pct 5..100 (20); trail_pct 3..40 (12); take_profit_pct 20..300 (80); stall_s 30..600 (90); fade_buy_share 0.2..0.6 (0.45); exit_progress 0.5..0.99 (0.92); max_hold_s 60..7200 (1800).
- new_launch_sniper: max_age_s 5..120 (45); dev_buy_min 0..5 SOL (0.5); dev_buy_max 0.5..10 SOL (3); confirm_window_s 2..30 (8); min_early_buyers 1..20 (3); min_early_inflow 0.1..10 SOL (0.5); dup_window 0..1000 (200); topb_cap_ppm 100000..900000 (500000); stop_loss_pct 3..40 (12); take_profit_pct 10..200 (40); trail_arm_pct 5..100 (15); trail_pct 3..40 (10); max_hold_s 30..1800 (300).
- mean_reversion: lookback_s 120..3600 (600); run_min_pct 20..500 (50); dd_min_pct 10..50 (25); dd_max_pct 20..70 (45); bounce_window_s 5..120 (20); bounce_pct 1..15 (3); sell_exhaust 0.1..1.0 (0.7); min_buyers 5..500 (30); target_frac 0.2..1.0 (0.5); stop_pct 5..30 (12); max_hold_s 60..7200 (900).
- Common (per-strategy defaults): risk_per_trade 0.001..0.02; max_position_fraction 0.01..0.2; min_real_sol 0.5..20; max_entry_impact_bps 10..500; max_open_positions 1..3; min_age_s, max_age_s 0..86400; min_progress, max_progress 0..1 (momentum 0.05 and 0.70, reversion 0 and 0.80); post_gap_cooldown_s 0..600.
- legacy_screening: existing 9 filter and 5 exits sections only; `filter_reserve_basis` is a non-tunable enum.

Test plan. Unit: per strategy, hand-built `MintTape` cases with a pass and a boundary case per rule (decision flips exactly at the bound), each memefilter veto, bounds rejection (never clamp). Fixture datasets `strat-breakout`, `strat-launch`, `strat-reversion`, `strat-gap` (hand-authored, coverage=fixture) with asserted fills. Legacy parity: `legacy_screening` through the runtime on smoke matches `run_once_replay` fills and net lamports. Look-ahead canary: extreme values after time T must not change any decision at or before T. Determinism: two runs byte-identical. `FaultInjector` (STALE, TIMEOUT, MALFORMED, UNWRITABLE) on tick streams and the recorder sink.

## 6. Backtest v2 (`src/pumpgrok/backtest/`, bot-02-risk)

Valuation uses `backtest/equity.py` (PR 17/19, one valuation function; B15 depends on their merge). Series: time-stamped equity at each FillRecorded and MarkToMarket; D = window days; ratios are Decimal; undefined is None (never 0 or infinity); no expected-return language (BT-05).
- total_return R = (E1 − E0) / E0. annualized_return = (1 + R)^(365 / D) − 1 (−1 if 1 + R ≤ 0), `annualization_valid=false` when D under 7.
- Round trip = fills grouped by (mint, opening PositionOpened seq); pnl_rt = sum of cash_delta (fees included); hold_s from PositionClosed.
- profit_factor = sum of winning pnl_rt / |sum of losing pnl_rt|; None with no loser, 0 with no winner. win_rate and expectancy (mean pnl_rt / mean cost_basis) per round trip.
- sortino = mean(r) / sqrt(mean(min(r, 0)^2)) × sqrt(365 n / D) over the same per-step returns r as the existing Sharpe; None if n under 2, D = 0 or downside deviation 0.
- avg_hold_s and median_hold_s over closed round trips.
- time_weighted_exposure = ∫ open cost basis dt / ∫ equity dt (step-constant); `time_in_market` = window share with an open position.
- max_drawdown over the full series including marks (v1 used post-fill points only).
- per-strategy breakdown: each metric per strategy sub-ledger plus `pnl_share`.
`MetricsReportV2` is new; v1 `MetricsReport` and BT-05 tests are untouched.

**Controls.** Look-ahead: events replay in `(ts, line)` order on the FixtureClock; the context exposes only history at or before `now`; a fill prices at the latest tick known at decision + seeded latency (adapter CONFIRMING re-read); `ts_utc` is knowledge time (resynced events keep receipt time, `bt` separately); the importer never back-fills. Survivorship: every admitted token is recorded from creation; `evidence_grade` = promotion only if coverage is all_launches or watchset, gap and overflow shares ≤ 5 percent each, span at least 7 days and 200 tokens (`backtest.grade.*`); traded_only, fixture and hand-authored data grade research or synthetic and never count as promotion evidence. Holdout, walk-forward and TrialLedger limits (20, 50) are reused unchanged.

**Gap handling.** `gaps.jsonl` and any tick gap over 120 s split a dataset into segments replayed independently. A position open at segment end is closed at its last price with `gap_haircut_bps` = 500 (`flatten_at_last`) or its round trip is excluded and flagged (`exclude_trade`); no entries for `post_gap_cooldown_s` after a gap; reports state gap seconds and coverage.

**Strategy-aware replay through the same pipeline.** `DatasetEventSource` turns events, lifecycle and gap rows into the same typed events as live, on a FixtureClock, into the same `StrategyRuntime`, `RiskEngine`, `PaperAdapter` and a scratch ledger; only source, clock and price source (`DatasetCurveSource`, same three methods as `FixtureCurveSource`) differ from live-paper. v1 datasets get NewTokenSeen synthesized from first ticks. `run_replay` and `run_once_replay` are untouched.

**Autonomous runs.** `BacktestScheduler` reacts to `DatasetSealed`, `StrategyVersionRegistered`, `ParamsProposed`; no timers. Run key = sha256(strategy_version_id, dataset_digest, params_hash, seed); a seen key is skipped, so repeated events do no work. One run at a time, only when `read_autonomy(store)` is autonomous-paper, trials within BT-04 limits, no LLM client constructible. Results persist deterministically under `var/backtest/RUNID/` (result.json, report.md, trials.jsonl, manifest.json) plus append-only `index.jsonl`; `BacktestCompleted` carries evidence_grade and content hash to Design C's promotion gate (PR 18 `is_writer` plus content-verify pattern); non-legacy runs add a JournalNote `backtest-result`.

## 7. Live-data paper composition root (`supervisor/live_paper.py`, bot-00-chief)

Wiring: WallClock, `ReadOnlyRpc` over `RpcClient`, PortalSource, LogsSource, MintBook, LivePriceSource, StrategyRuntime, per-strategy ExitRules, `PaperAdapter(price source=LivePriceSource)`, `RiskEngine`, paper ledger, optional Recorder. It refuses to build unless the effective mode is paper; `LiveGate` stays refused (exit 3 untouched).

**Provably cannot send.** (1) Only `PaperAdapter` is bound to `exec.place`; it has no transport. (2) `ReadOnlyRpc` allowlist: getAccountInfo, getMultipleAccounts, getSignaturesForAddress, getTransaction, getSlot, getHealth, getTokenSupply, getRecentPrioritizationFees, logsSubscribe, logsUnsubscribe; PumpPortal allowlist: subscribeNewToken, subscribeMigration, unsubscribeNewToken; anything else raises `ReadOnlyViolation` (`core/errors.py`). (3) An AST test fails if any desk module imports a signing or wallet library (solders, solana, nacl, ed25519 private-key APIs) or contains sendTransaction, sendRawTransaction, simulateTransaction, signTransaction, requestAirdrop, subscribeTokenTrade or subscribeAccountTrade outside the allowlist file (Design C's segregated signer lives outside the desk package and is never imported). (4) A fake-transport test runs a full session and asserts every JSON-RPC method and websocket frame is allowlisted. (5) The root refuses to start when any wallet-key or live-arming environment variable is set.

## 8. Requirements (continue repo numbering; checkable)

Every command is `uv run pytest PATH -q` unless shown; every PR also passes `python3 ci/gates/check_ownership.py --validate-manifest`, `uv run ruff check`, `uv run pytest -q`.
- MKT-01 Official layout (49-byte and 166-byte accounts, bad discriminator rejected): tests/tools/onchain/test_curve_layout.py.
- MKT-02 Decoder round-trips all five event types, ignores trailing bytes, EventDecodeError on truncation: tests/tools/onchain/test_pump_events.py.
- MKT-03 Probe fixtures decode, TradeEvent reserves equal account reserves, `reviewed_by` starts `human:`, VERIFIED only then: tests/tools/onchain/test_probe_record.py.
- MKT-04 Price gate allowlist (unknown and unverified sources refused, replay sources allowed): tests/tools/onchain/test_price_gate.py.
- MKT-05 Watch set never exceeds cap, pins held mints, counts overflow: tests/datafeed/test_watchset.py.
- MKT-06 FaultInjector TIMEOUT reconnect: no duplicate signature, gap events, limiter honoured: tests/datafeed/test_feed.py.
- MKT-07 LivePriceSource None when disconnected; complete refuses entry; gap holds position; timeout marks zero: tests/datafeed/test_price_source.py tests/datafeed/test_graduation.py.
- MKT-08 Every held mint marked within 60 s on a fake Clock, no timer when flat: tests/datafeed/test_marks.py.
- MKT-09 No-send proof (allowlist, AST scan, frame capture, env refusal): tests/datafeed/test_readonly.py tests/desk/test_live_paper_root.py.
- REC-01 Sealed dataset passes `load_dataset`, ticks only, ts non-decreasing; REC-02 gaps written, torn line recovered: tests/replay/test_live_recorder.py.
- REC-03 `run --record`, `replay trim|rebuild-ticks|import` work and rerun byte-identically: tests/cli/test_record.py.
- STR-01 Version id tracks code and params; bounds TOML parity: tests/strategies/test_base.py tests/strategies/test_registry.py.
- STR-02 Hash safety: `uv run pumpgrok verify --fixture smoke-10m`; tests/replay/test_runner_determinism.py unchanged.
- STR-03 Legacy writes no refs; per-strategy fold equals total: tests/strategies/test_attribution.py.
- STR-04 Per-rule boundaries, fixture-dataset fills, look-ahead canary: tests/strategies.
- STR-05 No hook reaches an LLM client; idle runtime makes zero calls: tests/strategies/test_no_llm.py.
- BT-08 Metrics v2 formulas, None for undefined: tests/backtest/test_metrics_v2.py. BT-09 Round trips and per-strategy breakdown: tests/backtest/test_roundtrip.py.
- BT-10 Look-ahead canary and grading: tests/backtest/test_lookahead.py tests/backtest/test_grading.py. BT-11 Gap segmentation and haircut: tests/backtest/test_gaps.py.
- BT-12 Strategy-aware replay of legacy_screening on smoke matches v1 fills and net lamports: tests/backtest/test_strategy_replay.py.
- BT-13 Autonomous runs idempotent, deterministic, autonomy-gated: tests/backtest/test_scheduler.py.


## 9. Units

| id | title | seat | files | depends_on | acceptance | parallelism |
|---|---|---|---|---|---|---|
| B01 | Pump event decoder | bot-05-rug | tools/onchain/pump_events.py, tests/tools/onchain/test_pump_events.py | none | MKT-02 | parallel |
| B02 | New probe script | bot-00-chief | scripts/probe_pump_accounts.py, tests/desk/test_probe_pump_accounts.py | none | its test (fake RPC: `decoded_pending_review`, never VERIFIED) | parallel |
| B03 | Layout fix and price gate (statuses stay ASSUMED) | bot-05-rug | tools/onchain/curve_layout.py, tests/tools/onchain/test_curve_layout.py, test_price_gate.py, test_onchain_reads.py | none | MKT-01, MKT-04; tests/tools tests/execution tests/safety green | parallel |
| B04 | Probe artifacts, docs; tests/docs, tests/safety, tests/cli made status-agnostic | bot-02-risk | tests/fixtures/rpc/**, docs/CURVE_LAYOUT_PROBE.md, tests/docs, tests/safety, tests/cli | B02 | those suites green; `reviewed_by` set by a human | after B02 |
| B04s | tests/execution status-agnostic | bot-04-sniper | tests/execution/test_graduation_blind.py, test_curve_source_gate.py | B03 | tests/execution green under both statuses | parallel with B04 |
| B04c | Delete old probe script | bot-00-chief | scripts/probe_curve_layout.py | B04 | ownership gate, no references | serial |
| B05 | Flip statuses to VERIFIED | bot-05-rug | tools/onchain/curve_layout.py, tests/tools/onchain/test_probe_record.py | B03, B04, B04s, human review | MKT-03 | serial |
| B06 | datafeed core: events, MintBook, WatchSet, ReadOnlyRpc, ReadOnlyViolation | bot-02-risk | datafeed/{events,mintbook,watchset,readonly}.py, core/errors.py, tests/datafeed | none | MKT-05, readonly test | parallel |
| B07 | Portal and logs sources, resync, REST fallback, conftest connect patches | bot-02-risk | datafeed/{portal,logs,resync,fallback}.py, tests/datafeed/test_feed.py, tests/conftest.py | B01, B06 | MKT-06 | parallel |
| B08 | LivePriceSource, graduation, marks | bot-02-risk | datafeed/{price,graduation,marks}.py, tests/datafeed | B06 | MKT-07, MKT-08 | parallel |
| B09 | Recorder, importer, trim, rebuild-ticks library | bot-02-risk | replay/{live_recorder,import_data,trim}.py, tests/replay | B06 | REC-01, REC-02 | parallel |
| B10 | Strategy core: protocol, registry, runtime, allocation, tape, attribution, StrategiesSettings | bot-02-risk | strategies/{base,registry,runtime,allocation,tape,attribution}.py, config/settings.py, tests/strategies | B06, Design C ticket refs | STR-01, STR-02, STR-03, STR-05 | parallel |
| B11 | memefilters and legacy_screening wrapper | bot-02-risk | strategies/{memefilters,legacy}.py, tests/strategies | B10 | STR-02; legacy half of BT-12 | parallel |
| B12 | momentum_breakout | bot-02-risk | strategies/momentum.py, tests/strategies, tests/fixtures/replay/strat-breakout, bounds section, registry line | B10, B11 | STR-04 | parallel; serialize merges on registry.py and bounds toml |
| B13 | new_launch_sniper | bot-02-risk | strategies/sniper.py, tests/strategies, tests/fixtures/replay/strat-launch, bounds section | B10, B11 | STR-04 | parallel; same merge rule |
| B14 | mean_reversion | bot-02-risk | strategies/reversion.py, tests/strategies, tests/fixtures/replay/strat-reversion, bounds section | B10, B11 | STR-04 | parallel; same merge rule |
| B15 | Metrics v2 and round trips | bot-02-risk | backtest/{metrics_v2,roundtrip}.py, tests/backtest | PR 17 and 19 merged | BT-08, BT-09 | parallel |
| B16 | Strategy-aware replay, gaps, grading, scheduler, result store | bot-02-risk | backtest/{event_source,strategy_run,gaps,grading,scheduler,store}.py, tests/backtest, tests/fixtures/replay/strat-gap | B09, B10, B15 | BT-10 to BT-13 | serial after B15 |
| B17 | ExitRules ticket filter, CurveReader protocol, live-paper composition root | bot-00-chief | supervisor/{exit_rules,live_paper}.py, tests/desk/test_live_paper_root.py, tests/desk/test_exit_rules_filter.py | B07, B08, B10 | MKT-09; filter test | serial |
| B18 | CLI: run --record, live serve, replay verbs, backtest --strategy | bot-02-risk | cli/{parsing,verbs_state,backtest}.py, tests/cli | B09, B16, B17 | REC-03; smoke verify unchanged | serial |
| B19 | CHANGELOG and per-strategy report section | bot-09-journal | CHANGELOG.md, reporting/ | B18 | smoke hash recorded unchanged | last |
