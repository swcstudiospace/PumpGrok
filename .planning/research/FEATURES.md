# Feature Research

**Domain:** Autonomous Solana memecoin (pump.fun) paper-trading desk. Milestone adds launch discovery, token safety scoring, signals with confidence, curve-faithful paper fills, a hash-chained ledger with PnL attribution, deterministic replay, risk controls and breakers, supervision, reports, human approval, and a disabled go-live gate.
**Researched:** 2026-10-21
**Confidence:** MEDIUM overall.
- HIGH: what the desk must do (read from `.planning/PROJECT.md`, `docs/upgrade-plan-desk-v2.md` section 5, `docs/RISK_POLICY.md`, `docs/design/paper-engine.md`, `docs/TOOL_CATALOG.md`, `agents/risk.md`); PumpPortal free/metered split and funded-key refusal (live-observed per `.planning/research/STACK.md`, confirmed on the PumpPortal docs page).
- MEDIUM: competitor comparison (Freqtrade docs read; Hummingbot docs read only at index level).
- LOW: PumpPortal migration payload shape, trade-frame shape, bonding-curve account layout over RPC, RPC rate limits for per-token polling, pump.fun historical data availability. Each is marked where it matters.

## Scope and method

This file covers features only, for the milestone that adds the target capabilities to the existing desk. It does not re-research the existing system (vendor engine, root tools, skills, seat prompts). Every requirement family id from `docs/upgrade-plan-desk-v2.md` section 5 is consistent with the feature groups below; feature ids here (DISC, SAFE, SIG, EXEC, LEDG, REPL, RISK, SUPV, RPT, HITL, GOLV, DIFF, AF) are grouping labels for the requirements step, not final requirement ids.

Method:
- Desk requirements taken from the required reading and the design documents they cite.
- External facts checked against primary pages: PumpPortal real-time data docs and FAQ (rate limits, metering, latency statements), Freqtrade bot-usage, backtesting and lookahead-analysis docs, Solana Token Extensions overview and Transfer Hook docs, pump.fun docs root (contains only a terms clickwrap, so no technical bonding-curve specification was available there), Hummingbot docs index.
- Not available: `docs.rugcheck.xyz` failed DNS resolution, so no RugCheck feature is claimed. The Hummingbot paper-trading page returned HTTP 404, so no Hummingbot paper-model claim is made.
- Nothing in the repo was modified. No git, test, gate, or formatter command was run.

## Constraint status legend

Every feature that touches an external source carries one status tag in its Notes column.

| Tag | Meaning |
|---|---|
| `[CLEAR]` | Source is free or observed working; the feature can be built and tested on fixtures. |
| `[DEGRADABLE: reason]` | Source is unreliable or paid. The feature must work when the source is absent, by falling back or by reporting `BLIND`/`n/a`/`data_unavailable`. It must never be silently assumed. |
| `[BLOCKED: reason]` | Requires something the desk does not have by design or by decision. The feature is reported as `data_unavailable` and not built until the blocker is decided. |

Verified constraints applied (binding, from `.planning/research/STACK.md`, observed 2026-10-21):
- PumpPortal per-token trade subscriptions (`subscribeTokenTrade`, `subscribeAccountTrade`) are refused without an API key whose linked wallet holds at least 0.02 SOL. The desk holds no key material, so trade-stream features are `[BLOCKED]` unless the human decides otherwise. `subscribeNewToken` and `subscribeMigration` are free.
- pump.fun `frontend-api.pump.fun` returned HTTP 530 with `error code: 1016` on every path tested. It is `[DEGRADABLE]`.
- Jupiter `lite-api` v1 is superseded by Swap V2. Jupiter is informational only in this desk, so it is `[DEGRADABLE]`.
- x.ai `grok-4` and `grok-4-fast` are retired. LLM-backed scoring is `[DEGRADABLE]` and must use a current model id.

**Consequence the requirements step must see:** the desk's own policy is "BLIND is KILL" (`docs/RISK_POLICY.md` section 2.4). A `BLIND` status on any *required* check kills every token. Public RPC cannot enumerate top holders (`getTokenLargestAccounts` returned HTTP 429), and the pump.fun REST holder endpoint is down. If holder concentration is a required check with no paid RPC provider, the desk will trade nothing. This is the single most important scoping fact for the safety group (see Open Decisions).

## Feature Landscape

### Table Stakes (Users Expect These)

Features an autonomous paper desk must have to produce evidence the 2-4 week run can be judged on. Missing any of these makes the run uninterpretable.

#### Launch discovery (DISC)

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| DISC-1 New-token ingestion via `subscribeNewToken` | Every launch desk starts from the create stream | LOW | `[CLEAR]` Free. Create frame observed live with keys `signature, mint, traderPublicKey, txType, initialBuy, solAmount, bondingCurveKey, vTokensInBondingCurve, vSolInBondingCurve, marketCapSol, name, symbol, uri, is_mayhem_mode, pool`. Ack frames carry only `message` and must be discarded. Dedupe by mint. |
| DISC-2 Single-connection WebSocket client with reconnect and resubscribe | Long autonomous runs; PumpPortal asks for one connection and states disconnects happen | MEDIUM | `[CLEAR]` PumpPortal FAQ: one connection, at most 200 subscribe messages per second, at most 5,000 keys per message, bans of about one hour on violation. Re-send subscriptions after every reconnect. Set `proxy=None` and an explicit `max_queue` (STACK V-7). |
| DISC-3 Migration ingestion via `subscribeMigration` | Graduation ends the curve; the paper engine must close or freeze there (EXEC-6) | LOW | `[CLEAR, shape UNVERIFIED]` Free per PumpPortal docs. Payload shape was not observed in this research. Capture a fixture before EXEC-6 depends on it. Graduation can also be detected from `S >= 85 SOL` (`docs/design/paper-engine.md` section 2.2). |
| DISC-4 Bonding-curve state from create frames; pre-graduation price derivation | Fills and mark-to-market need reserves, not a market price | MEDIUM | `[CLEAR]` Price is `vSolInBondingCurve / vTokensInBondingCurve` (STACK sample: 30 SOL / 1,073,000,000 tokens). Reserve changes after creation are not in the create frame. See SIG-1. |
| DISC-5 Cheap pre-filter before paid or RPC-heavy safety checks | RPC and paid-data budgets are finite; not every launch deserves the full check set | LOW | `[CLEAR]` Filter only on create-frame fields (reserves, initial buy, name/symbol shape). Thresholds `REVIEW`. Analogue: Freqtrade `AgeFilter`, `SpreadFilter`, `VolatilityFilter` pairlist filters (see Competitor analysis). |
| DISC-6 Per-source freshness and health tracking | Missing data must never look like safe data | MEDIUM | `[CLEAR]` `DataStale` after 120 s of WebSocket silence (`docs/design/paper-engine.md` section 6.7); source health appears in reports (RPT-4). |

#### Token safety scoring (SAFE)

