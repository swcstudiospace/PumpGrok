# TOOL_CATALOG - Every tool the pumpgrok desk exposes

Tracker: SPE-17999 https://linear.app/swcstudio/issue/SPE-17999/n3-target-bot-roster-skill-manifests-tool-catalog-core-interfaces | Notion https://app.notion.com/p/3ffbc1a0c7ae8190b46ced6823fa3c90?pvs=204

Design document only. Companion to `docs/ROSTER.md` (who may call what) and
`docs/design/interfaces.md` (the `ToolSpec` model every entry below instantiates).

## 0. Conventions

| Attribute | Meaning |
|---|---|
| name | `<namespace>.<verb>`; gateway/roster spelling replaces `.` with `_` because G-7 validates `^[a-z][a-z0-9_]{2,60}$` (`programming-desk/ci/gates/check_desk_integrity.py:46`) |
| side_effect | `read` (never mutates a system of record, fails open with empty result + reason), `paper-write` (mutates the paper ledger / journal / desk state, fails closed), `live-write` (would submit a real transaction; present in the enum, absent from every roster, never resolvable: D3/D4) |
| timeout_s | wall-clock limit per call; REVIEW values derived from today's `timeout=12` (`tools/jupiter_quote.py:33`) and `timeout=15` (`tools/authority_check.py` `rpc_call`) and vendor `request_timeout: 10` (`vendor/grokbot-pumpfun/src/models.py:311`) |
| retry | tenacity policy (D5): `none`, or `jitter(n, base_s, max_s)` = exponential backoff with full jitter, n attempts, retry only on timeout / 5xx / 429 (vendor precedent `src/agents/base.py:131-182` retries 5xx/429/timeouts, never other 4xx) |
| rate_limit_key | token-bucket key shared by every tool hitting the same upstream (vendor `RateLimiter`, `src/ops.py:90`) |
| idempotency_key | writes only; derivation in `docs/design/interfaces.md` section 10; a repeated call with the same key returns the first result and performs nothing |
| backend | data source and endpoint, with the file:line in current code that proves the desk already uses it (D8: Solana mainnet; pump.fun frontend REST + PumpPortal WS; Jupiter lite-api quote; Solana JSON-RPC with failover list; x.ai Grok) |
| callers | seats whose roster carries the tool (`docs/ROSTER.md` section 6) |
| source | the existing function to port, or `new` |

Common envelope. Every output includes `meta: {source: str, fetched_at: datetime(UTC),
freshness_s: float, correlation_id: str, stale: bool}`; every input accepts an optional
`correlation_id` (propagated by the registry if omitted; section 10 of interfaces.md). The
schemas below list only tool-specific fields. `required` marks required inputs.

Types: `Mint` = base58 string 32..44 chars; `Pubkey` = same; `Sol` = decimal string or
float in SOL; `Bps` = integer basis points 0..10000; `TicketId` = `^SOL-\d{8}-\d{3}$`
(`tools/ticket_helper.py:28`).

Data-source fallback (spec `MARKET_DATA_TOOLS`, xml line 94): every `read` tool returns
the last cached value with `meta.stale = true` when the upstream fails and a cache entry
younger than `cache_max_age_s` (config, REVIEW 300) exists; otherwise an empty result
with `reason`.

## 1. market.* (read; Scout owns `src/pumpgrok/tools/market/`)

### market.price

| Attribute | Value |
|---|---|
| description | Spot price of a token in SOL from the pump.fun bonding curve reserves, with Jupiter quote as cross-check when the token has graduated |
| input | `mint: Mint` (required); `quote_mint: Mint` (default WSOL); `probe_amount_lamports: int` (default 1_000_000) |
| output | `price_sol: float`; `source: enum[curve, jupiter]`; `curve_progress: float 0..1`; `market_cap_sol: float`; `context_slot: int or null` |
| side_effect | read |
| timeout_s | 10 |
| retry | jitter(3, 0.5, 4) |
| rate_limit_key | `pumpfun_rest` or `jupiter_lite` |
| backend | GET `https://frontend-api.pump.fun/coins/{mint}` (`vendor/grokbot-pumpfun/src/models.py:309`, `src/executor.py:65-77` `price`, `src/executor.py:85` `price_from_reserves`); fallback GET `https://lite-api.jup.ag/swap/v1/quote` (`tools/jupiter_quote.py:22`) |
| callers | scout, sniper, exit, signal |
| source | port `vendor/grokbot-pumpfun/src/executor.py:85-96` `price_from_reserves`; `tools/jupiter_quote.py:25` `get_quote` |

### market.ohlcv

| Attribute | Value |
|---|---|
| description | Candles built from the trade stream (pump.fun has no OHLCV endpoint; candles are aggregated locally from `market.trades`) |
| input | `mint: Mint` (required); `interval_s: int enum[15, 60, 300]` (default 60); `limit: int 1..500` (default 100) |
| output | `candles: list[{ts: int, open: float, high: float, low: float, close: float, volume_sol: float, trades: int}]`; `partial_last: bool` |
| side_effect | read |
| timeout_s | 10 |
| retry | jitter(3, 0.5, 4) |
| rate_limit_key | `pumpfun_rest` |
| backend | aggregation over GET `https://frontend-api.pump.fun/trades/all/{mint}?limit=200` (`vendor/grokbot-pumpfun/src/analyzer.py:86`) |
| callers | signal |
| source | new (`src/pumpgrok/tools/market/ohlcv.py`); trade parsing from `analyzer.py:128` `parse_trade` |

### market.liquidity

| Attribute | Value |
|---|---|
| description | Pool depth: virtual SOL and token reserves, curve progress toward completion (85 SOL, `vendor/grokbot-pumpfun/src/monitor.py:30`), and price impact for a given order size |
| input | `mint: Mint` (required); `order_size_sol: float >= 0` (default 0) |
| output | `virtual_sol_reserves: float`; `virtual_token_reserves: float`; `liquidity_sol: float`; `curve_progress: float`; `price_impact_pct: float`; `order_to_liquidity_ratio: float`; `graduated: bool` |
| side_effect | read |
| timeout_s | 10 |
| retry | jitter(3, 0.5, 4) |
| rate_limit_key | `pumpfun_rest` |
| backend | GET `https://frontend-api.pump.fun/coins/{mint}` (`analyzer.py:84`) |
| callers | scout, rug, signal |
| source | new; reserve math from `executor.py:85-96` |

### market.trades

