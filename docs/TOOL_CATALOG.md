# TOOL_CATALOG - Every tool the pumpgrok desk exposes

Tracker: SPE-17999 https://linear.app/swcstudio/issue/SPE-17999/n3-target-bot-roster-skill-manifests-tool-catalog-core-interfaces | Notion https://app.notion.com/p/3ffbc1a0c7ae8190b46ced6823fa3c90?pvs=204

Design document only. Companion to `docs/ROSTER.md` (who may call what) and
`docs/design/interfaces.md` (the `ToolSpec` model every entry below instantiates).

## 0. Conventions

| Attribute | Meaning |
|---|---|
| name | `<namespace>.<verb>`, dotted, and nothing else: catalog, roster YAML `name`, registry, tests and ownership all use this one id (R19). Transport encoding rule, stated once: the MCP/gateway transport name is the same id with each `.` replaced by an underscore, derived at exposure time by the gateway and never stored or documented as an alias. The ported G-7 `TOOL_NAME_RE` is `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$` (today's underscore-only regex: `programming-desk/ci/gates/check_desk_integrity.py:46`) |
| side_effect | `read` (never mutates a system of record, fails open with empty result + reason), `paper-write` (mutates the paper ledger / journal / desk state, fails closed), `live-write` (would submit a real transaction; present in the enum, absent from every roster, never resolvable: D3/D4) |
| timeout_s | wall-clock limit per call; REVIEW values derived from today's `timeout=12` (`tools/jupiter_quote.py:33`) and `timeout=15` (`tools/authority_check.py` `rpc_call`) and vendor `request_timeout: 10` (`vendor/grokbot-pumpfun/src/models.py:311`) |
| retry | tenacity policy (D5): `none`, or `jitter(n, base_s, max_s)` = exponential backoff with full jitter, n attempts, retry only on timeout / 5xx / 429 (vendor precedent `src/agents/base.py:131-182` retries 5xx/429/timeouts, never other 4xx) |
| rate_limit_key | token-bucket key shared by every tool hitting the same upstream (vendor `RateLimiter`, `src/ops.py:90`) |
| idempotency_key | writes only; derivation in `docs/design/interfaces.md` section 10; a repeated call with the same key returns the first result and performs nothing. `exec.place` keys on `(ticket_id, side, decision_id)` where `decision_id` is a ULID minted per decision (R23); a new decision is a new order |
| backend | data source and endpoint, with the file:line in current code that proves the desk already uses it (D8: Solana mainnet; pump.fun frontend REST + PumpPortal WS; Jupiter lite-api quote; Solana JSON-RPC with failover list; x.ai Grok) |
| callers | seats whose roster carries the tool (`docs/ROSTER.md` section 6) |
| source | the existing function to port, or `new` |

Common envelope. Every output includes `meta: {source: str, fetched_at: datetime(UTC),
freshness_s: float, correlation_id: str, stale: bool}`; every input accepts an optional
`correlation_id` (propagated by the registry if omitted; section 10 of interfaces.md). The
schemas below list only tool-specific fields. `required` marks required inputs.

Types: `Mint` = base58 string 32..44 chars; `Pubkey` = same; `Lamports` = integer SOL
base units (R28: no float money anywhere); `Units` = integer token base units (R28);
`Ratio` = decimal string (e.g. `"0.0123"`) used only for derived ratios such as prices,
shares and impacts; `Bps` = integer basis points 0..10000; `TicketId` =
`^SOL-\d{8}-\d{3}$` (`tools/ticket_helper.py:28`); `Ulid` = 26-char Crockford base32 from
`src/pumpgrok/core/ids.py` (R29; used for `correlation_id`, `decision_id`, `order_id`).
Field names carry the unit: `*_lamports: Lamports`, `*_units: Units`, prices and shares
are `Ratio`.

Data-source fallback (spec `MARKET_DATA_TOOLS`, xml line 94): every `read` tool returns
the last cached value with `meta.stale = true` when the upstream fails and a cache entry
younger than `cache_max_age_s` (config, REVIEW 300) exists; otherwise an empty result
with `reason`.

## 1. market.* (read; Scout owns `src/pumpgrok/tools/market/`)

### market.price

| Attribute | Value |
|---|---|
| description | Spot price of a token in SOL. Pre-graduation the price is computed from the pump.fun bonding-curve reserves and is the only price the fill model uses; the Jupiter quote is informational (route, priority) and never a fill price (R38). After graduation only the Jupiter route price is available and `graduated: true` is reported |
| input | `mint: Mint` (required); `quote_mint: Mint` (default WSOL); `probe_amount_lamports: Lamports` (default 1_000_000) |
| output | `price: Ratio` (SOL per token); `source: enum[curve, jupiter]`; `curve_progress: Ratio` 0..1; `market_cap_lamports: Lamports`; `graduated: bool`; `context_slot: int or null` |
| side_effect | read |
| timeout_s | 10 |
| retry | jitter(3, 0.5, 4) |
| rate_limit_key | `pumpfun_rest` or `jupiter_lite` |
| backend | GET `https://frontend-api.pump.fun/coins/{mint}` (`vendor/grokbot-pumpfun/src/models.py:309`, `src/executor.py:65-77` `price`, `src/executor.py:85` `price_from_reserves`); fallback GET `https://lite-api.jup.ag/swap/v1/quote` (`tools/jupiter_quote.py:22`) |
| callers | scout, sniper, rug, exit, signal |
| source | port `vendor/grokbot-pumpfun/src/executor.py:85-96` `price_from_reserves`; `tools/jupiter_quote.py:25` `get_quote` |

### market.ohlcv

| Attribute | Value |
|---|---|
| description | Candles built from the trade stream (pump.fun has no OHLCV endpoint; candles are aggregated locally from `market.trades`) |
| input | `mint: Mint` (required); `interval_s: int enum[15, 60, 300]` (default 60); `limit: int 1..500` (default 100) |
| output | `candles: list[{ts: int, open: Ratio, high: Ratio, low: Ratio, close: Ratio, volume_lamports: Lamports, trades: int}]`; `partial_last: bool` |
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
| input | `mint: Mint` (required); `order_size_lamports: Lamports >= 0` (default 0) |
| output | `virtual_sol_reserves_lamports: Lamports`; `virtual_token_reserves_units: Units`; `liquidity_lamports: Lamports`; `curve_progress: Ratio`; `price_impact: Ratio`; `order_to_liquidity_ratio: Ratio`; `graduated: bool` |
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
| output | `trades: list[{ts: int, side: enum[buy, sell], wallet: Pubkey, sol_lamports: Lamports, token_units: Units, signature: str or null}]`; `buy_sell_ratio: Ratio`; `unique_wallets: int` |
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
| output | `holder_count: int`; `holders: list[{wallet: Pubkey, share: Ratio}]`; `top5_share: Ratio`; `creator_share: Ratio` |
| side_effect | read |
| timeout_s | 10 |
| retry | jitter(3, 0.5, 4) |
| rate_limit_key | `pumpfun_rest` |
| backend | GET `https://frontend-api.pump.fun/coins/{mint}/holders?limit=50` (`analyzer.py:85`, `HOLDER_LIMIT=50`) |
| callers | scout, whale, signal |
| source | port `analyzer.py:114` `parse_holder`, `analyzer.py:168` `compute_metrics` (top5/creator share) |

## 2. onchain.* (read; Rug owns `src/pumpgrok/tools/onchain/` as directory owner incl. `rpc.py`; Whale owns `holders.py` and `transfers.py`, R31)

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
| callers | scout, rug (RISK reads the result inside the safety report, R35) |
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
| callers | rug |
| source | new (no existing tool covers LP; `scout-pumpgrok-pack.md:125`) |

### onchain.top_holders

| Attribute | Value |
|---|---|
| description | On-chain largest token accounts with LP/curve accounts excluded, concentration percentages against total supply (fixes today's "of sampled top-N only; LP not excluded" caveat, `scout-pumpgrok-code.md:24`) |
| input | `mint: Mint` (required); `limit: int 1..20` (default 20); `exclude: list[Pubkey]` (default: curve + LP accounts from `onchain.lp_status`) |
| output | `holders: list[{address: Pubkey, owner: Pubkey or null, amount_units: Units, share: Ratio}]`; `top1_share: Ratio`; `top5_share: Ratio`; `top10_share: Ratio`; `supply_units: Units`; `excluded: list[Pubkey]` |
| side_effect | read |
| timeout_s | 15 |
| retry | jitter(3, 0.5, 5) |
| rate_limit_key | `solana_rpc` |
| backend | JSON-RPC `getTokenLargestAccounts [mint]` (`tools/holder_check.py:43`) + `getTokenSupply` |
| callers | whale, rug |
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
| callers | whale (WHALE-only grant, R35; `safety.score_report` composes it in-process for RUG) |
| source | port `src/reputation.py` (`CreatorRecord` `:31`, `ReputationBook` `:48`) into `src/pumpgrok/tools/onchain/deployer.py`; RPC part new |

### onchain.large_transfers

| Attribute | Value |
|---|---|
| description | Recent transfers above a threshold by top holders or the creator; feeds WHALE clusters and RUG "large insider sells" trigger (`agents/rug.md:41`) |
| input | `mint: Mint` (required); `wallets: list[Pubkey]` (default: top 10 holders); `min_share: Ratio` (default `"0.005"`); `since_ts: int or null` |
| output | `transfers: list[{ts: int, signature: str, from: Pubkey, to: Pubkey, amount_units: Units, share: Ratio, kind: enum[sell, transfer, lp_remove, unknown]}]` |
| side_effect | read |
| timeout_s | 20 |
| retry | jitter(3, 0.5, 5) |
| rate_limit_key | `solana_rpc` |
| backend | JSON-RPC `getSignaturesForAddress` + `getTransaction` (jsonParsed) per wallet, bounded by `limit` |
| callers | whale (WHALE-only grant, R35; `safety.score_report` composes it in-process for RUG) |
| source | new |

### onchain.priority_fee

| Attribute | Value |
|---|---|
| description | Recommended compute-unit price from recent prioritization fees; used by the PaperAdapter fee model and reported in fills (`agents/sniper.md:49,53`) |
| input | `percentile: int 0..100` (default 50); `multiplier: Ratio 1.0..3.0` (default `"1.2"`); `max_micro_lamports: int` (default 50000; the cap that today's `tools/priority_fee.py` documents but does not enforce, `scout-pumpgrok-code.md:25`); `accounts: list[Pubkey]` (default []) |
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
| input | `mint: Mint` (required); `intended_size_lamports: Lamports >= 0` (default 0); `thresholds: object or null` (override of `config.safety.thresholds`; keys below); `checks: list[str] or null` (subset to run; default all) |
| output | `score: int 0..100` (100 = safest); `verdict_recommendation: enum[CLEAR, CONDITIONAL, KILL]` (recommendation only; RISK issues the verdict from the `JournalNote` `note_kind: safety_report` that RUG appends); `hard_veto: bool`; `checks: list[{id: enum[mint_authority, freeze_authority, lp_status, transfer_tax, honeypot, top10_concentration, bundler_cluster, deployer_history, token2022_extensions, liquidity_depth], status: enum[pass, warn, fail, blind], value: any, threshold: any, weight: Ratio, reason: str}]`; `blind_checks: list[str]`; `evidence: list[{check: str, source: str, slot: int or null, fetched_at: datetime}]`; `thresholds_used: object` |
| side_effect | read |
| timeout_s | 45 (composes up to 8 onchain/market calls) |
| retry | none at this level (inner tools retry) |
| rate_limit_key | `solana_rpc` (inherited) |
| backend | composes `onchain.authorities`, `onchain.lp_status`, `onchain.token_metadata`, `onchain.top_holders`, `onchain.deployer_history`, `market.liquidity`, `market.trades`; honeypot heuristic = sell-side simulation through `exec.simulate` on the PaperAdapter curve math (no transaction) |
| callers | rug only (R35: RISK consumes the report event through `portfolio.ledger_read` and never re-runs it) |
| source | new orchestration; metrics from `analyzer.py:168` `compute_metrics`, `:219` `_count_snipers`, `:226` `_wallet_diversity`, `:285` `_veto_reason`, `:294` `_risk_score` |

Threshold keys (config `safety.thresholds`, every value REVIEW; defaults from
`agents/risk.md:42-49`): `transfer_tax_hard_fail_pct: 10`, `transfer_tax_warn_pct: 5`,
`top10_concentration_warn_pct: 20`, `top10_concentration_fail_pct: 25`,
`liquidity_multiple_min: 10`, `liquidity_multiple_recommended: 20`,
`lp_lock_min_days: 180`, `creator_share_veto: 0.25`, `top5_share_veto: 0.80`,
`kill_below_score: 40`, `conditional_below_score: 70`. Any `blind` check on a required
id forces `verdict_recommendation = KILL` (constitution clause 10).

## 4. exec.* (Sniper owns `src/pumpgrok/tools/exec/` and `src/pumpgrok/execution/`; `src/pumpgrok/execution/live/**` is RISK's, R31)

All `exec.*` tools call the configured `ExecutionAdapter`. In every shipped configuration
that is `PaperAdapter` (`src/pumpgrok/execution/paper_adapter.py`, with `curve_math.py`,
`fees.py`, `latency.py`, R31). `src/pumpgrok/execution/live/live_adapter.py` holds the one
`LiveAdapter` stub whose every method raises `LiveGateError`; no live implementation is
registered (D4, R21 precondition 8). `src/pumpgrok/execution/live/live_gate.py` evaluates
the single nine-item precondition list of R21 against the effective execution mode:
(1) effective mode `live`; (2) env `PUMPGROK_LIVE_ENABLE=1`; (3) `live.min_paper_days`
>= 14 elapsed on ledger events with `source=paper` only; (4) `closed_trades >= 50`,
`profit_factor >= 1.2`, `max_drawdown <= drawdown_halt_fraction` on the same events;
(5) non-empty `live.wallet_allowlist` (public addresses only); (6) `0 <
live.notional_cap_sol <= 1.0`; (7) `live.confirmation_record` HMAC-signed by
`pumpgrok live confirm` with an operator secret no seat or tool can read, bound to the
config hash; (8) `live.adapter` named and registered (never true); (9) no active kill
switch, halt or open breaker. Any unmet item -> startup prints every unmet item and exits
3. A ledger containing `source=replay` events is refused for the gate's metrics; replay
runs write `var/replay/<dataset>/ledger.sqlite`.

### exec.quote

| Attribute | Value |
|---|---|
| description | Route quote for a swap: expected out amount, price impact, route plan. The Jupiter lite-api quote is informational (route, priority, cross-check) and is never the fill price: pre-graduation fills are computed from the bonding-curve reserves (R38). `source: curve` is returned when the token is not routable |
| input | `input_mint: Mint` (required); `output_mint: Mint` (required); `amount: int` (required; `Lamports` when `input_mint` is WSOL, else `Units`); `slippage_bps: Bps` (default 100) |
| output | `quote_id: str`; `in_amount: int`; `out_amount: int`; `other_amount_threshold: int`; `price_impact: Ratio`; `route_plan: list[{swap_info: object, percent: int}]`; `context_slot: int or null`; `source: enum[jupiter, curve]`; `expires_at: datetime` |
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
| description | Simulate a fill against observed liquidity without placing it: price impact vs size, fee model, expected slippage, partial-fill flag, liquidity-floor rejection (PaperAdapter fill model, `docs/design/paper-engine.md`). Full fills for size <= L/50, partial in (L/50, L/10], rejected above L/10 where L = `liquidity_lamports` (R6); the slippage threshold is recomputed for the executed size (R38); a BUY on a graduated token is rejected `post_graduation_no_reserves` (R38) |
| input | `ticket_id: TicketId` (required); `mint: Mint` (required); `side: enum[buy, sell]` (required); `size_lamports: Lamports > 0` (buy) or `token_units: Units > 0` (sell); `slippage_bps: Bps` (default 100); `quote_id: str or null` |
| output | `would_fill: bool`; `fill_kind: enum[full, partial, rejected]`; `price_expected: Ratio`; `expected_out: int` (`Units` for buy, `Lamports` for sell); `executed_size: int` (same unit as the input size; smaller than the input for a partial fill); `price_impact: Ratio`; `fee_lamports: Lamports`; `priority_fee_lamports: Lamports`; `liquidity_ratio: Ratio`; `rejection_reason: enum[below_liquidity_floor, size_too_small, post_graduation_no_reserves, data_stale] or null`; `latency_ms_estimate: int` |
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
| description | Place exactly one paper order. Fails closed. Requires an `approval_id` (g6) that resolves to an `ApprovalRecorded` ledger event of kind `human_buy` for buys (`rules/pumpgrok-team.mdc:28`) or `exit_rule` / `autonomous_paper` / `human_sell` for sells (R17, R33). `RiskEngine.check` runs inside `PaperAdapter.place` for every order and again at CONFIRMING immediately before the fill; kill switch, halts, breakers and limits found there reject the in-flight order with reason `kill_switch` / `halted` / `breaker_open` (R22, R24). A sell for a token that graduated while open is closed by the adapter with reason `graduated` and MTM frozen (R8, R38) |
| input | `ticket_id: TicketId` (required); `mint: Mint` (required); `side: enum[buy, sell]` (required); `decision_id: Ulid` (required; minted per decision, R23); `size_lamports: Lamports > 0` (buy) or `token_units: Units > 0` (sell); `max_slippage_bps: Bps` (required); `approval_id: str` (required); `quote_id: str or null` |
| output | `order_id: Ulid`; `status: enum[filled, partial, rejected, unknown]`; `signature: str` (`paper:<idempotency_key>`; never a real signature); `filled_lamports: Lamports`; `filled_units: Units`; `price_avg: Ratio`; `realised_slippage_bps: int`; `fee_lamports: Lamports`; `priority_fee_lamports: Lamports`; `route: str`; `ledger_seq: int`; `reason: str or null` (a `risk.check_limits` rule id, `post_graduation_no_reserves`, or `graduated`) |
| side_effect | paper-write |
| timeout_s | 20 |
| retry | none (single-send rule, `rules/pumpgrok-team.mdc:30`; timeout -> `status: unknown`, caller reports `UNKNOWN RESULT - reconcile by signature`) |
| rate_limit_key | `exec` (a repeated call with the same `(ticket_id, side, decision_id)` returns the stored result and performs nothing; a new `decision_id` is a new order that passes `RiskEngine.check` again, so a partial-fill remainder or a re-decided order is never stranded, R23) |
| idempotency_key | derived: `sha256(ticket_id, side, decision_id)` (R23); the adapter stores `(key -> result)` in the ledger; replay returns the stored result. The `ApprovalRecorded.consumed` update is written in the same ledger transaction as the order (R23) |
| backend | PaperAdapter.place -> `portfolio.ledger_write` (events `OrderPlaced`, then `FillRecorded` + `PositionOpened` / `PositionClosed`, or `OrderRejected`; `ApprovalRecorded` consumed update; R32) |
| callers | sniper (buy), exit (sell) |
| source | new; position bookkeeping from `vendor/grokbot-pumpfun/src/executor.py:183` `new_position`, `src/risk.py:182` `register_open`, `:188` `register_close` |

### exec.cancel

| Attribute | Value |
|---|---|
| description | Cancel a pending paper order owned by the calling seat (orders are near-instant in paper mode; cancel exists for the simulated-latency window between ACCEPTED and CONFIRMING and for parity with the adapter interface) |
| input | `order_id: Ulid` (required); `ticket_id: TicketId` (required); `approval_id: str` (required; g6) |
| output | `cancelled: bool`; `status_after: enum[cancelled, already_filled, not_found]` |
| side_effect | paper-write |
| timeout_s | 10 |
| retry | none |
| rate_limit_key | `exec` |
| idempotency_key | derived (`order_id`, `cancel`) |
| backend | PaperAdapter.cancel -> ledger event `OrderRejected` with `reason: cancelled` (R32 defines no separate cancel type) |
| callers | sniper, exit |
| source | new |

### exec.positions

| Attribute | Value |
|---|---|
| description | Open paper positions with mark-to-market from the latest curve price; a position whose token graduated is reported with `mtm_frozen: true` until the adapter's forced close (R8) |
| input | `mint: Mint or null`; `include_closed_since_ts: int or null` |
| output | `positions: list[{ticket_id: TicketId, mint: Mint, side: enum[long], price_entry: Ratio, price_peak: Ratio, sol_spent_lamports: Lamports, token_units: Units, opened_at: datetime, price_mark: Ratio or null, mtm_frozen: bool, unrealised_pnl_lamports: Lamports or null, unrealised_pnl: Ratio or null, hold_seconds: int, closed_reason: enum[stop_loss, take_profit, trailing_stop, max_hold, rug_alert, kill_flatten, blind_flatten, graduated, manual] or null}]`; `equity_lamports: Lamports`; `cash_lamports: Lamports` |
| side_effect | read |
| timeout_s | 10 |
| retry | none |
| rate_limit_key | `ledger` |
| backend | ledger snapshot + `market.price` |
| callers | chief, sniper, exit, journal |
| source | port `vendor/grokbot-pumpfun/src/models.py:243` `Position` fields; `src/risk.py:226` `pnl_pct` |

## 5. portfolio.* (Journal owns `src/pumpgrok/tools/portfolio/`; the store `src/pumpgrok/ledger/` is RISK infrastructure, R36)

### portfolio.ledger_read

| Attribute | Value |
|---|---|
| description | Read append-only ledger events and snapshots (sqlite WAL, D5; schema R32) with filters |
| input | `since_seq: int` (default 0); `types: list[str] or null` (CamelCase names from `src/pumpgrok/ledger/events.py`); `ticket_id: TicketId or null`; `source: enum[paper, replay, manual] or null`; `limit: int 1..1000` (default 200) |
| output | `events: list[{seq: int, ts_utc: datetime, source: enum[paper, replay, manual], correlation_id: Ulid, idempotency_key: str, type: str, payload: object, prev_hash: str, hash: str}]`; `latest_snapshot: {seq: int, ts_utc: datetime, equity_lamports: Lamports, cash_lamports: Lamports, positions: int} or null` |
| side_effect | read |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `ledger` |
| backend | `var/ledger.sqlite` tables `events(seq, ts_utc, source, correlation_id, idempotency_key, type, payload_json, prev_hash, hash)` and `snapshots(seq, ts_utc, state_json)` (R32); replay runs read `var/replay/<dataset>/ledger.sqlite` (R21) |
| callers | risk, journal |
| source | new; replaces `tools/pipeline_evidence.py:183` `load_records` JSONL reader and vendor `src/log.py:197` `read_log` |

### portfolio.ledger_write

| Attribute | Value |
|---|---|
| description | Append one ledger event through `src/pumpgrok/ledger/store.py`. Not in any seat roster: only the PaperAdapter, `RiskEngine.check`, the supervisor and the human CLI verbs call it in-process (`docs/ROSTER.md` section 6). Listed so the registry can audit it |
| input | `type: str` (required; one of the 18 CamelCase types in `src/pumpgrok/ledger/events.py`, R32); `source: enum[paper, replay, manual]` (required, R21); `payload: object` (required; validated against `contracts/events/<snake>.schema.json`); `ticket_id: TicketId or null`; `idempotency_key: str` (required) |
| output | `seq: int`; `hash: str`; `duplicate: bool` |
| side_effect | paper-write |
| timeout_s | 5 |
| retry | none; `sqlite3.OperationalError` -> `LedgerUnavailable`, supervisor refuses new orders (spec `GRACEFUL_DEGRADATION`) |
| rate_limit_key | `ledger` |
| idempotency_key | required input; unique index on `events.idempotency_key`; `HaltSet` / `BreakerTripped` use `(type, reason, utc_day)` so the appends are idempotent per reason and day (R24) |
| backend | `var/ledger.sqlite` (hash chain `prev_hash` / `hash` computed inside the append transaction) |
| callers | none (adapter/supervisor only) |
| source | new; `paper_sim.py:25` `append_paper_fill` markdown append is retired |

### portfolio.exposure

| Attribute | Value |
|---|---|
| description | Current exposure: per token, total, fraction of paper equity, open position count; what `RiskEngine.check` compares against the R20 budget |
| input | `mint: Mint or null` |
| output | `equity_lamports: Lamports`; `cash_lamports: Lamports`; `gross_exposure_lamports: Lamports`; `gross_exposure_fraction: Ratio`; `open_positions: int`; `trades_today: int`; `per_token: list[{mint: Mint, exposure_lamports: Lamports, exposure_fraction: Ratio}]` |
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
| description | Realised and unrealised PnL for a window; daily loss fraction that the 5% constitutional halt reads (`rules/pumpgrok-team.mdc:34`, `daily_loss_halt_fraction`, R20). Day attribution uses the fill timestamp (R38) |
| input | `window: enum[day, week, all]` (default day); `as_of: datetime or null` |
| output | `realised_lamports: Lamports`; `unrealised_lamports: Lamports`; `fees_lamports: Lamports`; `daily_loss_fraction: Ratio`; `day_start_equity_lamports: Lamports`; `peak_equity_lamports: Lamports`; `drawdown_fraction: Ratio`; `trades: int`; `closed_trades: int`; `win_rate: Ratio or null`; `profit_factor: Ratio or null` |
| side_effect | read |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `ledger` |
| backend | ledger |
| callers | chief, risk, journal |
| source | port `vendor/grokbot-pumpfun/src/risk.py:122-136` (`daily_loss`, `remaining_loss_budget`, `halted`) semantics; adds unrealised and drawdown |

## 6. risk.* (Risk owns `src/pumpgrok/tools/risk/` and `src/pumpgrok/risk/`: `engine.py` (`RiskEngine`), `limits.py`, `sizing.py`, `breakers.py`, `killswitch.py`, R31)

### risk.check_limits

| Attribute | Value |
|---|---|
| description | Read-only view of `RiskEngine.check` (`src/pumpgrok/risk/engine.py`): evaluate a proposed order against the R20 budget, verdict state, approval record, halt, breakers and kill switch and return every rule evaluated; a `KILL` verdict on the ticket is non-overridable (D9). The same engine runs as library code inside `PaperAdapter.place` for every order regardless of seat rosters or seat health and again at CONFIRMING; that in-process run owns the `HaltSet` / `BreakerTripped` appends (R22, R24) |
| input | `ticket_id: TicketId` (required); `mint: Mint` (required); `side: enum[buy, sell]` (required); `size_lamports: Lamports >= 0` (required); `decision_id: Ulid or null`; `approval_id: str or null`; `bot: str` (seat id, injected by registry) |
| output | `approved: bool`; `reason: str` (the first failing rule id); `rules: list[{id: enum[ledger_inconsistent, kill_switch, halted, breaker_open, live_gate, approval_missing, approval_mismatch, seat_may_trade, max_trades_per_day, max_open_positions, already_open, creator_already_open, max_trade_fraction, max_token_fraction, daily_loss_halt, drawdown_halt, data_stale, size_too_small, below_liquidity_floor], status: enum[pass, fail, skip], value: any, limit: any}]` (R34: one vocabulary, in engine order); `limits: {max_trade_fraction: Ratio, max_token_fraction: Ratio, daily_loss_halt_fraction: Ratio, drawdown_halt_fraction: Ratio, max_open_positions: int, max_trades_per_day: int, liquidity_floor_multiple: int, partial_fill_fraction: Ratio, paper_equity_sol: int}` (the effective R20 budget, every value REVIEW); `size_cap_lamports: Lamports` |
| side_effect | read (pure evaluation; the enforcing run is inside the adapter, R24) |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `ledger` |
| backend | ledger + config `[risk]` block (R20 keys) + `var/KILLSWITCH` + breaker state |
| callers | chief, risk; `RiskEngine.check` in-process for sniper/exit orders (no roster grant needed) |
| source | port `vendor/grokbot-pumpfun/src/risk.py:149` `evaluate` and `:143` `position_size` (score-proportional sizing, `MAX_SHARE_OF_REMAINING_BUDGET=0.30` at `:33`, `MIN_TRADE_SOL=0.01` at `:36`) into `src/pumpgrok/risk/{engine,limits,sizing}.py`, extended with fraction-of-equity limits |

### risk.drawdown

| Attribute | Value |
|---|---|
| description | Drawdown from peak equity and loss velocity (loss per hour) for the `loss_velocity` breaker |
| input | `window_hours: int 1..168` (default 24) |
| output | `peak_equity_lamports: Lamports`; `current_equity_lamports: Lamports`; `drawdown_fraction: Ratio`; `loss_velocity_lamports_per_h: Lamports`; `halted: bool` |
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
| description | Set the global kill switch or request a flatten of every open paper position (D6, R22). Actions `set` and `flatten_request` only: `clear` is not a tool action; it is the human CLI `pumpgrok killswitch clear --by <human> --reason <text>`, which appends `KillSwitchCleared` with an `ApprovalRecorded` of kind `killswitch_clear` (R22, R33). Sources: env `PUMPGROK_KILLSWITCH=1` read once at start; file `var/KILLSWITCH` and the alert-channel command polled every cycle. `RiskEngine.check` re-checks the switch at CONFIRMING so in-flight orders are rejected with reason `kill_switch`; `flatten_request` waits on the in-flight barrier, then closes every open position with reason `kill_flatten` |
| input | `action: enum[set, flatten_request]` (required); `reason: str` (required) |
| output | `active: bool`; `since: datetime or null`; `source: enum[env, file, command, none]`; `flatten_requested: bool`; `reason: str or null` |
| side_effect | paper-write |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `killswitch` |
| idempotency_key | derived (`risk.kill_switch`, action, reason, UTC minute) |
| backend | `var/KILLSWITCH` file + ledger events `KillSwitchSet` / `PositionClosed` (`reason: kill_flatten`) + `Escalation` (relayed to `notify.alert` by the supervisor) |
| callers | risk only (`docs/ROSTER.md` section 6); `pumpgrok killswitch set|flatten` CLI; status is read through `risk.halt_status` |
| source | new; replaces `tools/desk_state.py:195` `write_halt` (`Halt: true` in desk.md) |

### risk.halt_status

| Attribute | Value |
|---|---|
| description | Combined halt view: daily-loss floor halt, drawdown halt, kill switch, breaker states with cooldown expiry, engagement level and effective execution mode |
| input | none |
| output | `halted: bool`; `reasons: list[enum[daily_loss, drawdown, kill_switch, breaker_data_stale, breaker_loss_velocity, breaker_exec_errors, manual]]`; `kill_switch: {active: bool, since: datetime or null, source: enum[env, file, command, none], flatten_requested: bool}`; `breakers: list[{id: str, open: bool, trips: int, cooldown_until: datetime or null}]`; `engagement: enum[research, paper]` (R16: `micro-live` is retired); `execution_mode: enum[paper, live]` (effective mode; `live` never passes the gate); `autonomy_level: enum[manual-ticket, autonomous-paper]` |
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
| description | Human alert through the abstract `Notifier`. Sinks: stdout + file always on; Telegram and webhook adapters config-driven (D6; `hermes/profiles.yaml:16` `telegram_token_profile: chief`). Destinations are restricted to the configured allowlist `notify.allowlist` (Telegram chat ids, webhook URLs); a destination outside the allowlist is refused, never sent (R39). Never posts to social platforms (D7): `notify.*` is inside the no-manipulation static test scope (`tests/safety/test_no_manipulation_tools.py`, R39). The supervisor calls this tool to relay every `Escalation` ledger event, which is how RISK and RUG alerts reach a human without a roster grant (R35) |
| input | `severity: enum[info, warning, critical]` (required); `kind: enum[rug_flag, halt, breaker, killswitch, escalation, report, unknown_result, bot_restart_exhausted, heartbeat_stale, persistence_down, clock_skew, ledger_inconsistent]` (required; the same enum as `contracts/events/escalation.schema.json` `kind`, R40); `text: str maxLength 4000` (required); `ticket_id: TicketId or null`; `fields: object`; `destinations: list[str] or null` (subset of the allowlist; default all); `idempotency_key: str or null` |
| output | `delivered: list[{sink: str, ok: bool, error: str or null}]`; `suppressed: bool` (rate limit) |
| side_effect | paper-write |
| timeout_s | 10 |
| retry | jitter(3, 1, 8) per network sink; stdout/file never retried |
| rate_limit_key | `notify` (sliding window per minute; vendor `Notifier._allow_now`, `src/alerts.py:40-91`) |
| idempotency_key | derived (`kind`, `ticket_id`, `severity`, UTC minute) when omitted |
| backend | stdout, `var/alerts.log`, Telegram Bot API `sendMessage` (token from env profile; `chat_id` must be in `notify.allowlist`), generic webhook POST `{event, text, fields, ts}` to allowlisted URLs only (`src/alerts.py:91` `_send`) |
| callers | chief, journal; supervisor relay for `Escalation` events (RISK and RUG hold no grant, R35) |
| source | port `vendor/grokbot-pumpfun/src/alerts.py:40` `Notifier` behind an ABC |

## 8. journal.* (Journal owns `src/pumpgrok/tools/journal/` and `src/pumpgrok/reporting/`)

### journal.append

| Attribute | Value |
|---|---|
| description | Append a decision/journal entry keyed by ticket (constitution clause 8: "Log every decision with ticket ID. The journal is the only audit evidence."). Stored as a ledger event of the named type and exported to `var/journal/YYYY-MM-DD.jsonl` |
| input | `kind: str` (required; the snake_case form of a ledger type from `src/pumpgrok/ledger/events.py`, generated from the registry, R32; seats may write only `journal_note` and `escalation`; every other kind is adapter / `RiskEngine` / supervisor / CLI-only and is rejected with `kind_not_seat_writable`); `note_kind: enum[lead, whale, social, signal, verdict, safety_report, ticket, halt, review, note]` (required when `kind = journal_note`; the registry restricts each seat to the `note_kind`s listed in its manifest, `docs/ROSTER.md` section 5); `ticket_id: TicketId or null`; `body: object` (required; validated against `contracts/events/<kind>.schema.json`); `bot: str` (injected) |
| output | `seq: int`; `journal_path: str` |
| side_effect | paper-write |
| timeout_s | 5 |
| retry | none |
| rate_limit_key | `ledger` |
| idempotency_key | derived (`kind`, `ticket_id`, sha256(body)) |
| backend | ledger (`JournalNote` / `Escalation`) + JSONL export |
| callers | chief, scout, whale, shill, signal, journal |
| source | replaces `tools/paper_sim.py:25` `append_paper_fill` and vendor `src/log.py:40` `TradeLog` |

### journal.render_report

| Attribute | Value |
|---|---|
| description | Render the daily (00:05Z) or weekly (Monday 00:15Z) report (trades taken, win rate, PnL, max drawdown, rejected signals and why, safety false positives/negatives if later known, bot health; spec `REPORTING`, xml line 108; R40) to markdown under `var/reports/` with `str.format` templates (R9, no templating dependency) and deliver via `notify.alert` (kind `report`) |
| input | `period: enum[daily, weekly]` (required); `as_of: datetime or null`; `deliver: bool` (default true) |
| output | `report_path: str`; `summary: {trades: int, closed_trades: int, win_rate: Ratio or null, profit_factor: Ratio or null, realised_lamports: Lamports, max_drawdown_fraction: Ratio, rejected_signals: int, open_positions: int, halts: int, bot_health: object}` |
| side_effect | paper-write |
| timeout_s | 30 |
| retry | none |
| rate_limit_key | `ledger` |
| idempotency_key | derived (`period`, `as_of` day) |
| backend | ledger reads + `str.format` markdown templates in `src/pumpgrok/reporting/` (R9); written via tmp file + `os.replace` |
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
| desk.event_emit | paper-write | 5 | none | `desk` | Emit a seat-attributed event to the ledger event log; payload redacted and capped at 4 KB (`_core.yaml:113-128`) | **kind** (snake_case ledger type from the registry, R32; seats may emit `journal_note` and `escalation` only, with `note_kind` as for `journal.append`), `task_id`, `payload` | `seq: int` | `core.event_emit` -> `portfolio.ledger_write` |
| desk.doctor | paper-write | 60 | none | `desk` | `check` verifies prompt SHA, skills, roster, registry grants, effective execution mode == paper; `register` records the Bot's agent id; `install_prompt` returns the assembled prompt; `repair` re-runs install (`_core.yaml:130-148`); `pumpgrok doctor` CLI | **action: enum[check, register, install_prompt, repair]**, `agent_uuid`, `channel_id`, `prompt_sha256`, `installed_skills` | `ok: bool`, `rows: list[{check, status, detail}]` | `core.doctor` |

Idempotency for `desk.memory_retain`, `desk.event_emit`, `desk.doctor`: derived
(`tool`, `bot`, sha256(input)).

## 10. Side-effect summary

| side_effect | Tools | Roster `kind` | Gate tag |
|---|---|---|---|
| read | market.*, onchain.*, safety.score_report, exec.quote, exec.simulate, exec.positions, portfolio.ledger_read, portfolio.exposure, portfolio.pnl, risk.check_limits, risk.drawdown, risk.halt_status, desk.brief, desk.docs_search, desk.memory_recall, desk.ownership_resolve, desk.receipt_check | `read` | - |
| paper-write | exec.place, exec.cancel, portfolio.ledger_write, risk.kill_switch, notify.alert, journal.append, journal.render_report, desk.memory_retain, desk.event_emit, desk.doctor | `write` | `g6` on exec.place and exec.cancel because each requires `approval_id` in `input.required` (`check_desk_integrity.py:55-58`); risk.kill_switch carries no gate tag because `clear` is not a tool action (R22) |
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

Effective roster for sniper = core 8 + 7 = 15, the ported G-7 ceiling (`ROSTER_MAX_TOOLS = 15`,
`check_desk_integrity.py:42`; the minimum becomes 8, R19). Every `name:` is the dotted id.

```yaml
# SNIPER roster: core 8 + 7 = 15. Contract surface (RISK); consumer bot-04-sniper.
# Conventions (contracts/tool-rosters/_core.yaml):
#   name:        dotted <namespace>.<verb> registry id (R19); the gateway derives the
#                transport name at exposure time and nothing stores a second spelling
#   kind:        read  - never mutates a system of record; fails open (empty result + reason)
#                write - mutates; fails closed
#   side_effect: read | paper-write   (live-write is never permitted in a roster)
#   gates:       g6 - approval_id is required and echoed into the audit event
#   backend:     the registry capability that implements the tool
#   money:       integers in base units (lamports, token units); never floats (R28)
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
  - name: exec.quote
    kind: read
    side_effect: read
    gates: []
    description: >-
      Route quote for a swap through the configured ExecutionAdapter (paper). Returns
      expected out amount, price impact and route plan. Informational only: the fill is
      computed from the bonding curve (R38). Never submits anything.
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
        correlation_id: { type: string, pattern: "^[0-9A-HJKMNP-TV-Z]{26}(\\.[0-9]+)*$" }

  - name: exec.simulate
    kind: read
    side_effect: read
    gates: []
    description: >-
      Simulate a fill against observed liquidity: expected price, impact, fee, partial-fill
      or liquidity-floor rejection. Precondition for exec.place.
    backend: exec.simulate
    input:
      type: object
      additionalProperties: false
      required: [ticket_id, mint, side, size_lamports]
      properties:
        ticket_id: { type: string, pattern: "^SOL-[0-9]{8}-[0-9]{3}$" }
        mint: { type: string, minLength: 32, maxLength: 44 }
        side: { type: string, enum: [buy] }
        size_lamports: { type: integer, minimum: 1 }
        slippage_bps: { type: integer, minimum: 0, maximum: 10000, default: 100 }
        quote_id: { type: string, maxLength: 64 }
        correlation_id: { type: string, pattern: "^[0-9A-HJKMNP-TV-Z]{26}(\\.[0-9]+)*$" }

  - name: exec.place
    kind: write
    side_effect: paper-write
    gates: [g6]
    description: >-
      Place exactly one paper BUY for an approved ticket. Fails closed. approval_id must
      resolve to the ApprovalRecorded event (kind human_buy) for this ticket, mint, size
      and slippage. RiskEngine.check runs inside PaperAdapter.place and again at
      CONFIRMING (kill switch, halts, breakers, limits). Idempotent on
      (ticket_id, side, decision_id). No retry: a timeout is reported as
      UNKNOWN RESULT - reconcile by signature.
    backend: exec.place
    input:
      type: object
      additionalProperties: false
      required: [ticket_id, mint, side, decision_id, size_lamports, max_slippage_bps, approval_id]
      properties:
        ticket_id: { type: string, pattern: "^SOL-[0-9]{8}-[0-9]{3}$" }
        mint: { type: string, minLength: 32, maxLength: 44 }
        side: { type: string, enum: [buy] }
        decision_id: { type: string, pattern: "^[0-9A-HJKMNP-TV-Z]{26}$" }
        size_lamports: { type: integer, minimum: 1 }
        max_slippage_bps: { type: integer, minimum: 1, maximum: 10000 }
        approval_id: { type: string, pattern: "^apr-[a-f0-9]{16}$" }
        quote_id: { type: string, maxLength: 64 }
        correlation_id: { type: string, pattern: "^[0-9A-HJKMNP-TV-Z]{26}(\\.[0-9]+)*$" }

  - name: exec.cancel
    kind: write
    side_effect: paper-write
    gates: [g6]
    description: Cancel a pending paper order that this seat placed. Fails closed.
    backend: exec.cancel
    input:
      type: object
      additionalProperties: false
      required: [order_id, ticket_id, approval_id]
      properties:
        order_id: { type: string, pattern: "^[0-9A-HJKMNP-TV-Z]{26}$" }
        ticket_id: { type: string, pattern: "^SOL-[0-9]{8}-[0-9]{3}$" }
        approval_id: { type: string, pattern: "^apr-[a-f0-9]{16}$" }
        correlation_id: { type: string, pattern: "^[0-9A-HJKMNP-TV-Z]{26}(\\.[0-9]+)*$" }

  - name: exec.positions
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
        correlation_id: { type: string, pattern: "^[0-9A-HJKMNP-TV-Z]{26}(\\.[0-9]+)*$" }

  - name: market.price
    kind: read
    side_effect: read
    gates: []
    description: >-
      Spot price in SOL from bonding-curve reserves with the Jupiter route as an
      informational cross-check. Used for precondition 4 (live mid-price within
      tolerance of the brief).
    backend: market.price
    input:
      type: object
      additionalProperties: false
      required: [mint]
      properties:
        mint: { type: string, minLength: 32, maxLength: 44 }
        correlation_id: { type: string, pattern: "^[0-9A-HJKMNP-TV-Z]{26}(\\.[0-9]+)*$" }

  - name: onchain.priority_fee
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
        multiplier: { type: string, pattern: "^[1-3](\\.[0-9]+)?$", default: "1.2" }
        max_micro_lamports: { type: integer, minimum: 1, default: 50000 }
        correlation_id: { type: string, pattern: "^[0-9A-HJKMNP-TV-Z]{26}(\\.[0-9]+)*$" }
```

Differences from the programming-desk file that the port must carry: `name` is the dotted
registry id and `backend` repeats it (the gateway is a thin wrapper over the in-process
`ToolRegistry`, D2 `services/desk-gateway/`; the ported G-7 `TOOL_NAME_RE` accepts dots,
R19); `packs_allowed: false` for every pumpgrok seat (no tool-packs in D2); `approval_id`
pattern `apr-<16 hex>` is the `ApprovalRecord.id` format in `docs/design/interfaces.md`
section 9; `decision_id`, `order_id` and `correlation_id` are ULIDs from
`src/pumpgrok/core/ids.py` (R29; child spans `<ulid>.<n>`); money fields are integers in
base units (R28).

## 12. CLI wrappers

Seat CLIs are thin wrappers over catalog tools (orchestrator decision). Human-only verbs
(`killswitch clear`, `state halt --clear`, `live confirm`) do not go through any seat
roster: they append to the ledger through `src/pumpgrok/ledger/store.py` with an
`ApprovalRecorded` of the matching kind (R22, R33). SOL amounts on the CLI (`--size-sol`)
are converted to lamports at the boundary (R28).

| CLI | Tools called |
|---|---|
| `pumpgrok run --mode paper [--once] [--replay <dataset>] [--record <dataset> --duration <s>]` | supervisor; every tool via registry (R40) |
| `pumpgrok doctor` / `audit` / `verify [--fixture <dataset>]` | desk.doctor, desk.receipt_check, desk.ownership_resolve (R40) |
| `pumpgrok report --daily` / `--weekly` | journal.render_report (daily 00:05Z, weekly Monday 00:15Z, R40) |
| `pumpgrok scout discover` / `pipeline` | market.trades, market.liquidity, onchain.authorities, journal.append (`journal_note`, `note_kind: lead`) |
| `pumpgrok risk audit` | portfolio.ledger_read, portfolio.exposure, portfolio.pnl, risk.drawdown, risk.check_limits, risk.halt_status, desk.event_emit (`journal_note` `note_kind: verdict`, `escalation`) (R35) |
| `pumpgrok chief pickup` | desk.brief, risk.halt_status, exec.positions, notify.alert |
| `pumpgrok rug watch` | onchain.lp_status, onchain.authorities, onchain.top_holders, market.price, desk.event_emit (`escalation` `kind: rug_flag`) (R35) |
| `pumpgrok journal rollup` | journal.render_report |
| `pumpgrok ticket next` / `create` / `list` | journal.append (`journal_note`, `note_kind: ticket`); ledger read (port of `tools/ticket_helper.py:80,90`) |
| `pumpgrok state status` | risk.halt_status (port of `tools/desk_state.py:213`) |
| `pumpgrok state halt --clear --by <human> --reason <text>` | human-only: ledger `HaltCleared` + `ApprovalRecorded` kind `halt_clear` (R22); no tool; replaces `tools/desk_state.py:195` `write_halt` |
| `pumpgrok state autonomy <manual-ticket|autonomous-paper>` | human-only: ledger `ConfigChanged` (R17, R40) |
| `pumpgrok paper buy|sell --ticket --mint --size-sol --slippage-bps --approval-id` | exec.simulate + exec.place (R40; port of `tools/paper_sim.py`); a fresh `decision_id` is minted per invocation (R23) |
| `pumpgrok killswitch set --reason` / `flatten --reason` / `status` | risk.kill_switch (`set`, `flatten_request`); status via risk.halt_status |
| `pumpgrok killswitch clear --by <human> --reason <text>` | human-only: ledger `KillSwitchCleared` + `ApprovalRecorded` kind `killswitch_clear` (R22); no tool |
| `pumpgrok live confirm` | human-only: writes `live.confirmation_record` (HMAC with an operator secret no seat or tool can read, bound to the config hash; R21 precondition 7); no tool |
| `pumpgrok replay trim` / `rebuild-ticks` | replay fixture maintenance (R12, R40); no registry tool |

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
| R28 money-field names (`*_lamports`, `*_units`, `Ratio` strings) were chosen here; `docs/design/interfaces.md` and `docs/design/paper-engine.md` must use the same names [INFERENCE] | these names; report cross-doc drift |
| `exec.cancel` maps to `OrderRejected` with `reason: cancelled` because R32 defines no cancel event type [INFERENCE] | `OrderRejected`; `reason` enum gains `cancelled` |
| Kill-switch flatten executor: the catalog assigns the `kill_flatten` closes to the supervisor calling the PaperAdapter in-process after the in-flight barrier (R22 names no executor) [INFERENCE] | supervisor in-process |
| `notify.allowlist` config key name and shape (Telegram chat ids, webhook URLs) [INFERENCE] | `notify.allowlist: list[str]`, empty list = stdout/file only |