Checklist source: `agents/risk.md` lines 35-50 (ten checks, run in order). Thresholds are `safety.thresholds.*` keys, all `REVIEW` (`docs/TOOL_CATALOG.md` section 3).

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| SAFE-1 Mint and freeze authority read | Checklist items 1-2; the first thing every safety desk checks | LOW | `[CLEAR]` One account read per check over RPC. Never trade on cached authority data (constitution clause 6). Output `mint_authority`, `freeze_authority`, `slot`. |
| SAFE-2 Token-2022 extension scan | Extensions can tax, hook, pause, or seize; checklist item 9 asks to document them | MEDIUM | `[CLEAR]` Parse mint extensions. Flag `TransferFeeConfig`, `TransferHook`, `PermanentDelegate`, `NonTransferable`, `DefaultAccountState`, `Pausable`; document the rest. Solana docs confirm all of these exist in `ExtensionType`. A transfer hook runs a CPI on every transfer, so an extension scan is necessary but not sufficient for sell safety (see SAFE-6). |
| SAFE-3 Creator share from the create frame | Creator dumping is a common rug pattern; vendor veto `CREATOR_SHARE_VETO = 0.25` | LOW | `[CLEAR]` `initialBuy` and `traderPublicKey` arrive in the create frame. Reading `initialBuy` as the creator's share is `[INFERENCE]`; verify on a fixture. Creator holdings over time need RPC balance reads or the trade stream (BLOCKED). |
| SAFE-4 Holder concentration (top 10 and top 5, excluding the bonding-curve account) | Checklist item 6; vendor `TOP5_SHARE_VETO = 0.80` | HIGH | `[DEGRADABLE: exact enumeration needs a paid RPC provider; public RPC returns 429 for getTokenLargestAccounts; unofficial frontend-api-v3 top-holders returned HTTP 200 with holder flags but is unofficial]`. The bonding curve holds unsold supply before graduation, so it must be excluded from the concentration base `[INFERENCE]`. Without a source the check is `BLIND`, which kills the token (see Consequence above). |
| SAFE-5 LP status | Checklist item 3 | LOW | `[N/A PRE-GRADUATION]` No LP exists on the curve. LP burn or lock matters only after migration, which the paper engine does not model. Report `n/a` with reason. Reporting it as `BLIND` would kill every token. Scope decision needed in requirements. |
| SAFE-6 Sell-side safety heuristic (honeypot check) | The most expensive loss mode for a buyer; checklist item 5 | HIGH | `[PARTIAL]` The design's heuristic is a sell-side simulation on the paper curve math (`docs/TOOL_CATALOG.md` safety.score_report backend). That is structural only: it cannot see program-level blocks such as a transfer hook, freeze, pause, or blacklist. Label it "structural sell simulation", never "honeypot". Stronger option: RPC `simulateTransaction` of a sell with no signature, built from public keys only. No key material is needed, but feasibility and RPC support are `[UNVERIFIED]`, LOW confidence. |
| SAFE-7 Bundler and same-block cluster detection | Checklist item 7; launch bundles are the main sniper-cartel pattern | HIGH | `[BLOCKED for trade-derived signals: needs per-trade slot and signer data; trade stream requires a funded key]` `[DEGRADABLE for flags: frontend-api-v3 top-holder entries carry isBundler, isSniper, isDev; unofficial and LOW stability]`. |
| SAFE-8 Deployer wallet history | Checklist item 8 | HIGH | `[DEGRADABLE: needs signature-history walks on the creator wallet; paid RPC; WHALE grant only (R35)]`. |
| SAFE-9 Metadata sanity and confusable-symbol check | Ticker impersonation is a standard launch scam | LOW | `[CLEAR]` Local checks on name, symbol, and uri. Match against tickers already seen this session. A confusable match is `BLIND` by RISK_POLICY section 2.4. External ticker lists are not assumed. |
| SAFE-10 Scored, explained verdict (never a bare boolean) | Vetoes must be auditable by the human | MEDIUM | `[CLEAR]` Per check: value, threshold, status in `pass, warn, fail, blind`. Score 0-100. Verdict `CLEAR, CONDITIONAL, KILL` with `kill_below_score = 40` and `conditional_below_score = 70` (REVIEW). Recommendation only; RISK issues the verdict. |
| SAFE-11 Fail-closed on BLIND | Constitutional: missing data is KILL | LOW | `[CLEAR, policy]` Must be paired with an explicit list of which checks are required. See Open Decisions. |

#### Momentum and signal generation (SIG)

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| SIG-1 Price ticks by polling the bonding-curve account (`bondingCurveKey` from the create frame) | Momentum and mark-to-market need reserve updates after creation; the trade stream that would supply them is blocked | HIGH | `[CLEAR path, LOW confidence on layout]` Decode the curve account over RPC at a fixed cadence (MTM 60 s; watcher poll 15 s). Cost is RPC budget per tracked token. Account layout decoding and per-token polling limits on the chosen RPC are not verified here; a probe is required before requirements freeze. This is the only price-tick source that does not depend on BLOCKED or DEGRADABLE sources. |
| SIG-2 Rule-based momentum features from reserves: reserve velocity, return over windows, time since launch, curve fill percentage | Standard momentum inputs, computable without trades | MEDIUM | `[CLEAR once SIG-1 works]` Reserve velocity substitutes for buy/sell imbalance. |
| SIG-3 Trade-flow features: volume, buy:sell ratio, unique buyers, whale flow | The usual momentum inputs in any memecoin screener | HIGH | `[BLOCKED: subscribeTokenTrade refused without a funded 0.02 SOL key, observed live]`. Mark `data_unavailable`. Never fall back to a guess (STACK "Stack Patterns by Variant"). |
| SIG-4 Component-aware confidence score | A missing feature must not look like a weak feature | MEDIUM | `[CLEAR]` Vendor `compute_scores` sets missing components to 0.0 (`docs/design/paper-engine.md` section 6.7 row for LLM outage). The desk should drop missing components from the denominator and cap confidence by coverage. |
| SIG-5 LLM-assisted scoring with rule-based fallback | Vendor design; qualitative read of safety and social context | MEDIUM | `[DEGRADABLE: x.ai grok-4 and grok-4-fast retired; use a current id; fallback to rules when down]`. `signal.require_llm = false` in paper; `true` makes buys observe-only without the LLM. |
| SIG-6 Signal record with inputs, component scores, and decision reason | Replay and attribution need the exact inputs that produced each decision | LOW | `[CLEAR]` Ledger `signal` event (kind literal `signal`, R40). |