| Attribute | Value |
|---|---|
| description | Recent trades for a mint with buyer/seller, size, timestamp; live tail optionally from PumpPortal `subscribeTokenTrade` |
| input | `mint: Mint` (required); `limit: int 1..200` (default 200); `since_ts: int or null` |
| output | `trades: list[{ts: int, side: enum[buy, sell], wallet: Pubkey, sol_amount: float, token_amount: float, signature: str or null}]`; `buy_sell_ratio: float`; `unique_wallets: int` |
| side_effect | read |
| timeout_s | 10 |
| retry | jitter(3, 0.5, 4) |
| rate_limit_key | `pumpfun_rest` |
| backend | GET `https://frontend-api.pump.fun/trades/all/{mint}` (`analyzer.py:86`, `TRADE_LIMIT=200`); WS `wss://pumpportal.fun/api/data` method `subscribeTokenTrade` (`models.py:310`, `monitor.py:256`) |
| callers | scout, whale, shill, signal |
| source | port `analyzer.py:128` `parse_trade`, `analyzer.py:81` `Analyzer.fetch` |

### market.holders_snapshot

| Attribute | Value |
|---|---|
| description | Holder count and share distribution snapshot from the pump.fun holders endpoint (off-chain view, cheap); on-chain truth is `onchain.top_holders` |
| input | `mint: Mint` (required); `limit: int 1..50` (default 50) |
| output | `holder_count: int`; `holders: list[{wallet: Pubkey, share: float}]`; `top5_share: float`; `creator_share: float` |
| side_effect | read |
| timeout_s | 10 |
| retry | jitter(3, 0.5, 4) |
| rate_limit_key | `pumpfun_rest` |
| backend | GET `https://frontend-api.pump.fun/coins/{mint}/holders?limit=50` (`analyzer.py:85`, `HOLDER_LIMIT=50`) |
| callers | scout, whale, signal |
| source | port `analyzer.py:114` `parse_holder`, `analyzer.py:168` `compute_metrics` (top5/creator share) |

## 2. onchain.* (read; Rug owns `src/pumpgrok/tools/onchain/`, Whale owns holders/transfers)

All `onchain.*` tools go through one RPC client (`src/pumpgrok/tools/onchain/rpc.py`)
that replaces the three copy-pasted `rpc_call` functions (`tools/authority_check.py:25`,
`tools/holder_check.py:26`, `tools/priority_fee.py:27`), adds a failover list
(`PUMPGROK_RPC_URLS`, default `["https://api.mainnet-beta.solana.com"]`,
`tools/authority_check.py:22`), commitment `confirmed`, request id correlation, and
tenacity retries. Failover rotates to the next URL on timeout, 5xx, 429, or
`-32005` node-behind errors.

### onchain.token_metadata

| Attribute | Value |
|---|---|
| description | Mint account fields plus off-chain metadata (name, symbol, uri, socials) treated as untrusted text (constitution clause 9) |
| input | `mint: Mint` (required) |
| output | `decimals: int`; `supply: str`; `is_initialized: bool`; `program: enum[spl-token, token-2022]`; `extensions: list[str]`; `name: str or null`; `symbol: str or null`; `uri: str or null`; `twitter: str or null`; `telegram: str or null`; `website: str or null`; `creator: Pubkey or null` |
| side_effect | read |
| timeout_s | 15 |
| retry | jitter(3, 0.5, 5) |
| rate_limit_key | `solana_rpc` |
| backend | JSON-RPC `getAccountInfo [mint, {encoding: jsonParsed}]` (`tools/authority_check.py:42-45`); socials from GET `/coins/{mint}` (`analyzer.py:146` `enrich_token`) |
| callers | scout, rug, shill |
| source | port `tools/authority_check.py:40` `check_mint` (fields `decimals, supply, isInitialized, extensions`) |

### onchain.authorities

| Attribute | Value |
|---|---|
| description | Mint and freeze authority status (checklist items 1-2, `agents/risk.md:40-41`) |
| input | `mint: Mint` (required) |
| output | `mint_authority: Pubkey or null`; `freeze_authority: Pubkey or null`; `has_mint_authority: bool`; `has_freeze_authority: bool`; `slot: int` |
| side_effect | read |
| timeout_s | 15 |
| retry | jitter(3, 0.5, 5) |
| rate_limit_key | `solana_rpc` |
| backend | JSON-RPC `getAccountInfo` jsonParsed (`tools/authority_check.py:42-45`) |
| callers | scout, risk, rug |
| source | port `tools/authority_check.py:40` `check_mint` (`hasMintAuthority`, `hasFreezeAuthority`) |

### onchain.lp_status

| Attribute | Value |
|---|---|
| description | Liquidity status: for bonding-curve tokens the curve account and completion flag; for graduated tokens the Raydium LP mint, LP supply held by burn address or known lockers (checklist item 3, `agents/risk.md:42`) |
| input | `mint: Mint` (required) |
| output | `stage: enum[bonding_curve, graduated, unknown]`; `curve_complete: bool or null`; `lp_mint: Pubkey or null`; `lp_burned_pct: float or null`; `lp_locked_pct: float or null`; `locker: str or null`; `lock_expires_at: datetime or null`; `checked: list[str]` (which sub-checks ran) |
| side_effect | read |
| timeout_s | 20 |
| retry | jitter(3, 0.5, 5) |
| rate_limit_key | `solana_rpc` |
| backend | JSON-RPC `getAccountInfo` on the bonding-curve PDA; `getTokenLargestAccounts` on `lp_mint`; GET `/coins/{mint}` field `complete` ([INFERENCE] field name from vendor `enrich_token`, `analyzer.py:146`) |
| callers | risk, rug |
| source | new (no existing tool covers LP; `scout-pumpgrok-pack.md:125`) |

### onchain.top_holders