#### Realistic paper execution (EXEC)

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| EXEC-1 Bonding-curve constant-product fill with price impact, integer math | Fill basis without an order book; the Jupiter quote is not the fill price (R38) | MEDIUM | `[CLEAR]` `buy_out`, `sell_out`, `impact_buy`, `impact_sell` from `docs/design/paper-engine.md` section 2.2. Lamports and token base units as integers; Decimal only for ratios. |
| EXEC-2 Fees: venue fee (100 bps REVIEW), base fee (5,000 lamports), priority fee | Paper bots that ignore fees overstate PnL | LOW | `[CLEAR]` `getRecentPrioritizationFees` observed live HTTP 200. The venue fee and compute-unit default are `REVIEW` values. |
| EXEC-3 Confirmation-time re-quote and slippage check on the executed size | Price moves during latency; partial fills change the threshold | MEDIUM | `[CLEAR]` Latency is lognormal and seeded (`docs/design/paper-engine.md` section 2.5). Threshold recomputed on executed size (R38). |
| EXEC-4 Seeded dropped-transaction outcome with no retry | Single-send rule (constitution clause 3): an unknown result must not be retried | MEDIUM | `[CLEAR]` `tx_dropped` at p = 0.02 (REVIEW). Idempotency on `(ticket_id, side, decision_id)`. |
| EXEC-5 Liquidity floor and partial fills | With 0.2 SOL orders on a 10 SOL equity, thin curves must be rejected or partially filled | MEDIUM | `[CLEAR]` Full fill at size <= S/50; partial in (S/50, S/10]; reject above S/10 (REVIEW). Expect many `below_liquidity_floor` rejections on young curves; RPT-3 makes that visible. |
| EXEC-6 Graduation handling: reject buys on graduated tokens and force-close open positions at the last curve price | Otherwise paper results silently stop at migration | MEDIUM | `[CLEAR once DISC-3 fixture or the S >= 85 SOL check exists]`. Documented limitation: paper results stop at graduation (`docs/design/paper-engine.md` section 11.5). |
| EXEC-7 Mark-to-market at liquidation value on a 60 s cadence | Spot price overstates the equity of a curve position | MEDIUM | `[CLEAR once SIG-1 works]` `docs/design/paper-engine.md` section 2.7. |
| EXEC-8 Blind-position protection (`last_good` price, `blind_flatten` at 300 s) | Open positions must never be left unprotected when data dies | MEDIUM | `[CLEAR]` RISK_POLICY section 2.4; PAPER-005. |
| EXEC-9 Decision-data age gate | Decisions on stale ticks are the paper analogue of stale-quote fills. The design models confirmation latency but not decision-data age | LOW | `[CLEAR]` PumpPortal FAQ says the data websocket is processed-level and typically under 100 ms behind gRPC from New York. Treat the remaining gap as an explicit assumption and reject decisions whose data age exceeds a REVIEW bound. |
| EXEC-10 Jupiter quote as an informational route and price cross-check | Operator sanity check and tool-catalogue parity | LOW | `[DEGRADABLE: lite-api v1 superseded by Swap V2; Swap V2 order endpoint answered keyless in probe, free key tier is 1 RPS]`. Informational only. The desk must run with it absent. |

#### Ledger and PnL attribution (LEDG)

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| LEDG-1 Append-only, hash-chained event ledger with idempotency keys | Audit trail, restart, and the honesty claim in the core value | HIGH | `[CLEAR]` SQLite WAL; canonical JSON hash chain (R28); snapshot plus tail replay on restart; tampering yields `INCONSISTENT` and `HaltSet(ledger_inconsistent)`. A duplicate idempotency key is refused. |
| LEDG-2 Realized and unrealized PnL with fees split out | Every report and gate depends on it | MEDIUM | `[CLEAR]` Gross, fees (venue, base, priority), and net, in integer lamports. Day attribution by fill timestamp (PAPER-001). |
| LEDG-3 Equity curve, peak, drawdown, and start-of-day equity | Drawdown and daily-loss halts require them | MEDIUM | `[CLEAR]` Built from 60 s mark-to-market points (`ledger.mtm_interval_s`). |
| LEDG-4 Source tagging (`paper`, `replay`, `manual`) with gate statistics counted on `paper` only | Replay results must never be mistaken for paper evidence | LOW | `[CLEAR]` R21, R41. Paper window starts at the first `source=paper` event. |
| LEDG-5 Atomic markdown and JSONL export | Reports and vendor-shaped tooling read files | LOW | `[CLEAR]` tmp file plus `os.replace` (R26). Derived, never read back. |

#### Replay and backtest (REPL)

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| REPL-1 Deterministic replay: virtual clock, one seeded RNG, fixture timestamps; two runs give identical hashes | Without determinism, backtests are not evidence | HIGH | `[CLEAR]` PAPER-004 and AUTO-006. A different seed must differ. A hole of 180 s must trip `DataStale`. |
| REPL-2 Replay with recorded LLM responses keyed by canonical request hash; a missing record fails the run | Keeps LLM stochasticity out of replay results | MEDIUM | `[CLEAR]` `outcome` in `{ok, timeout, error}` with virtual latency (R27). |
| REPL-3 Recording live feeds into datasets (`run --record <dataset> --duration <s>`) | No historical pump.fun trade data is available to this desk; recording is the only replay data source | MEDIUM | `[DEGRADABLE: records only what the connected feeds deliver; blocked trade data cannot be recorded]`. The PumpPortal FAQ has a question "Do you provide historical Pump.fun token data?"; its answer was not read in this research. Treat historical data as unavailable (LOW) until checked. |
| REPL-4 Fault-injection replay: WebSocket loss, RPC down, LLM 429 or timeout, unwritable ledger | The autonomy claim needs proof for each degraded mode | MEDIUM | `[CLEAR]` AUTO-008 `tests/degradation/`. |

#### Risk controls (RISK)

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| RISK-1 Per-trade (2%), per-token (5%), open-position (3) and daily-trade (20) caps | Standard position limits | LOW | `[CLEAR]` All REVIEW (RISK_POLICY section 2.2). Oversize orders are capped and the decision says so. |
| RISK-2 Daily-loss halt (5% of start-of-day equity, floor) and drawdown halt (15% of peak) with explicit human clear | Constitution clause 5; stops autonomous bleed | MEDIUM | `[CLEAR]` The vendor auto-clears at UTC rollover (`risk.py:106-117`). The desk does not (D9). Clear only via `pumpgrok state halt --clear --by <human>`. |
| RISK-3 Breakers `DataStale`, `LossVelocity` (2% over 15 min), `ExecErrors`, with cooldown and one half-open probe | Autonomous runs need automatic brakes | HIGH | `[CLEAR]` Reconstructed from ledger events after restart (`docs/design/paper-engine.md` section 9). |
| RISK-4 Kill switch: env at start, file `var/KILLSWITCH`, alert-channel command; checked every 5 s; zero buys after it is set; optional flatten | The operator's emergency stop must work with no code change | MEDIUM | `[CLEAR]` Clear is CLI-only with a recorded approval. |
| RISK-5 Re-check of every limit and breaker at CONFIRMING | Conditions change inside the latency window | MEDIUM | `[CLEAR]` In-flight orders rejected with `kill_switch`, `halted`, or `breaker_open`. |
| RISK-6 RISK veto is absolute for the token session | Constitution clause 4 | LOW | `[CLEAR]` `KILL` is terminal for `(mint, session)` for every seat. |
| RISK-7 Exit rules: stop-loss 30%, take-profit 120%, trailing stop 35% (only above entry), max hold 3600 s | Exits define realised PnL; the paper run needs them to close positions | MEDIUM | `[CLEAR]` Vendor parity (`docs/design/paper-engine.md` section 1, row "Exit rules"). Each rule needs a per-ticket `exit_rule` approval under `manual-ticket` (HITL-2). |

#### Supervision and health (SUPV)

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| SUPV-1 Asyncio supervisor: one task per seat, cycle timeouts, roster-order scheduling in a 1 s tick | The autonomous run is a long-lived process | HIGH | `[CLEAR]` A timed-out cycle counts as a crash. `asyncio.timeout` is never called directly (static test). |
| SUPV-2 Restart with backoff (1, 2, 4, 8, 16 s plus jitter), budget of 5 per hour, then latch observe-only with an escalation | Crash containment without a crash loop | MEDIUM | `[CLEAR]` Other seats keep running. `pumpgrok state resume --seat <seat> --by human:<name>` clears the latch. |
| SUPV-3 Heartbeats, stale detection, `/healthz`, `/readyz`, atomic `var/health.json` every 10 s | Compose and Hermes need liveness | MEDIUM | `[CLEAR]` Stale for 3 cadences degrades health and emits one edge-triggered escalation. |
| SUPV-4 Graceful shutdown: drain within 30 s, snapshot, flush export, exit 0 | Restarts must not corrupt the ledger | LOW | `[CLEAR]` A second signal does not force exit. |
| SUPV-5 Structured JSON logs, correlation IDs, secret redaction, Prometheus metrics | Debuggable autonomy; redaction is a security requirement | MEDIUM | `[CLEAR]` Metric list in OBS-003. |
| SUPV-6 Degraded modes: LLM to rules, RPC failover, WebSocket reconnect with backoff, ledger-unwritable buffer | Several sources are unreliable by observation | MEDIUM | `[CLEAR]` `docs/design/paper-engine.md` section 6.7. Each mode has a fault-injection test (REPL-4). |

#### Reporting (RPT)

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| RPT-1 Daily report at 00:05Z | Human review of a 2-4 week autonomous run | MEDIUM | `[CLEAR]` Sections of `docs/design/paper-engine.md` section 8.3: summary, trades, open positions, rejected signals, safety outcomes, risk events, bot health, data freshness. Pure renderer, ASCII only. |
| RPT-2 Weekly report at Monday 00:15Z with the nine live-gate lines marked OK or unmet | The only admissible evidence before any live discussion (RISK_POLICY section 3.2) | MEDIUM | `[CLEAR]` Computed on `source=paper` events only. |
| RPT-3 Rejected signals by R34 reason | Shows what sizing and the liquidity floor do; without it the paper results look cleaner than they are | LOW | `[CLEAR]` |
| RPT-4 Data freshness: `DataStale` open time and per-source age | Honest about blind periods | LOW | `[CLEAR]` |
| RPT-5 "Unverified" section: days computed from `last_good` prices, `ledger_inconsistent` days, unexplained `blind_flatten` closes | Honest reporting of what the numbers do not cover | LOW | `[CLEAR]` Empty section is a precondition for the weekly gate. |

#### Human-in-the-loop (HITL)

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| HITL-1 Ticket `SOL-YYYYMMDD-NNN` and exact-phrase approval under `manual-ticket` | Constitution clause 2: analysis is not approval | MEDIUM | `[CLEAR]` Token-for-token match; mismatch yields `OrderRejected reason=approval_mismatch`. Ticket regex byte-equal to `tools/desk_state.py:32`. |
| HITL-2 Per-exit-rule approval under `manual-ticket` | Exits are autonomous only after the human approves the rule per ticket | LOW | `[CLEAR]` `ApprovalRecorded(kind=exit_rule)`. |
| HITL-3 Explicit autonomy-level switch (`manual-ticket` to `autonomous-paper`) recorded with its approval | Autonomous paper must be a deliberate human act and must be visible in the window statistics | LOW | `[CLEAR]` `ConfigChanged` plus `ApprovalRecorded(kind=autonomous_paper)`. |
| HITL-4 Operator escalation: stdout and file always on; Telegram and webhook only to an allowlist | The human must see alerts without any outbound social surface | MEDIUM | `[CLEAR]` Escalation kinds include `bot_restart_exhausted`, `heartbeat_stale`, `persistence_down`, `clock_skew`, `ledger_inconsistent` (R40). |
| HITL-5 Inbound alert-channel commands limited to `KILL [FLATTEN] <reason>` and `STATUS`; anything else is logged and ignored | Only safe commands may reach the desk from chat | LOW | `[CLEAR]` Unknown text never acts (`docs/design/paper-engine.md` section 9 unverified item 8). |

#### Go-live gating (GOLV)

| Feature | Why Expected | Complexity | Notes |
|---|---|---|---|
| GOLV-1 Nine-precondition live gate that refuses start with exit code 3 and lists every unmet line | Live must be unreachable by accident | MEDIUM | `[CLEAR]` Precondition 8 (a registered live adapter) is always unmet in this milestone. This is intended. |
| GOLV-2 Paper-window statistics: 14 days minimum, `closed_trades >= 50`, `profit_factor >= 1.2`, `max_drawdown <= 0.15` | Gate evidence must be defined before the run starts | LOW | `[CLEAR]` All REVIEW. They gate nothing in paper and are not a return claim (RISK_POLICY section 3.2). |
| GOLV-3 Any limit change during the window restarts the window | Prevents tune-then-claim | LOW | `[CLEAR]` `ConfigChanged(keys_changed=[...])` records what changed. |
| GOLV-4 HMAC-signed live confirmation bound to the config hash, with an operator secret no seat can read | Human sign-off that cannot be forged by a seat | MEDIUM | `[CLEAR]` ed25519 signatures are deferred. |
| GOLV-5 Notional cap `0 < live.notional_cap_sol <= 1.0` in every overlay | Bounds any future live mistake | LOW | `[CLEAR]` Overlays ship `live.enabled = false`. |

### Differentiators (Competitive Advantage)

Not expected by a generic paper bot, but they are where this desk's value comes from. Each one supports the core value: "honest, replayable reports; no code path can move real funds."

| Feature | Value Proposition | Complexity | Notes |
|---|---|---|---|
| DIFF-1 Explained, fail-closed safety verdicts (SAFE-10 plus SAFE-11) | Every veto shows value, threshold, and reason; missing data is never a pass | MEDIUM | `[CLEAR]` Most paper bots return a single pass/fail or a bare score. |
| DIFF-2 Curve-faithful paper fills with confirmation re-quote, seeded drops, and no retry (EXEC-1 to EXEC-4) | Most paper bots fill at mid price with no impact, latency, or drops; that overstates results | HIGH | `[CLEAR]` The gap this desk closes against typical paper trading. |
| DIFF-3 Calibration of confidence against realised outcomes, reported by confidence bin | Tells the human whether the confidence number means anything | MEDIUM | `[CLEAR]` Needs enough closed trades; reported as n/a below a REVIEW sample size. Depends on SIG-4. |
| DIFF-4 PnL attribution by exit reason, verdict, confidence bin, and day | Shows where edge or loss came from, not just the total | MEDIUM | `[CLEAR]` Built on LEDG-2 and LEDG-5 data. |
| DIFF-5 Lookahead and leakage check on replay: perturb inputs and confirm decisions do not move (Freqtrade `lookahead-analysis` analogue) | Catches a feature that peeks at later reserves or later holder data | HIGH | `[CLEAR]` Must use the desk's own replay, not Freqtrade code. Note Freqtrade's own caveat: a check only verifies the signals it triggered. |
| DIFF-6 Recorded LLM responses and deterministic replay together (REPL-1 plus REPL-2) | Replay results stay identical across runs even with an LLM in the loop | HIGH | `[CLEAR]` Mostly the same mechanism as REPL-2; listed here because few paper tools do it. |
| DIFF-7 Per-seat least-privilege tool grants with 403 across seats | A compromised or confused seat cannot place orders it was not granted | HIGH | `[CLEAR]` TOOL-009 and TOOL-010. Architecture-level, not a UI feature. |
| DIFF-8 Reserve-polling price ticks as the replacement for the blocked trade stream (SIG-1) | Keeps MTM and momentum alive without a funded key or a metered feed | HIGH | `[CLEAR path, LOW confidence on layout]` Turns a blocker into a degradable feature. Needs a probe. |
| DIFF-9 Honest "Unverified" reporting plus a gate that refuses replay data (RPT-5, LEDG-4, GOLV-2) | The report says what it does not cover; a replay run cannot satisfy the live gate | MEDIUM | `[CLEAR]` |