| Attribute | Value |
|---|---|
| description | On-chain largest token accounts with LP/curve accounts excluded, concentration percentages against total supply (fixes today's "of sampled top-N only; LP not excluded" caveat, `scout-pumpgrok-code.md:24`) |
| input | `mint: Mint` (required); `limit: int 1..20` (default 20); `exclude: list[Pubkey]` (default: curve + LP accounts from `onchain.lp_status`) |
| output | `holders: list[{address: Pubkey, owner: Pubkey or null, ui_amount: float, pct_of_supply: float}]`; `top1_pct: float`; `top5_pct: float`; `top10_pct: float`; `supply: float`; `excluded: list[Pubkey]` |
| side_effect | read |
| timeout_s | 15 |
| retry | jitter(3, 0.5, 5) |
| rate_limit_key | `solana_rpc` |
| backend | JSON-RPC `getTokenLargestAccounts [mint]` (`tools/holder_check.py:43`) + `getTokenSupply` |
| callers | risk, whale, rug |
| source | port `tools/holder_check.py:41` `holder_snapshot` |

### onchain.deployer_history

| Attribute | Value |
|---|---|
| description | Creator wallet history: tokens created, prior rugs recorded in the desk's reputation book, age of wallet, funding source (checklist item 8, `agents/risk.md:47`) |
| input | `creator: Pubkey` (required); `lookback_days: int 1..90` (default 30) |
| output | `tokens_seen: int`; `tokens_bought: int`; `rugs: int`; `worst_pnl_pct: float or null`; `is_known_bad: bool`; `first_seen_at: datetime or null`; `recent_signatures: list[str]` |
| side_effect | read |
| timeout_s | 20 |
| retry | jitter(3, 0.5, 5) |
| rate_limit_key | `solana_rpc` |
| backend | local reputation book (`vendor/grokbot-pumpfun/src/reputation.py:48` `ReputationBook`, `:129` `verdict`) + JSON-RPC `getSignaturesForAddress` |
| callers | whale, rug |
| source | port `src/reputation.py` (`CreatorRecord` `:31`, `ReputationBook` `:48`) into `src/pumpgrok/tools/onchain/deployer.py`; RPC part new |

### onchain.large_transfers

| Attribute | Value |
|---|---|
| description | Recent transfers above a threshold by top holders or the creator; feeds WHALE clusters and RUG "large insider sells" trigger (`agents/rug.md:41`) |
| input | `mint: Mint` (required); `wallets: list[Pubkey]` (default: top 10 holders); `min_pct_of_supply: float` (default 0.5); `since_ts: int or null` |
| output | `transfers: list[{ts: int, signature: str, from: Pubkey, to: Pubkey, ui_amount: float, pct_of_supply: float, kind: enum[sell, transfer, lp_remove, unknown]}]` |
| side_effect | read |
| timeout_s | 20 |
| retry | jitter(3, 0.5, 5) |
| rate_limit_key | `solana_rpc` |
| backend | JSON-RPC `getSignaturesForAddress` + `getTransaction` (jsonParsed) per wallet, bounded by `limit` |
| callers | whale, rug |
| source | new |

### onchain.priority_fee

| Attribute | Value |
|---|---|
| description | Recommended compute-unit price from recent prioritization fees; used by the PaperAdapter fee model and reported in fills (`agents/sniper.md:49,53`) |
| input | `percentile: int 0..100` (default 50); `multiplier: float 1.0..3.0` (default 1.2); `max_micro_lamports: int` (default 50000; implements the `--max-micro` cap documented but missing today, `scout-pumpgrok-code.md:25`); `accounts: list[Pubkey]` (default []) |
| output | `samples: int`; `median: int`; `percentile_fee: int`; `recommended_micro_lamports: int`; `capped: bool` |
| side_effect | read |
| timeout_s | 15 |
| retry | jitter(3, 0.5, 5) |
| rate_limit_key | `solana_rpc` |
| backend | JSON-RPC `getRecentPrioritizationFees [accounts]` (`tools/priority_fee.py:45`) |
| callers | sniper, exit |
| source | port `tools/priority_fee.py:42` `estimate_priority_fee`; drop the mislabeled `recommended_lamports_per_cu` alias |

## 3. safety.* (read; Rug owns `src/pumpgrok/tools/safety/`)

### safety.score_report

| Attribute | Value |
|---|---|
| description | Composable rug/honeypot heuristics producing a scored report with reasons; thresholds configurable; never a bare boolean (spec `SAFETY_TOOLS`, xml line 96). Implements the 10-check list at `agents/risk.md:39-49` plus vendor vetoes (`CREATOR_SHARE_VETO=0.25`, `TOP5_SHARE_VETO=0.80`, `vendor/grokbot-pumpfun/src/analyzer.py:34-35`) |
| input | `mint: Mint` (required); `intended_size_sol: float >= 0` (default 0); `thresholds: object or null` (override of `config.safety.thresholds`; keys below); `checks: list[str] or null` (subset to run; default all) |
| output | `score: int 0..100` (100 = safest); `verdict_recommendation: enum[CLEAR, CONDITIONAL, KILL]` (recommendation only; RISK issues the verdict); `hard_veto: bool`; `checks: list[{id: enum[mint_authority, freeze_authority, lp_status, transfer_tax, honeypot, top10_concentration, bundler_cluster, deployer_history, token2022_extensions, liquidity_depth], status: enum[pass, warn, fail, blind], value: any, threshold: any, weight: float, reason: str}]`; `blind_checks: list[str]`; `evidence: list[{check: str, source: str, slot: int or null, fetched_at: datetime}]`; `thresholds_used: object` |
| side_effect | read |
| timeout_s | 45 (composes up to 8 onchain/market calls) |
| retry | none at this level (inner tools retry) |
| rate_limit_key | `solana_rpc` (inherited) |
| backend | composes `onchain.authorities`, `onchain.lp_status`, `onchain.token_metadata`, `onchain.top_holders`, `onchain.deployer_history`, `market.liquidity`, `market.trades`; honeypot heuristic = sell-side simulation through `exec.simulate` on the PaperAdapter curve math (no transaction) |
| callers | risk, rug |
| source | new orchestration; metrics from `analyzer.py:168` `compute_metrics`, `:219` `_count_snipers`, `:226` `_wallet_diversity`, `:285` `_veto_reason`, `:294` `_risk_score` |

Threshold keys (config `safety.thresholds`, every value REVIEW; defaults from
`agents/risk.md:42-49`): `transfer_tax_hard_fail_pct: 10`, `transfer_tax_warn_pct: 5`,
`top10_concentration_warn_pct: 20`, `top10_concentration_fail_pct: 25`,
`liquidity_multiple_min: 10`, `liquidity_multiple_recommended: 20`,
`lp_lock_min_days: 180`, `creator_share_veto: 0.25`, `top5_share_veto: 0.80`,
`kill_below_score: 40`, `conditional_below_score: 70`. Any `blind` check on a required
id forces `verdict_recommendation = KILL` (constitution clause 10).

## 4. exec.* (Sniper owns `src/pumpgrok/tools/exec/` and `src/pumpgrok/execution/`)

All `exec.*` tools call the configured `ExecutionAdapter`. In every shipped configuration
that is `PaperAdapter`; `LiveJupiterAdapter` and `LivePumpfunAdapter` exist as disabled
stubs whose every method raises `LiveGateError` (D4). The registry refuses to construct a
live adapter unless `LiveGate.check()` returns no unmet preconditions; the startup path
prints every unmet precondition and exits non-zero (D4).

### exec.quote

| Attribute | Value |
|---|---|
| description | Route quote for a swap: expected out amount, price impact, route plan. Paper mode returns a Jupiter lite-api quote when the token is routable, otherwise a curve-derived quote |
| input | `input_mint: Mint` (required); `output_mint: Mint` (required); `amount: int` lamports/base units (required); `slippage_bps: Bps` (default 100) |
| output | `quote_id: str`; `in_amount: int`; `out_amount: int`; `other_amount_threshold: int`; `price_impact_pct: float`; `route_plan: list[{swap_info: object, percent: int}]`; `context_slot: int or null`; `source: enum[jupiter, curve]`; `expires_at: datetime` |
| side_effect | read |
| timeout_s | 12 |
| retry | jitter(3, 0.5, 4) |
| rate_limit_key | `jupiter_lite` |
| backend | GET `https://lite-api.jup.ag/swap/v1/quote?inputMint&outputMint&amount&slippageBps` (`tools/jupiter_quote.py:22,26-33`) |
| callers | sniper, exit |
| source | port `tools/jupiter_quote.py:25` `get_quote`; keep the `raw` upstream body under `meta.raw` |

### exec.simulate

| Attribute | Value |
|---|---|
| description | Simulate a fill against observed liquidity without placing it: price impact vs size, fee model, expected slippage, partial-fill flag, liquidity-floor rejection (PaperAdapter fill model, `docs/design/paper-engine.md`) |
| input | `ticket_id: TicketId` (required); `mint: Mint` (required); `side: enum[buy, sell]` (required); `size_sol: float > 0` (buy) or `token_amount: float > 0` (sell); `slippage_bps: Bps` (default 100); `quote_id: str or null` |
| output | `would_fill: bool`; `fill_kind: enum[full, partial, rejected]`; `expected_price: float`; `expected_out: float`; `price_impact_pct: float`; `fee_sol: float`; `priority_fee_sol: float`; `liquidity_ratio: float`; `rejection_reason: str or null`; `latency_ms_estimate: int` |
| side_effect | read |
| timeout_s | 10 |
| retry | none |
| rate_limit_key | `pumpfun_rest` |
| backend | PaperAdapter.simulate over `market.liquidity` + `onchain.priority_fee` |
| callers | sniper, exit, (safety.score_report internally) |
| source | new; replaces the zero-slippage/zero-fee model in `vendor/grokbot-pumpfun/src/executor.py:103-134` |

### exec.place

| Attribute | Value |
|---|---|
| description | Place exactly one paper order. Fails closed. Requires an `approval_id` (g6) that resolves to an `ApprovalRecord` (human approval phrase for buys, `rules/pumpgrok-team.mdc:28`; pre-authorised exit rule id or human confirmation for sells, `agents/exit.md:41`). The registry wraps this tool with `risk.check_limits` and kill-switch/halt checks before the adapter is reached |
| input | `ticket_id: TicketId` (required); `mint: Mint` (required); `side: enum[buy, sell]` (required); `size_sol: float > 0` or `token_amount: float > 0`; `max_slippage_bps: Bps` (required); `approval_id: str` (required); `quote_id: str or null`; `idempotency_key: str` (required; see section 10 of interfaces.md) |
| output | `order_id: str`; `status: enum[filled, partial, rejected, unknown]`; `signature: str` (`paper:<idempotency_key>`; never a real signature); `filled_sol: float`; `filled_tokens: float`; `avg_price: float`; `realised_slippage_bps: int`; `fee_sol: float`; `priority_fee_sol: float`; `route: str`; `ledger_event_id: int`; `reason: str or null` |
| side_effect | paper-write |
| timeout_s | 20 |
| retry | none (single-send rule, `rules/pumpgrok-team.mdc:30`; timeout -> `status: unknown`, caller reports `UNKNOWN RESULT - reconcile by signature`) |
| rate_limit_key | `exec_place` (1 per ticket per side; a second call with a different idempotency key for the same ticket+side is refused) |
| idempotency_key | required input; adapter stores `(key -> result)` in the ledger; replay returns the stored result |
| backend | PaperAdapter.place -> `portfolio.ledger_write` (events `order.placed`, `fill`) |
| callers | sniper (buy), exit (sell) |
| source | new; position bookkeeping from `vendor/grokbot-pumpfun/src/executor.py:183` `new_position`, `src/risk.py:182` `register_open`, `:188` `register_close` |

### exec.cancel

| Attribute | Value |
|---|---|
| description | Cancel a pending paper order owned by the calling seat (orders are near-instant in paper mode; cancel exists for the simulated-latency window and for parity with the adapter interface) |
| input | `order_id: str` (required); `ticket_id: TicketId` (required); `idempotency_key: str` (required) |
| output | `cancelled: bool`; `status_after: enum[cancelled, already_filled, not_found]` |
| side_effect | paper-write |
| timeout_s | 10 |
| retry | none |
| rate_limit_key | `exec_place` |
| idempotency_key | required input |
| backend | PaperAdapter.cancel -> ledger event `order.cancelled` |
| callers | sniper, exit |
| source | new |

### exec.positions

| Attribute | Value |
|---|---|
| description | Open paper positions with mark-to-market from the latest price |
| input | `mint: Mint or null`; `include_closed_since_ts: int or null` |
| output | `positions: list[{ticket_id: TicketId, mint: Mint, side: enum[long], entry_price: float, peak_price: float, sol_spent: float, token_amount: float, opened_at: datetime, mark_price: float or null, unrealised_pnl_sol: float or null, unrealised_pnl_pct: float or null, hold_seconds: int}]`; `equity_sol: float`; `cash_sol: float` |
| side_effect | read |
| timeout_s | 10 |
| retry | none |
| rate_limit_key | `ledger` |
| backend | ledger snapshot + `market.price` |
| callers | chief, sniper, exit, journal |
| source | port `vendor/grokbot-pumpfun/src/models.py:243` `Position` fields; `src/risk.py:226` `pnl_pct` |

## 5. portfolio.* (Journal owns `src/pumpgrok/tools/portfolio/` and `src/pumpgrok/ledger/`)

### portfolio.ledger_read

| Attribute | Value |
|---|---|
| description | Read append-only ledger events and snapshots (sqlite WAL, D5) with filters |
| input | `since_event_id: int` (default 0); `kinds: list[str] or null`; `ticket_id: TicketId or null`; `limit: int 1..1000` (default 200) |
| output | `events: list[{event_id: int, ts: datetime, kind: str, ticket_id: TicketId or null, correlation_id: str, payload: object}]`; `latest_snapshot: {snapshot_id: int, ts: datetime, equity_sol: float, cash_sol: float, positions: int} or null` |
| side_effect | read |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `ledger` |
| backend | `var/ledger.sqlite` tables `events`, `snapshots` |
| callers | risk, journal |
| source | new; replaces `tools/pipeline_evidence.py:183` `load_records` JSONL reader and vendor `src/log.py:197` `read_log` |

### portfolio.ledger_write

| Attribute | Value |
|---|---|
| description | Append one ledger event. Not in any seat roster: only the PaperAdapter and the supervisor call it in-process (`docs/ROSTER.md` section 6). Listed so the registry can audit it |
| input | `kind: str` (required; enum from `contracts/events/*`); `payload: object` (required); `ticket_id: TicketId or null`; `idempotency_key: str` (required) |
| output | `event_id: int`; `duplicate: bool` |
| side_effect | paper-write |
| timeout_s | 5 |
| retry | none; `sqlite3.OperationalError` -> `LedgerUnavailable`, supervisor refuses new orders (spec `GRACEFUL_DEGRADATION`) |
| rate_limit_key | `ledger` |
| idempotency_key | required input; unique index on `events.idempotency_key` |
| backend | `var/ledger.sqlite` |
| callers | none (adapter/supervisor only) |
| source | new; `paper_sim.py:25` `append_paper_fill` markdown append is retired |

### portfolio.exposure

| Attribute | Value |
|---|---|
| description | Current exposure: per token, total, percentage of paper equity, open position count; what `risk.check_limits` compares against D6 limits |
| input | `mint: Mint or null` |
| output | `equity_sol: float`; `cash_sol: float`; `gross_exposure_sol: float`; `gross_exposure_pct: float`; `open_positions: int`; `per_token: list[{mint: Mint, exposure_sol: float, exposure_pct: float}]` |
| side_effect | read |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `ledger` |
| backend | ledger snapshot + marks |
| callers | chief, risk, journal |
| source | new |

### portfolio.pnl

| Attribute | Value |
|---|---|
| description | Realised and unrealised PnL for a window; daily loss percentage that the 5% constitutional halt reads (`rules/pumpgrok-team.mdc:34`) |
| input | `window: enum[day, week, all]` (default day); `as_of: datetime or null` |
| output | `realised_sol: float`; `unrealised_sol: float`; `fees_sol: float`; `daily_loss_pct: float`; `peak_equity_sol: float`; `drawdown_pct: float`; `trades: int`; `win_rate: float or null` |
| side_effect | read |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `ledger` |
| backend | ledger |
| callers | chief, risk, journal |
| source | port `vendor/grokbot-pumpfun/src/risk.py:122-136` (`daily_loss`, `remaining_loss_budget`, `halted`) semantics; adds unrealised and drawdown |

## 6. risk.* (Risk owns `src/pumpgrok/tools/risk/` and `src/pumpgrok/risk/`)

### risk.check_limits

| Attribute | Value |
|---|---|
| description | Evaluate a proposed order against D6 limits, verdict state, approval record, halt and kill switch. Returns a decision with every rule evaluated; a `KILL` verdict on the ticket is non-overridable (D9) |
| input | `ticket_id: TicketId` (required); `mint: Mint` (required); `side: enum[buy, sell]` (required); `size_sol: float >= 0` (required); `approval_id: str or null`; `bot: str` (seat id, injected by registry) |
| output | `approved: bool`; `reason: str`; `rules: list[{id: enum[verdict_clear, approval_present, approval_matches_ticket, max_position_pct, max_token_pct, daily_loss_halt, drawdown_halt, max_open_positions, liquidity_floor, kill_switch, breaker_state, seat_may_trade], status: enum[pass, fail, skip], value: any, limit: any}]`; `size_cap_sol: float` |
| side_effect | read (pure evaluation; the registry wrapper around `exec.place` calls it) |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `ledger` |
| backend | ledger + config + `var/KILLSWITCH` + breaker state |
| callers | chief, risk; registry wrapper for sniper/exit |
| source | port `vendor/grokbot-pumpfun/src/risk.py:149` `evaluate` and `:143` `position_size` (score-proportional sizing, `MAX_SHARE_OF_REMAINING_BUDGET=0.30` at `:33`, `MIN_TRADE_SOL=0.01` at `:36`), extended with percent-of-equity limits |

### risk.drawdown

| Attribute | Value |
|---|---|
| description | Drawdown from peak equity and loss velocity (loss per hour) for the breaker |
| input | `window_hours: int 1..168` (default 24) |
| output | `peak_equity_sol: float`; `current_equity_sol: float`; `drawdown_pct: float`; `loss_velocity_sol_per_h: float`; `halted: bool` |
| side_effect | read |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `ledger` |
| backend | ledger snapshots |
| callers | risk |
| source | new |

### risk.kill_switch

| Attribute | Value |
|---|---|
| description | Set or clear the global kill switch, optionally requesting flatten of all paper positions (D6). Sources: env `PUMPGROK_KILLSWITCH=1`, file `var/KILLSWITCH`, alert-channel command; checked every supervisor cycle. Clearing requires a human-signed approval record; RISK may set without one |
| input | `action: enum[set, clear, status]` (required); `reason: str` (required for set); `flatten: bool` (default false); `approval_id: str` (required for clear; g6) |
| output | `active: bool`; `since: datetime or null`; `source: enum[env, file, command, none]`; `flatten_requested: bool`; `reason: str or null` |
| side_effect | paper-write |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `killswitch` |
| idempotency_key | derived (`risk.kill_switch`, action, reason, UTC minute) |
| backend | `var/KILLSWITCH` file + ledger event `killswitch.set/clear` + `notify.alert` |
| callers | risk only (`docs/ROSTER.md` section 6); `pumpgrok killswitch set|clear|status` CLI |
| source | new; replaces `tools/desk_state.py:195` `write_halt` (`Halt: true` in desk.md) |

### risk.halt_status

| Attribute | Value |
|---|---|
| description | Combined halt view: daily-loss floor halt, drawdown halt, kill switch, breaker states with cooldown expiry |
| input | none |
| output | `halted: bool`; `reasons: list[enum[daily_loss, drawdown, kill_switch, breaker_data_stale, breaker_loss_velocity, breaker_exec_errors, manual]]`; `breakers: list[{id: str, open: bool, trips: int, cooldown_until: datetime or null}]`; `engagement: enum[research, paper, live]` |
| side_effect | read |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `ledger` |
| backend | risk engine state |
| callers | chief, risk |
| source | port `tools/desk_state.py:213` `status_payload` (`halt`, `engagement`), vendor `src/ops.py:131` `CircuitBreaker`, `src/pipeline.py:334` `_check_transitions` |

## 7. notify.* (Chief owns `src/pumpgrok/tools/notify/`)

### notify.alert

| Attribute | Value |
|---|---|
| description | Human alert through the abstract `Notifier`. Sinks: stdout + file always on; Telegram and webhook adapters config-driven (D6; `hermes/profiles.yaml:16` `telegram_token_profile: chief`). Never posts to social platforms (D7); the only allowed destinations are operator channels |
| input | `severity: enum[info, warning, critical]` (required); `kind: str` (required; enum from `contracts/events/alert.schema.json`: rug_flag, halt, breaker, killswitch, escalation, report, unknown_result); `text: str maxLength 4000` (required); `ticket_id: TicketId or null`; `fields: object`; `idempotency_key: str or null` |
| output | `delivered: list[{sink: str, ok: bool, error: str or null}]`; `suppressed: bool` (rate limit) |
| side_effect | paper-write |
| timeout_s | 10 |
| retry | jitter(3, 1, 8) per network sink; stdout/file never retried |
| rate_limit_key | `notify` (sliding window per minute; vendor `Notifier._allow_now`, `src/alerts.py:40-91`) |
| idempotency_key | derived (`kind`, `ticket_id`, `severity`, UTC minute) when omitted |
| backend | stdout, `var/alerts.log`, Telegram Bot API `sendMessage` (token from env profile), generic webhook POST `{event, text, fields, ts}` (`src/alerts.py:91` `_send`) |
| callers | chief, risk, rug, journal |
| source | port `vendor/grokbot-pumpfun/src/alerts.py:40` `Notifier` behind an ABC |

## 8. journal.* (Journal owns `src/pumpgrok/tools/journal/` and `src/pumpgrok/reporting/`)

### journal.append

| Attribute | Value |
|---|---|
| description | Append a decision/journal entry keyed by ticket (constitution clause 8: "Log every decision with ticket ID. The journal is the only audit evidence."). Stored as a ledger event `journal.entry` and exported to `var/journal/YYYY-MM-DD.jsonl` |
| input | `kind: enum[lead, whale, social, signal, verdict, ticket, approval, fill, alert, review, halt, escalation, note]` (required); `ticket_id: TicketId or null`; `body: object` (required; validated against the matching `contracts/events/*` schema when kind maps to one); `bot: str` (injected) |
| output | `event_id: int`; `journal_path: str` |
| side_effect | paper-write |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `ledger` |
| idempotency_key | derived (`kind`, `ticket_id`, sha256(body)) |
| backend | ledger + JSONL export |
| callers | chief, scout, whale, shill, signal, journal |
| source | replaces `tools/paper_sim.py:25` `append_paper_fill` and vendor `src/log.py:40` `TradeLog` |

### journal.render_report

| Attribute | Value |
|---|---|
| description | Render the daily or weekly report (trades taken, win rate, PnL, max drawdown, rejected signals and why, safety false positives/negatives if later known, bot health; spec `REPORTING`, xml line 108) to markdown under `var/reports/` and deliver via `notify.alert` |
| input | `period: enum[daily, weekly]` (required); `as_of: datetime or null`; `deliver: bool` (default true) |
| output | `report_path: str`; `summary: {trades: int, win_rate: float or null, realised_sol: float, max_drawdown_pct: float, rejected_signals: int, open_positions: int, halts: int, bot_health: object}` |
| side_effect | paper-write |
| timeout_s | 30 |
| retry | none |
| rate_limit_key | `ledger` |
| idempotency_key | derived (`period`, `as_of` day) |
| backend | ledger reads + markdown template |
| callers | journal; `pumpgrok report --daily|--weekly` CLI |
| source | new; study material `vendor/grokbot-pumpfun/scripts/dashboard.py`, `scripts/replay.py` (summaries over JSONL) |

## 9. desk.* core eight (every seat; Chief owns `services/desk-gateway/`)

Analogues of `programming-desk/contracts/tool-rosters/_core.yaml:12-148`. The gateway
serves these on every `/mcp/<seat>` endpoint in addition to the seat file's tools
(`programming-desk/contracts/README.md:42-45`).

| Tool | side_effect | timeout_s | retry | rate_limit_key | description | input (required in bold) | output | backend |
|---|---|---|---|---|---|---|---|---|
| desk.brief | read | 10 | none | `desk` | Start-of-turn brief: seat's open tickets, halt status, last receipts, memory recall (`_core.yaml:13-26`) | `task_id: str`, `refresh: bool` | `tickets: list`, `halt: object`, `recall: list`, `etag: str` | `core.brief` |
| desk.docs_search | read | 10 | none | `desk` | Search `docs/**`, `skills/**`, `contracts/**` at origin/main (`_core.yaml:28-42`) | **query**, `limit: int 1..20` | `chunks: list[{path, line, text}]` | `core.docs_search` |
| desk.memory_retain | paper-write | 5 | none | `desk` | Retain a decision or verified command into the seat memory bank; refused without `receipt_path` or `source` (`_core.yaml:44-61`) | **content**, `receipt_path`, `source`, `task_id`, `tags` | `id: str` | `core.memory_retain` |
| desk.memory_recall | read | 5 | none | `desk` | Recall from own bank and shared desk bank (`_core.yaml:63-76`) | **query**, `limit`, `include_shared` | `items: list` | `core.memory_recall` |
| desk.ownership_resolve | read | 5 | none | `desk` | Resolve repo paths to owning seat under `ownership.yaml`, last match wins, unowned reported (`_core.yaml:78-94`) | **paths: list[str] 1..100** | `resolved: list[{path, owner, contract_surface}]`, `unowned: list[str]` | `core.ownership_resolve` |
| desk.receipt_check | read | 60 | none | `desk` | Run G-2, G-3, G-5, G-6 against a receipt without writing to git (`_core.yaml:96-111`) | **bot** (`^bot-0[0-9]-[a-z-]+$`), `receipt`, `receipt_path`, `strict` | `gates: list[{gate, exit_code, output_tail}]` | `core.receipt_check` |
| desk.event_emit | paper-write | 5 | none | `desk` | Emit a seat-attributed event to the ledger event log; payload redacted and capped at 4 KB (`_core.yaml:113-128`) | **kind** (`^[a-z][a-z0-9_.]{2,60}$`), `task_id`, `payload` | `event_id: int` | `core.event_emit` -> `portfolio.ledger_write` |
| desk.doctor | paper-write | 60 | none | `desk` | `check` verifies prompt SHA, skills, roster, registry grants, config mode == paper; `register` records the Bot's agent id; `install_prompt` returns the assembled prompt; `repair` re-runs install (`_core.yaml:130-148`); `pumpgrok doctor` CLI | **action: enum[check, register, install_prompt, repair]**, `agent_uuid`, `channel_id`, `prompt_sha256`, `installed_skills` | `ok: bool`, `rows: list[{check, status, detail}]` | `core.doctor` |

Idempotency for `desk.memory_retain`, `desk.event_emit`, `desk.doctor`: derived
(`tool`, `bot`, sha256(input)).

## 10. Side-effect summary

| side_effect | Tools | Roster `kind` | Gate tag |
|---|---|---|---|
| read | market.*, onchain.*, safety.score_report, exec.quote, exec.simulate, exec.positions, portfolio.ledger_read, portfolio.exposure, portfolio.pnl, risk.check_limits, risk.drawdown, risk.halt_status, desk.brief, desk.docs_search, desk.memory_recall, desk.ownership_resolve, desk.receipt_check | `read` | - |
| paper-write | exec.place, exec.cancel, portfolio.ledger_write, risk.kill_switch, notify.alert, journal.append, journal.render_report, desk.memory_retain, desk.event_emit, desk.doctor | `write` | `g6` on exec.place, exec.cancel, risk.kill_switch (clear) because each requires `approval_id` in `input.required` (`check_desk_integrity.py:55-58`) |
| live-write | none registered; the enum value exists so the registry can refuse it and audit the attempt (spec `SECURITY_AND_VALIDATION`, xml line 131) | never appears in a roster | - |

The programming-desk `kind` vocabulary is two-valued (`read`/`write`,
`_core.yaml:5-6`). pumpgrok's roster files keep that vocabulary for G-7 compatibility and
add one extra key per tool, `side_effect: read | paper-write`, which the G-7 port
validates (value must be in `{read, paper-write}`; `live-write` in any roster fails the
gate). `check_tool` (`check_desk_integrity.py:103-147`) reads only known keys, so the
extra key is safe for the unmodified gate as well.

## 11. Roster YAML shape (copied from programming-desk) and the sniper example

Source schema: `programming-desk/contracts/tool-rosters/_core.yaml:1-11` (conventions
comment and header keys `version`, `surface`, `tools`) and a seat file,
`programming-desk/contracts/tool-rosters/systems.yaml:1-11` (header keys `version`,
`seat`, `short`, `endpoint`, `scope`, `memory_banks`, `core`, `packs_allowed`,
`consumers`, `tools`). Per-tool fields: `name`, `kind`, `gates`, `description`, `input`
(JSON Schema, `type: object`, `additionalProperties: false`), `backend`
(`programming-desk/contracts/README.md:58-60`).

Effective roster for sniper = core 8 + 7 = 15, the G-7 ceiling
(`check_desk_integrity.py:41-42`).

```yaml
# SNIPER roster: core 8 + 7 = 15. Contract surface (RISK); consumer bot-04-sniper.
# Conventions (contracts/tool-rosters/_core.yaml):
#   kind:        read  - never mutates a system of record; fails open (empty result + reason)
#                write - mutates; fails closed
#   side_effect: read | paper-write   (live-write is never permitted in a roster)
#   gates:       g6 - approval_id is required and echoed into the audit event
#   backend:     the gateway module and function that implements the tool
version: 1.0.0
seat: bot-04-sniper
short: sniper
endpoint: /mcp/sniper
scope: seat:sniper
memory_banks: { own: pg-sniper, shared: [pg-desk] }
core: true
packs_allowed: false
consumers: [bot-04-sniper]
tools:
  - name: exec_quote
    kind: read
    side_effect: read
    gates: []
    description: >-
      Route quote for a swap through the configured ExecutionAdapter (paper). Returns
      expected out amount, price impact and route plan. Never submits anything.
    backend: exec.quote
    input:
      type: object
      additionalProperties: false
      required: [input_mint, output_mint, amount]
      properties:
        input_mint: { type: string, minLength: 32, maxLength: 44 }
        output_mint: { type: string, minLength: 32, maxLength: 44 }
        amount: { type: integer, minimum: 1 }
        slippage_bps: { type: integer, minimum: 0, maximum: 10000, default: 100 }
        correlation_id: { type: string, maxLength: 64 }

  - name: exec_simulate
    kind: read
    side_effect: read
    gates: []
    description: >-
      Simulate a fill against observed liquidity: expected price, impact, fee, partial-fill
      or liquidity-floor rejection. Precondition for exec_place.
    backend: exec.simulate
    input:
      type: object
      additionalProperties: false
      required: [ticket_id, mint, side, size_sol]
      properties:
        ticket_id: { type: string, pattern: "^SOL-[0-9]{8}-[0-9]{3}$" }
        mint: { type: string, minLength: 32, maxLength: 44 }
        side: { type: string, enum: [buy] }
        size_sol: { type: number, exclusiveMinimum: 0 }
        slippage_bps: { type: integer, minimum: 0, maximum: 10000, default: 100 }
        quote_id: { type: string, maxLength: 64 }
        correlation_id: { type: string, maxLength: 64 }

  - name: exec_place
    kind: write
    side_effect: paper-write
    gates: [g6]
    description: >-
      Place exactly one paper BUY for an approved ticket. Fails closed. approval_id must
      resolve to the human approval record for this ticket, mint, size and slippage.
      The gateway runs risk_check_limits, halt and kill-switch checks first. No retry:
      a timeout is reported as UNKNOWN RESULT - reconcile by signature.
    backend: exec.place
    input:
      type: object
      additionalProperties: false
      required: [ticket_id, mint, side, size_sol, max_slippage_bps, approval_id, idempotency_key]
      properties:
        ticket_id: { type: string, pattern: "^SOL-[0-9]{8}-[0-9]{3}$" }
        mint: { type: string, minLength: 32, maxLength: 44 }
        side: { type: string, enum: [buy] }
        size_sol: { type: number, exclusiveMinimum: 0 }
        max_slippage_bps: { type: integer, minimum: 1, maximum: 10000 }
        approval_id: { type: string, pattern: "^apr-[a-f0-9]{16}$" }
        quote_id: { type: string, maxLength: 64 }
        idempotency_key: { type: string, pattern: "^[a-f0-9]{32}$" }
        correlation_id: { type: string, maxLength: 64 }

  - name: exec_cancel
    kind: write
    side_effect: paper-write
    gates: [g6]
    description: Cancel a pending paper order that this seat placed. Fails closed.
    backend: exec.cancel
    input:
      type: object
      additionalProperties: false
      required: [order_id, ticket_id, approval_id, idempotency_key]
      properties:
        order_id: { type: string, maxLength: 64 }
        ticket_id: { type: string, pattern: "^SOL-[0-9]{8}-[0-9]{3}$" }
        approval_id: { type: string, pattern: "^apr-[a-f0-9]{16}$" }
        idempotency_key: { type: string, pattern: "^[a-f0-9]{32}$" }
        correlation_id: { type: string, maxLength: 64 }

  - name: exec_positions
    kind: read
    side_effect: read
    gates: []
    description: Open paper positions with mark-to-market. Read-only ledger view.
    backend: exec.positions
    input:
      type: object
      additionalProperties: false
      properties:
        mint: { type: string, minLength: 32, maxLength: 44 }
        correlation_id: { type: string, maxLength: 64 }

  - name: market_price
    kind: read
    side_effect: read
    gates: []
    description: >-
      Spot price in SOL from bonding-curve reserves with Jupiter cross-check. Used for
      precondition 4 (live mid-price within tolerance of the brief).
    backend: market.price
    input:
      type: object
      additionalProperties: false
      required: [mint]
      properties:
        mint: { type: string, minLength: 32, maxLength: 44 }
        correlation_id: { type: string, maxLength: 64 }

  - name: onchain_priority_fee
    kind: read
    side_effect: read
    gates: []
    description: Recommended compute-unit price from getRecentPrioritizationFees, capped.
    backend: onchain.priority_fee
    input:
      type: object
      additionalProperties: false
      properties:
        percentile: { type: integer, minimum: 0, maximum: 100, default: 50 }
        multiplier: { type: number, minimum: 1.0, maximum: 3.0, default: 1.2 }
        max_micro_lamports: { type: integer, minimum: 1, default: 50000 }
        correlation_id: { type: string, maxLength: 64 }
```

Differences from the programming-desk file that the port must carry: `backend` values
are `<namespace>.<verb>` registry capabilities rather than gateway module paths, because
the gateway is a thin wrapper over the in-process `ToolRegistry` (D2
`services/desk-gateway/`); `packs_allowed: false` for every pumpgrok seat (no tool-packs
in D2); `approval_id` pattern `apr-<16 hex>` is the `ApprovalRecord.id` format in
`docs/design/interfaces.md` section 9.

## 12. CLI wrappers

Seat CLIs are thin wrappers over catalog tools (orchestrator decision):

| CLI | Tools called |
|---|---|
| `pumpgrok run --mode paper [--once] [--replay <dir>]` | supervisor; every tool via registry |
| `pumpgrok doctor` / `audit` / `verify` | desk.doctor, desk.receipt_check, desk.ownership_resolve |
| `pumpgrok report --daily` / `--weekly` | journal.render_report |
| `pumpgrok scout discover` / `pipeline` | market.trades, market.liquidity, onchain.authorities, journal.append |
| `pumpgrok risk audit` | safety.score_report, risk.check_limits, journal.append |
| `pumpgrok chief pickup` | desk.brief, risk.halt_status, exec.positions, notify.alert |
| `pumpgrok rug watch` | onchain.lp_status, onchain.large_transfers, onchain.authorities, notify.alert |
| `pumpgrok journal rollup` | journal.render_report |
| `pumpgrok ticket next` / `create` / `list` | journal.append (kind ticket); ledger read (port of `tools/ticket_helper.py:80,90`) |
| `pumpgrok state status` / `halt` | risk.halt_status; risk.kill_switch set (port of `tools/desk_state.py:195,213`) |
| `pumpgrok paper buy` / `sell` | exec.simulate + exec.place with an explicit `--approval-id` (port of `tools/paper_sim.py`) |
| `pumpgrok killswitch set` / `clear` / `status` | risk.kill_switch |

## Unverified Items

| Item | Default assumed |
|---|---|
| pump.fun `/coins/{mint}` field names for `complete`/graduation and LP mint (vendor reads them heuristically, `scout-vendor-engine.md:96`) | `onchain.lp_status` reports `stage: unknown` when fields are absent |
| Whether `getRecentPrioritizationFees` with account keys is accepted by all failover RPCs | default `accounts: []` as today (`tools/priority_fee.py:45`) |
| Jupiter lite-api rate limit for unauthenticated use (`scout-pumpgrok-code.md:82`) | `jupiter_lite` bucket 60/min, burst 10 (REVIEW) |
| Telegram Bot API delivery path: `hermes/profiles.yaml:16` names a token profile but no code sends today | `sendMessage` via httpx with token from env `PUMPGROK_TELEGRAM_TOKEN` |
| Vendor `Notifier` line numbers beyond `:40` and `:62` (`_send :91`, `_allow_now`) come from `scout-vendor-engine.md:44` | as the scout reports |
| Timeout and retry values | REVIEW; all are config fields under `tools.<name>` |
| Honeypot heuristic via `exec.simulate` sell path on bonding-curve math | sufficient for pump.fun curve tokens; graduated tokens get `status: blind` for `honeypot` until a sell-simulation source exists |
| Vendor line numbers `src/pipeline.py:334` `_check_transitions`, `src/reputation.py:31,48,129`, `scripts/dashboard.py`, `scripts/replay.py` come from `scout-vendor-engine.md:33,43,51-52`, not re-read here | as the scout reports |