### Anti-Features (Commonly Requested, Often Problematic)

Features the desk must NOT build. Mandated list first (manipulation and adjacent conduct, as required by the brief), then other items found in the sources or the design that should be refused explicitly. All of these are prohibited or out of scope under `docs/RISK_POLICY.md` section 4.1 or `docs/upgrade-plan-desk-v2.md` section 5.11 unless marked otherwise.

| Feature | Why Requested | Why Problematic | Alternative |
|---|---|---|---|
| AF-1 Coordinated buying: buying, or signalling intent to buy, in concert with other wallets; timing entries to another party's promotion | "Follow the smart money", group entries, copying a campaign | Manipulation of the price discovery the desk is trying to observe. Prohibited (D7, RISK_POLICY 4.1). The desk's own bundler and cluster checks exist to detect this pattern in others | One independent ticket per decision. Cluster and bundler evidence is a negative input to RISK, never a reason to join |
| AF-2 Wash trading: trading with oneself or an affiliate, on-curve or on any DEX | Making activity look real; seeding holder counts | Fake volume; prohibited. It would also corrupt the desk's own volume and holder features | None. Paper only. No code path builds a self-matched order; the desk holds no keys |
| AF-3 Volume generation: any order whose purpose is volume, candles, holder count, or "momentum" rather than its own position under an approved ticket | "Warm up" a curve to pass the liquidity floor; make a signal fire | Prohibited (RISK_POLICY 4.1). Self-impact also invalidates the paper fills and the signal being tested | Size to the floor (EXEC-5) and reject thin curves; RPT-3 shows the rejections |
| AF-4 Shilling and social posting: producing or relaying promotional content about a held or evaluated token; posting, replying, liking, following, DMing, or scheduling content on X, Telegram, Discord, or pump.fun comments | Audience growth; promoting a position; "social proof" for the signal | Prohibited (D7, RISK_POLICY 4.1, 4.3). Creates undisclosed promotion and conflicts with human approval. `bot-07-shill` is detection only | bot-07-shill classifies social velocity read-only (GET only, TOOL-009). `notify.alert` goes only to the operator allowlist |
| AF-5 Spoofing and layering: orders with no intent to fill; several orders at different sizes or times to misstate interest | Book-pressure signals; "fake interest" in a bullish read | Prohibited (RISK_POLICY 4.1). The curve has no order book, so any resting-order abstraction would be a new manipulation surface | None. The paper adapter has no resting orders; a live adapter must never add them. The quote tool returns no order intent |
| AF-6 Front-running desk-adjacent flow: trading ahead of a ticket, a human approval, another seat's pending order, an alert message, or the operator's other wallets | "Free edge" from knowing the desk's own queue | Prohibited (RISK_POLICY 4.1). It also contaminates paper results because the desk's own pending orders move the same curve | Approvals and seat orders are consumed atomically in the ledger (R23). A seat may not trade on another seat's pending ticket |
| AF-7 Auto-retry of a dropped, timed-out, or unknown send | "Make the fill happen" | Duplicates exposure; violates the single-send rule (clause 3) | Report `UNKNOWN RESULT - reconcile by signature`; wait for a fresh human approval (EXEC-4) |
| AF-8 Treating missing data as a pass or as a zero | Keeps the desk trading when a source is down or a metric does not apply | False safety (LP check reported as pass pre-graduation) or false weakness (vendor sets missing confidence components to 0.0). Violates fail-closed | Explicit `blind`, `n/a` with reason, or `data_unavailable`; confidence capped by coverage (SIG-4) |
| AF-9 Hyperparameter tuning or hyperopt against the live paper window | "Make the gate numbers pass" | Overfits and games the gate; GOLV-3 exists specifically because of this. Freqtrade ships hyperopt, which this desk should not copy for the live window | Tune only on replay datasets with recorded LLM responses; any change restarts the window |
| AF-10 Backtests on unrecorded or purchased "historical" pump.fun data presented as evidence | Longer backtest history looks more convincing | Unverifiable provenance and lookahead risk; historical availability was not confirmed (REPL-3) | Replay only from datasets the desk recorded itself, tagged `source=replay`, which never counts for the gate |
| AF-11 Using the Jupiter quote or pump.fun REST as the fill price | Familiar market prices; easy integration | R38 forbids it. pump.fun REST returned HTTP 530; lite-api v1 is superseded | Bonding-curve fill from reserves (EXEC-1); Jupiter stays informational (EXEC-10) |
| AF-12 Non-persistent dry run: paper trades that are not written to the ledger by default | Freqtrade's dry-run stores nothing unless `--db-url` is given (bot-usage docs) | No audit trail; the 2-4 week evidence depends on it | The ledger is always written; there is no unpersisted paper mode |
| AF-13 Post-graduation AMM (CPMM) modelling | Paper results would look complete past migration | No post-graduation reserve source is integrated (D8). Modelling it would invent PnL | Stop at graduation with explicit `graduated` closes (EXEC-6). Listed as v2 (section 5.11) |
| AF-14 Copy-trading named wallets (deployers, whales, sniper groups) | Easy signal: "buy what they buy" | Follows insider and bundle flow the desk is required to classify as manipulative; front-running adjacent. Desk judgement `[INFERENCE on policy fit]` | Wallet flow is a feature input to the whale seat, read-only, and is BLOCKED for trade data anyway (SIG-3) |
| AF-15 Any live send path, Jito bundles or tips, or a trading API that submits transactions | Real fills; faster execution (PumpPortal Lightning API) | Out of scope: live adapters are disabled stubs, no key material exists (D4, R3, R21 precondition 8) | Paper only. GOLIVE ships disabled (section 5.10) |
| AF-16 Web dashboard or profit-showing UI | Stakeholder visibility | Out of scope (spec line 160); return claims are forbidden (constitution clause 8) | Text and Markdown reports only (RPT-1 to RPT-5) |
| AF-17 Auto-clearing the daily-loss halt at UTC rollover (vendor behaviour) | Restores trading without a human | Contradicts constitution clause 5 and D9 | Explicit `pumpgrok state halt --clear` with a recorded approval (RISK-2). The vendor characterization test is marked "intentionally not ported" |
| AF-18 Depending on undocumented endpoints (pump.fun frontend-api v1, unofficial v3 flags) as primary sources | Richer data with no paid key | Observed unreliable (HTTP 530) or unofficial and unstable | Keep them as `[DEGRADABLE]` fallbacks behind a circuit breaker; never as the only source for a required check |

## Feature Dependencies

Read as "A requires B": B must be in the same phase or an earlier one. Derived from the design documents; the phase ordering itself belongs to the roadmapper.

```
Foundation: LEDG-1 ledger, FOUND clock, rng, config, SUPV-1 supervisor
    requires nothing outside the foundation

DISC-1 create ingest           requires: DISC-2 WebSocket client
DISC-3 migration ingest        requires: DISC-2
DISC-4 curve state             requires: DISC-1
DISC-5 pre-filter              requires: DISC-4
DISC-6 source health           requires: DISC-2, SUPV-3

SIG-1 curve polling            requires: DISC-4 (bondingCurveKey), RPC budget
SIG-2 reserve momentum         requires: SIG-1
SIG-3 trade-flow features      requires: trade stream  [BLOCKED]
SIG-4 confidence               requires: SIG-1 or SIG-2, SAFE-10
SIG-5 LLM scoring              requires: REPL-2 recording; falls back to SIG-2
SIG-6 signal record            requires: LEDG-1

SAFE-1, SAFE-2, SAFE-9         require: RPC account reads or local data
SAFE-3                         requires: DISC-1 (initialBuy, traderPublicKey)
SAFE-4                         requires: paid RPC provider OR unofficial v3 source  [DEGRADABLE]
SAFE-7                         requires: trade stream [BLOCKED] OR v3 flags [DEGRADABLE]
SAFE-8                         requires: paid RPC provider  [DEGRADABLE]
SAFE-6                         requires: EXEC-1 curve math (structural only)
SAFE-10 verdict                requires: SAFE-1..9 (any subset) plus the required-check list

EXEC-1 curve fill              requires: DISC-4, SIG-1 (confirmation re-read)
EXEC-3 re-quote                requires: EXEC-1, DISC-6 (data age)
EXEC-4 drop outcome            requires: EXEC-1, LEDG-1 (idempotency)
EXEC-5 floor and partial       requires: EXEC-1
EXEC-6 graduation              requires: DISC-3 or S >= 85 SOL check, EXEC-1
EXEC-7 mark-to-market          requires: SIG-1, LEDG-1
EXEC-8 blind protection        requires: EXEC-7, DISC-6
EXEC-10 Jupiter informational  requires: nothing; optional  [DEGRADABLE]

LEDG-2 PnL, LEDG-3 drawdown    require: LEDG-1, EXEC-7
LEDG-4 source tags             require: LEDG-1
DIFF-4 attribution             requires: LEDG-2, LEDG-3, SAFE-10 verdict stored, SIG-4

RISK-1 caps                    requires: LEDG-3 (equity), EXEC-7
RISK-2 daily and drawdown      requires: LEDG-3
RISK-3 breakers                requires: LEDG-1 (reconstruction), DISC-6 (DataStale), EXEC-3
RISK-4 kill switch             requires: SUPV-1 cycle; HITL-5 channel optional
RISK-5 CONFIRMING re-check     requires: RISK-1..4, EXEC-3
RISK-7 exit rules              requires: EXEC-7, HITL-2 (manual-ticket)

HITL-1 ticket and approval     requires: EXEC-1, LEDG-1
HITL-3 autonomy switch         requires: LEDG-1
HITL-4 escalation              requires: SUPV-2 escalation events, HITL channel
HITL-5 inbound commands        requires: HITL-4 channel; RISK-4

SUPV-2 restart budget          requires: SUPV-1
SUPV-3 health                  requires: SUPV-1
SUPV-6 degraded modes          requires: SUPV-1, DISC-6, RPC failover, REPL-2

REPL-1 determinism             requires: LEDG-1, FOUND clock and rng
REPL-2 LLM recording           requires: SIG-5 call path
REPL-3 recording live feeds    requires: the feeds it records; blocked feeds cannot be recorded
REPL-4 fault injection         requires: REPL-1, SUPV-6
DIFF-5 lookahead check         requires: REPL-1, SIG-2 feature set
DIFF-6 LLM plus determinism    requires: REPL-1, REPL-2

RPT-1 daily                    requires: LEDG-2, LEDG-3, RISK events, SUPV-3
RPT-2 weekly gate lines        requires: GOLV-2, LEDG-4, HITL-3
RPT-3 rejected signals         requires: EXEC-5, SAFE-10 verdict
RPT-5 unverified section       requires: LEDG-1 inconsistency checks, EXEC-8

GOLV-1 live gate               requires: LEDG-4, RPT-2, HITL-1..3, GOLV-4, GOLV-5; precondition 8 unmet by design
GOLV-3 window restart          requires: LEDG-1 ConfigChanged
```

### Dependency Notes

- **SIG-1 is the hinge.** MTM (EXEC-7), momentum (SIG-2), blind protection (EXEC-8), and the graduation check depend on it. It is the only price-tick path that is neither BLOCKED nor DEGRADABLE on paper. It needs a probe before requirements freeze because the account layout and the per-token RPC cost are unverified.
- **SAFE-4 and SAFE-8 depend on a paid RPC provider.** Public RPC returns 429 for `getTokenLargestAccounts`. This is a cost decision, not an engineering one.
- **SAFE-6 is structural only.** It cannot prove sellability. Any requirement that says "honeypot-free" must be rewritten.
- **SIG-3 and SAFE-7 (trade parts) conflict with "no key material"** unless the human approves a funded PumpPortal key. The orchestrator raised this already (STACK Risks item 2). Default: not built.
- **DIFF-3 and DIFF-4 need closed trades.** They are reported as n/a below a sample-size threshold, not hidden.
- **GOLV-3 conflicts with AF-9.** Tuning on the live window restarts it; hyperopt on the live window would be gate gaming.
- **EXEC-6 depends on a fixture for DISC-3.** Its shape is unverified; graduation can fall back to the `S >= 85 SOL` check.

### Conflicts

- **Required holder-concentration check vs. public RPC and fail-closed policy:** requiring SAFE-4 without a paid provider means every token is KILL. Resolve in requirements (see Open Decisions).
- **LP status as a required check vs. pre-graduation scope:** SAFE-5 cannot be satisfied on the curve. Must be `n/a`, not `BLIND`.
- **"Honeypot" label vs. structural simulation:** naming the check honeypot overclaims. Use the structural name.
- **Silent zero for missing confidence components (vendor) vs. calibration (DIFF-3):** a zero-filled score makes calibration meaningless. Drop missing components and cap confidence instead.

## Constraint Impact Summary

| Source | Status | Features affected | Consequence if absent |
|---|---|---|---|
| PumpPortal `subscribeNewToken` | `[CLEAR]` free | DISC-1, DISC-4, SAFE-3, SIG-1 start | No discovery. No fallback. The desk does nothing; this is the entry point. |
| PumpPortal `subscribeMigration` | `[CLEAR]` free, shape UNVERIFIED | DISC-3, EXEC-6 | Graduation falls back to `S >= 85 SOL` from reserves |
| PumpPortal `subscribeTokenTrade` and `subscribeAccountTrade` | `[BLOCKED]` funded key (0.02 SOL) refused without it; desk holds no key material | SIG-3, SAFE-7 trade parts, whale flow | Reported `data_unavailable`. Never guessed. |
| pump.fun `frontend-api.pump.fun` | `[DEGRADABLE]` HTTP 530 / 1016 observed on every path | Holder snapshot, price cross-check, trades | Use RPC curve polling (SIG-1) and create frames |
| pump.fun `frontend-api-v3` top-holders | `[DEGRADABLE]` HTTP 200 observed; unofficial; v3 trades endpoint returned 400 | SAFE-4 fallback, SAFE-7 bundler flags | `BLIND` on those checks; token KILL if required |
| Solana public RPC | `[CLEAR]` for account reads; `[DEGRADABLE]` for `getTokenLargestAccounts` (429) and signature walks | SAFE-1, SAFE-2, SAFE-4, SAFE-8, SIG-1 | Paid provider needed for SAFE-4 and SAFE-8. Failover list per `rpc.endpoints[]`. |
| Solana `getRecentPrioritizationFees` | `[CLEAR]` HTTP 200 observed | EXEC-2 | Priority fee unknown; use configured default with a flag |
| Jupiter lite-api v1 and Swap V2 | `[DEGRADABLE]` v1 superseded; V2 order keyless in probe, free key tier 1 RPS | EXEC-10 only | Informational feature absent; desk unaffected |
| x.ai Grok | `[DEGRADABLE]` retired ids; current names must come from the live model list | SIG-5, REPL-2 recording | Rule-based scoring; observe-only buys if `signal.require_llm` |

## Open Decisions for Requirements

These cannot be resolved by research. Each needs a human or orchestrator decision before requirements are frozen.

1. **Paid Solana RPC provider.** Is it approved (cost, key handled through env only)? Without it SAFE-4 and SAFE-8 are unavailable and holder concentration can only be `BLIND`.
2. **Which safety checks are REQUIRED (BLIND equals KILL) and which are advisory.** Proposal `[INFERENCE, for human decision]`: required = SAFE-1, SAFE-2, SAFE-9, SAFE-11; SAFE-4 required only if decision 1 is yes; advisory = SAFE-3, SAFE-5 (as `n/a`), SAFE-6, SAFE-7, SAFE-8.
3. **Funded PumpPortal key.** Is it an allowed exception to "no key material"? Default in `.planning/PROJECT.md`: no. If yes, SIG-3 and the trade parts of SAFE-7 move from BLOCKED to CLEAR, with the 0.01 SOL per 10,000 metered events budgeted.
4. **SIG-1 cadence and RPC budget.** Poll interval per tracked token and the maximum number of tracked tokens. Requires the probe in SIG-1.
5. **SAFE-6 depth.** Keep structural sell simulation only (label it so), or require an RPC `simulateTransaction` sell check (needs a probe; feasibility unverified).
6. **Historical data policy.** Confirm that replay uses only self-recorded datasets (AF-10). Read the PumpPortal FAQ answer on historical data before deciding whether any external history is ever considered.
7. **Data-age bound for EXEC-9.** Pick the REVIEW value.

## MVP Definition

This milestone's "MVP" is the minimum set that lets the 2-4 week autonomous paper run produce interpretable, replayable evidence. Items are added only where they are required by the run.

### Launch With (v1 of this milestone)

- [ ] DISC-1, DISC-2, DISC-4, DISC-5, DISC-6: discovery and source health. Essential: nothing else runs without them.
- [ ] SAFE-1, SAFE-2, SAFE-3, SAFE-9, SAFE-10, SAFE-11: the cheap, clearly-sourced checks plus the explained verdict. Essential for fail-closed behaviour.
- [ ] SAFE-4 only if decision 1 is yes; otherwise its absence is recorded as `BLIND` and the required list in decision 2 governs.
- [ ] SIG-1, SIG-2, SIG-4, SIG-6: price ticks by polling, reserve momentum, component-aware confidence, signal record. Essential: MTM and momentum depend on SIG-1.
- [ ] EXEC-1 to EXEC-9: curve-faithful fills, fees, re-quote, drops, floor and partials, graduation, MTM, blind protection, data-age gate. This is the realism the paper run is for.
- [ ] LEDG-1 to LEDG-4: ledger, PnL, equity and drawdown, source tags. Essential for every report and gate.
- [ ] REPL-1, REPL-2, REPL-3: deterministic replay, LLM recording, live-feed recording. Essential to make results reproducible.
- [ ] RISK-1 to RISK-7: caps, halts, breakers, kill switch, CONFIRMING re-check, absolute veto, exit rules. Essential for autonomy.
- [ ] SUPV-1 to SUPV-4, SUPV-6: supervisor, restarts, health, shutdown, degraded modes. Essential for a 2-4 week unattended run. SUPV-5 logging and redaction are required too.
- [ ] RPT-1 to RPT-5: daily and weekly reports with the unverified section. Essential for the human review.
- [ ] HITL-1 to HITL-5: ticket and exact-phrase approval, exit-rule approval, autonomy switch, escalation, safe inbound commands.
- [ ] GOLV-1, GOLV-2, GOLV-3, GOLV-5: the live gate that refuses to start, its statistics, window restart, cap. Disabled.

### Add After Validation (v1.x)

- [ ] SAFE-6 with the RPC `simulateTransaction` sell check: add once the probe shows it works. Trigger: the structural check shows false passes in the paper run.
- [ ] SAFE-7 bundler flags and SAFE-8 deployer history: add once a paid provider exists. Trigger: holder data is available and the bundler pattern shows in the replay.
- [ ] SIG-5 LLM scoring: add when a current x.ai model id is confirmed. Trigger: rule-based scoring is working and the desk needs the qualitative read.
- [ ] DIFF-3 calibration, DIFF-4 attribution, LEDG-5 export: add once there are enough closed trades to make them non-n/a. Trigger: first weekly report.
- [ ] DIFF-5 lookahead check, REPL-4 fault injection full suite: add after the replay harness is stable. Trigger: first replay-disagreement incident or before the go-live review.
- [ ] GOLV-4 signed confirmation, HITL-6 approval expiry: add before any live discussion.

### Future Consideration (v2+)

- [ ] SIG-3 trade-flow features and trade-derived bundler detection: defer until the human decides on a funded key. Why defer: blocked by a financial decision, not engineering.
- [ ] Post-graduation AMM modelling: defer. Why: no reserve source (AF-13).
- [ ] Live adapter and any real send path: defer and keep disabled. Why: out of scope; needs its own change document and a re-run of the paper window (RISK_POLICY section 5, item 4).
- [ ] Hyperparameter search on replay datasets only: defer. Why: value unproven; must never touch the live window (AF-9).

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---|---|---|---|
| DISC-1, DISC-2 discovery and client | HIGH | MEDIUM | P1 |
| DISC-4 curve state | HIGH | MEDIUM | P1 |
| SIG-1 curve polling price ticks | HIGH | HIGH | P1 |
| EXEC-1 to EXEC-5 curve fill, fees, re-quote, drops, floor | HIGH | HIGH | P1 |
| EXEC-6, EXEC-7, EXEC-8 graduation, MTM, blind protection | HIGH | MEDIUM | P1 |
| LEDG-1 ledger | HIGH | HIGH | P1 |
| LEDG-2, LEDG-3 PnL and drawdown | HIGH | MEDIUM | P1 |
| REPL-1 deterministic replay | HIGH | HIGH | P1 |
| REPL-2 LLM recording | MEDIUM | MEDIUM | P1 |
| SAFE-1, SAFE-2, SAFE-3, SAFE-9 cheap checks | HIGH | LOW | P1 |
| SAFE-10, SAFE-11 verdict and fail-closed | HIGH | MEDIUM | P1 |
| SAFE-4 holder concentration | HIGH | HIGH | P1 if decision 1 is yes; otherwise P2 with BLIND |
| SIG-2, SIG-4 momentum and confidence | HIGH | MEDIUM | P1 |
| RISK-1 to RISK-7 | HIGH | HIGH | P1 |
| SUPV-1 to SUPV-4, SUPV-6 | HIGH | HIGH | P1 |
| RPT-1, RPT-2, RPT-3 reports | HIGH | MEDIUM | P1 |
| HITL-1, HITL-2, HITL-3 approvals | HIGH | MEDIUM | P1 |
| HITL-4, HITL-5 escalation and commands | MEDIUM | MEDIUM | P1 |
| GOLV-1, GOLV-2, GOLV-3 live gate (disabled) | HIGH | MEDIUM | P1 |
| SAFE-6 RPC sell simulation | MEDIUM | HIGH | P2 |
| SAFE-7 and SAFE-8 bundler and deployer | MEDIUM | HIGH | P2 |
| SIG-5 LLM scoring | MEDIUM | MEDIUM | P2 |
| DIFF-3, DIFF-4 calibration and attribution | MEDIUM | MEDIUM | P2 |
| DIFF-5 lookahead check | MEDIUM | HIGH | P2 |
| REPL-4 fault-injection suite | MEDIUM | MEDIUM | P2 |
| EXEC-10 Jupiter informational | LOW | LOW | P3 |
| SIG-3 trade-flow features | HIGH | HIGH | P3 (BLOCKED) |
| Post-graduation modelling | LOW | HIGH | P3 (anti-feature for v1) |

**Priority key:**
- P1: Must have for this milestone's paper run
- P2: Should have, add after the first weekly report or when the blocker is cleared
- P3: Nice to have, future consideration or blocked

## Competitor Feature Analysis

Only features verified in the docs read are listed. Hummingbot paper-trading and RugCheck could not be verified (see Scope and method).

| Feature | Freqtrade (docs read) | Hummingbot (docs index read) | Vendor `grokbot-pumpfun` (repo docs) | Our Approach |
|---|---|---|---|---|
| Dry run and persistence | Dry run stores no trades by default; `--db-url` enables storage (bot-usage) | Paper trading page not verified (404) | Dry-run only; persisted as a single JSON state file (`state.py:32-45`) | Ledger always written; no unpersisted paper mode (AF-12); hash-chained SQLite WAL |
| Fee modelling in backtests | `--fee` applied twice (entry and exit); default fee fetched from exchange market info | Not verified | Fee fields in risk config; no fee model in paper | Venue, base, and priority fees in integer lamports, separately reported (EXEC-2, LEDG-2) |
| Lookahead or leakage check | `lookahead-analysis` perturbs indicator values and compares moved entries and exits; flags false positives when code depends on the pairlist | Not verified | None | Replay-based perturbation check (DIFF-5), with the same caveat about verifying only triggered signals |
| Pre-trade filters | Pairlist filters: `AgeFilter`, `SpreadFilter`, `VolatilityFilter`, `PerformanceFilter`, `PriceFilter` (plugins page) | Not verified | Vendor `FilterConfig` (one position per creator, min trade size) | Create-frame pre-filter (DISC-5) plus creator-dedupe (`risk.engine.one_position_per_creator`) |
| Fill model | Exchange order-book style through ccxt | Not verified | No fill model; "EXTEND" to curve math (`paper-engine.md` section 1) | Bonding-curve constant-product fill with impact, re-quote, drops, floor, partials (EXEC-1 to EXEC-5) |
| Safety and authority checks | Not applicable | Not applicable | Authority, holder, LP checks; vetoes `CREATOR_SHARE_VETO = 0.25`, `TOP5_SHARE_VETO = 0.80` | Ten-check list with explained verdict and fail-closed BLIND (SAFE-1 to SAFE-11) |
| Daily loss halt | Not verified | Not verified | Auto-clears at UTC rollover (`risk.py:106-117`) | Explicit human clear only (RISK-2, AF-17) |
| Live gate | Not applicable | Not applicable | Not applicable | Nine preconditions; refuses to start; disabled in this milestone (GOLV-1) |
| Operator tooling | Telegram and web UI (bot-usage intro) | Condor (AI assistant), Hummingbot API, MCP server, Quants Lab backtesting sandbox (docs index) | Hermes cron jobs and Telegram chief profile | Text reports and alert channel only; web UI out of scope (AF-16) |

## Sources

**Primary, read in this research (2026-10-21)**
- PumpPortal real-time data (free vs metered methods; metering 0.01 SOL per 10,000 events; funded key 0.02 SOL; one connection; reconnect): https://pumpportal.fun/data-api/real-time/ - HIGH
- PumpPortal FAQ (200 subscribe messages per second; 5,000 keys per message; bans about one hour; data at processed commitment, under 100 ms behind gRPC from New York; trading endpoints 25 requests per second; reconnect advice): https://pumpportal.fun/FAQ - HIGH. Answer to "Do you provide historical Pump.fun token data?" was not read - LOW.
- Freqtrade bot usage (dry-run stores nothing by default; `--db-url`): https://www.freqtrade.io/en/stable/bot-usage/ - HIGH
- Freqtrade backtesting (`--fee` applied twice; timerange; export and cache options): https://www.freqtrade.io/en/stable/backtesting/ - HIGH
- Freqtrade lookahead analysis (perturbation method; forced options; false-positive caveats): https://www.freqtrade.io/en/stable/lookahead-analysis/ - HIGH
- Freqtrade plugins (pairlist handlers and filters): https://www.freqtrade.io/en/stable/plugins/ - HIGH for filter names; protection details not read
- Solana Token Extensions overview (full `ExtensionType` list; incompatible combinations): https://solana.com/docs/tokens/extensions - HIGH
- Solana Transfer Hook guide (CPI on every transfer; accounts read-only in the hook): https://solana.com/docs/tokens/extensions/transfer-hook - HIGH
- Hummingbot documentation index (Condor, Hummingbot API, MCP, Quants Lab): https://hummingbot.org/docs/ - MEDIUM (index only)
- pump.fun docs root (terms clickwrap only; no technical bonding-curve specification found): https://pump.fun/docs - no technical claim made

**Repository, read as required reading or cited from it (HIGH for desk requirements)**
- `.planning/PROJECT.md` (core value, active requirements, constraints, key decisions)
- `docs/upgrade-plan-desk-v2.md` sections 4 (decisions D1-D9, R-items) and 5 (requirement families FOUND, TOOL, SKILL, PAPER, RISK, AUTO, OBS, SEC, GOLIVE, out-of-scope table)
- `docs/RISK_POLICY.md` sections 2.2 (risk budget), 2.4 (BLIND is KILL), 3.1-3.2 (paper window and report evidence), 4.1-4.4 (prohibited actions and boundary)
- `docs/design/paper-engine.md` sections 1 (extend-vs-build), 2.2-2.7 (curve math, fees, latency, partial fills, MTM), 6.7 (degraded modes), 9 (tests), 11 (contradictions)
- `docs/TOOL_CATALOG.md` section 3 (`safety.*`, thresholds) and section 4 (`exec.*`)
- `agents/risk.md` lines 35-50 (ten-check live checklist and thresholds)
- `.planning/research/STACK.md` (verdict table V-1 to V-12; PumpPortal, Jupiter, pump.fun REST, Solana RPC, x.ai fact sheets; live observations of 2026-10-21)

**Not available**
- `docs.rugcheck.xyz`: DNS resolution failed (`getaddrinfo ENOTFOUND`). No RugCheck feature is claimed.
- Hummingbot paper-trading page `hummingbot.org/v2/paper-trading/`: HTTP 404. No Hummingbot paper-model claim is made.

---
*Feature research for: Autonomous Solana memecoin paper-trading desk (milestone: discovery, safety, signals, paper execution, ledger, replay, risk, supervision, reports, HITL, go-live gate)*
*Researched: 2026-10-21*
