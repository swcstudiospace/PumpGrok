# Design C: risk, promotion lifecycle, dormant live path, segregated signer

Repo facts below were checked against the tree. [INF] marks inference. Owners come from `resolve_owner`; note that `src/pumpgrok/cli/**` resolves to bot-02-risk because the manifest names the legacy file `cli.py`, so CLI units here are risk-owned (OD-5).

## 0. Findings that shape the design

- Three breakers already exist (`risk/breakers.py`: `data_stale`, `loss_velocity`, `exec_errors`), restart-safe via ledger rows. v4 extends them; it does not add duplicates.
- RiskEngine has 19 R34 rows in `STEP_IDS`, persisted in `OrderPlaced.risk_json`. A 20th row would change every order row and the smoke-10m replay hash. New reasons therefore map onto existing rows, the way `reputation_degraded` maps onto `breaker_open`.
- Live mode today forces `manual-ticket` at registry build, so the engine cannot approve autonomously. An `autonomous_live` approval kind is the one new engine concept (amendment clause 2).
- `live confirm` already writes an HMAC record (`var/live_confirmation.json`, config-hash bound, cap at most 1.0 SOL) but its allowlist hash is `sha256("[]")` and no verifier exists. `LiveGate` rows 5, 6, 8, 9 are hardcoded unmet; the id of row 6 is `notional_cap`.
- `Fill.venue_tx_ref` is pattern-locked to `dry_run:ULID`; `FillRecorded.venue_tx_ref` is an unconstrained string. `EventSource` is `paper|replay|manual`.
- No signing symbol may exist under `src/pumpgrok` outside `execution/live/` (INV-S-01). `services/` is outside that scan.

## 1. Risk additions

All new behavior is config-gated, default off, so smoke-10m is byte-identical (RSK-07).

**1.1 Strategy attribution (carrier agreed with Design B).** `allocate_ticket(..., strategy_id=None, param_set_hash=None)` appends refs `strategy:<id>` and `param_set:<64hex>` after `refs[0]` (the ticket, so `day_max_ticket_number` is unaffected). Legacy rows stay byte-identical; unbound ticket means `legacy_screening`. Reader `strategy_of(store, ticket_id)` lives in `risk/strategy_slice.py`.

**1.2 Strategy exposure slice.** Inside `RiskEngine._evaluate`, in the existing `max_token_fraction` step function: remaining slice = `slice_lamports(equity, weight)` (Design B leaf `strategies/allocation.py`) minus open cost basis of that strategy's positions. A buy above the remainder is capped to it, or rejected as `strategy_slice_exceeded` if below `min_trade_lamports`. Weights arrive as a `Mapping[str, Decimal]` at engine construction. Reason maps to row `max_token_fraction`. Sells skip it, as for all exit steps.

**1.3 Strategy kill.** State is a ledger row: `ConfigChanged(keys_changed=["strategy_kill:<id>"], new_hash="killed", by="gate:risk")`, read with `is_writer` semantics. Triggers: strategy day loss at or past `risk.strategy.daily_loss_fraction_of_slice` of its slice (REVIEW default 0.25), N consecutive losses, an `exec_errors` trip attributed to it, or a promotion demotion. Evaluated on the PositionClosed and breaker edges and lazily at `check()`; the row is idempotent per (id, day). Clear is human-only (`human:`), like halts. Reason `strategy_killed` maps to row `breaker_open`; unbound-while-enabled is `strategy_unbound` on row `seat_may_trade`. Exits always pass.

**1.4 Feed staleness (extend `data_stale`).** The breaker is silence-based; an event-driven desk is legitimately silent. Changes: (a) only frames from feeds declared `critical` call `note_tick` (a new `FeedHealth` book, keyed by feed name, fed by Design A's transports); (b) staleness evaluates lazily at `check()` and on the RiskEdge from a transport disconnect (`note_miss`), never by timer; (c) it applies only when exposure exists or a buy is under check, so idle is quiet; (d) in live mode a required feed that never ticked fails closed as `feed_stale` (today the breaker never trips before the first tick); (e) strategies declare `required_feeds`; a stale one refuses that strategy's buys. Reasons map to `breaker_open`. The `data_stale` step on held-mint MTM age still needs on-demand mark refresh before a buy check (Design A/B dependency).

**1.5 Repeated execution failure (extend `exec_errors`).** Add live failure classes to `EXEC_ERROR_REASONS`: `sim_failed`, `send_failed`, `tx_failed_onchain`, `tx_dropped` (already present). Same 3-in-10-minutes trip, ledger-rebuilt. A separate `live_unknown` is not a breaker: any UNKNOWN sets `HaltSet(reason="live_unknown", set_by="risk_engine")` immediately, human-clear only (clause 3). A strategy-attributed failure also counts toward 1.3.

**1.6 Memecoin entry checks.** `risk/entry_checks.py`, async `EntryGate.refresh(mint)` called by the adapter's `place()` before `check()`, filling a Clock-TTL cache (`risk.entry.facts_ttl_s`, default 30); the sync engine reads it through an injected `entry_facts(mint)` callable (same shape as `get_reserves`). Missing or stale facts fail closed as `entry_check_failed`, mapped to row `seat_may_trade`. Facts come from `tools/onchain/authorities.check_mint` and `top_holders` (rug-owned, unchanged). Hard rules, live and shadow modes: mint authority and freeze authority both null; mint owner is Token or Token-2022 program; Token-2022 extensions limited to `metadataPointer` and `tokenMetadata` (any other, including transfer fee, hook, permanent delegate, pausable, non-transferable, default-frozen, is a reject; research.md says do not assume pump create_v2 is clean); top-10 non-curve holders at most `risk.entry.max_top10_fraction` of circulating supply (REVIEW default 0.30; curve ATA excluded); BLIND on any fact is a reject (stricter than the paper-mode SAFE-4/8 advisory); curve `complete` or `real_token_reserves==0` rejects buys. Lists live in version-controlled `config/mint_lists.toml` (block mints, block creators, optional allow-only mode for the first armed week); RISK kill verdicts continue through `_killed_mints`. Paper mode enables the gate by config so paper evidence reflects live gating.

**1.7 Enforcement path.** Two independent points. (1) In-process: every `place()` implementation calls `risk.check` inside the ledger transaction (existing `_append_order_batch` shape); live and shadow adapters follow it. (2) Out-of-process: the signer re-derives caps, allowlist, stop state, strategy stage and kill, arm validity, and mint facts from its own RPC and a read-only ledger fold (section 4.3). A strategy has no handle to either; it emits intents and the supervisor composition root owns the adapter.

**1.8 Bypass-proof tests.**
1. Choke point: parametrize {Paper, SignerLive on a fake signer, Shadow} x seeded random orders x perturbed ledgers (halt, kill, breaker open, strategy kill, stage below LIVE_ELIGIBLE, stale feed, slice exhausted, blocklisted mint, bad extension, cap exceeded). Invariant: when any condition holds the fake signer records zero `place` frames.
2. AST test: every `place` in `src/pumpgrok/execution/**` reaches `.check(` before any signer or ledger side effect.
3. Import graph: `pumpgrok.strategies` and `pumpgrok.promotion` cannot reach `execution.live`, `desk_signer`, `solders`; extends `test_import_graph_no_live.py` guarded roots.
4. Signer-only bypass: send frames straight to the signer with a crafted valid `OrderRequest`; every stop condition still refuses.
5. Fault matrix with `FaultInjector` modes TIMEOUT, UNKNOWN, MALFORMED, RAISE on a new `FaultySignerTransport`: exactly one `place` frame per `exec_place_key`, no retry, UNKNOWN sets the halt.
6. `STEP_IDS` length 19 and `risk_json` row shape pinned.

## 2. Promotion lifecycle

**Stage machine.** BACKTEST (default) to PAPER to LIVE_ELIGIBLE. LIVE is derived, never stored: stage LIVE_ELIGIBLE and the strategy in a verified arm record and the gate open. Stage binds the pair (strategy id, `param_set_hash`) where the hash is the single PR 17 identity (`ParamSet.content_hash`); any hash change resets that pair to BACKTEST.

**Storage and log, existing event types only.** Stage row: `ConfigChanged(keys_changed=["strategy_stage:<id>:<hash>"], old_hash=<prior stage>, new_hash=<stage>, by="gate:promotion" or "human:<name>")`. Decision log: a `JournalNote(seat="desk", note_kind="review", refs=["strategy:<id>","param_set:<hash>","run:<id>"], text="promotion <id> <from>-><to> reason=<code>")` in the same `append_batch`. Blocked attempts write one note per changed reason (key `promo-blocked|id|hash|reason`), reusing `upgrade/escalate.py` for the human-facing `Escalation`. Evidence manifest via `upgrade/evidence.record_promotion` (`var/upgrade/promotions/<hash>.json`). Readers copy `ledger/active_set.py`: ledger order, last valid row, writer prefix check through `is_writer` (PR 18), and `verify_stored_content` before any append so no row names an unstored param set (PRM-06).

**Thresholds, version-controlled.** `config/promotion_thresholds.toml`, loaded fail-closed, floors enforced by the loader against `LiveGate` constants (14 days, 50 closed trades, profit factor 1.2, drawdown 0.15): a looser value refuses to load. Keys: `[backtest_to_paper]` (`max_trials` 20, holdout net positive, bounds), `[paper_to_live_eligible]` (`min_days`, `min_closed`, `min_profit_factor`, `max_drawdown`, divergence limits from `backtest/divergence.py` D7 defaults, `min_shadow_orders`, `max_shadow_slippage_gap_bps`, no kill and no unresolved UNKNOWN in window), `[demote]` (hysteresis: profit factor below 1.0 over the last N closed, drawdown above `max_drawdown`, consecutive losses, divergence breach, shadow gap). Editing the file is a risk-owned change with a human-approved receipt (RISK_POLICY change control).

**Gate reuse.** BACKTEST to PAPER runs `upgrade/gate.evaluate_candidate` checks 1 to 4 (bounds, trials, autonomy level, holdout); `evaluate_candidate` gains `paper: MetricsReport | None`, and `None` skips only the divergence check. PAPER to LIVE_ELIGIBLE runs all five including `divergence.check` on the same window, then the thresholds. Paper metrics use only `source=paper` rows attributed by `strategy_of`, valued through the shared `backtest/equity.py` (PR 17/19), so backtest and paper cannot diverge on valuation. Replay and backtest rows never count (existing LiveGate rule).

**Automatic demotion.** LIVE_ELIGIBLE to PAPER on any demote threshold, a strategy kill, a halt with a `ledger_inconsistent` reason, or a hash change; PAPER to BACKTEST on a hash change or severe degradation. Demotion by `gate:promotion` takes effect at the next decision because both RiskEngine and signer read the stage (reason `strategy_stage_ineligible`, mapped to row `live_gate`). Re-promotion needs a fresh window starting at the demotion row. Humans can demote and arm; they cannot promote past a failed threshold. One-operation rollback: `pumpgrok promotion demote <id> --by human:<n>`.

**Event-triggered, no timers.** `PromotionEvaluator.on_edge(edge)` is a pure function subscribed (Design A bus) to PositionChange closed, RiskEdge breaker, halt and kill, `Timer(daily_rollover)` (the one daily edge, covers day-count thresholds), and Design B's backtest-finished edge. No Grok calls, no `Clock.sleep` in `promotion/` (AST test, PRM-05). Idle emits nothing. Design B supplies `BacktestEvidenceProvider.latest(strategy_id, param_set_hash)` returning run id, `HarnessResult`, `MetricsReport`.

## 3. Live gate: five hardcoded preconditions

Exit 3 remains the default: with overlays at `enabled=false`, no env flag and no record, rows 1, 2, 7 stay unmet whatever else is built.

| Row | Implementation |
|---|---|
| 5 `wallet_allowlist` | `LiveSettings.wallet_allowlist: tuple[str,...]`, base58 shape validated. Met when non-empty, the signer identity file (`var/signer/identity.json`, written by the signer at start) names a pubkey in the list, and the record's `wallet_allowlist_sha256` equals the hash of the canonical sorted list. `live confirm` stops hashing `[]`. |
| 6 `notional_cap` | `LiveSettings.notional_cap_sol: Decimal`, validator `0 < x <= 1.0` (above 1.0 is a `ConfigError` at load). Met when set and not above the record cap. Meaning: per-order cap, total open live notional cap, and UTC-day buy cap, each the minimum of this and the D6 fractions. |
| 7 `confirmation_record` | `execution/live/arm.py` verifies shape, expiry (injected Clock), `config_hash` against current settings, `wallet_allowlist_sha256`, strategies listed. The HMAC itself is verified by the signer, which alone holds `PUMPGROK_CONFIRMATION_KEY`; the signer writes `var/signer/attestation.json` (record digest, verified, expiry) and the gate requires it. The desk never holds the key (doctor check LIV-11). Records gain a `strategies` list. |
| 8 `adapter_registered` | `execution/live/registry.py`: explicit literal `LIVE_ADAPTERS = {"signer": SignerLiveAdapter}`; met when `live.adapter` names an entry and `execution.build_adapter` can build it. `LiveGate` takes the registry as an injectable argument for tests. |
| 9 `no_active_stop` | `ledger/stop_state.py::read_stop_state(ledger_path, kill_file, environ)` folds the live ledger read-only (`mode=ro`) with `ledger.reducer.reduce` plus the kill file; reports halt, kill, open breakers, strategy kills; unreadable is unmet. Shared by the gate and the signer. |

New read-only verb `pumpgrok live status` prints the gate lines without starting anything. Today's 14-day and performance rows (3, 4) are unchanged.

## 4. Signer service `services/desk-signer`

**Process boundary.** Separate process, preferably separate container and uid, own sqlite (`var/signer/signer.sqlite`), own RPC client. It imports only an allowlisted set of desk modules (`core.adapter`, `core.idempotency`, `core.units`, `core.errors`, `core.signer_protocol`, `ledger.reducer`, `ledger.stop_state`, `ledger.strategy_state`, `replay.clock`), enforced by an import-graph test in its own suite. No desk code imports `desk_signer`.

**IPC.** Unix domain socket at `var/signer/signer.sock`, mode 0600, `SO_PEERCRED` uid allowlist, length-prefixed `canonical_json` frames. Chosen over loopback HTTP with HMAC: an HMAC secret in the desk environment adds no authority boundary, because a compromised desk can always call the socket; authorization is signer-side policy. Replay window: each frame carries a nonce and `Clock` timestamp. Frames: `hello` (pubkey, policy hash, mode, attestation), `quote`, `simulate`, `place`, `status(exec_key)`, `reconcile(exec_key)`, `balances`.

**Intent schema.** `place` carries the `OrderRequest` JSON unchanged, `exec_place_key(ticket, side, decision_id)` as the dedupe key, `approval_id` and kind (`human_buy`, `autonomous_live`), and `strategy_id`. Duplicate `exec_key` returns the stored response, never a new send.

**4.3 Signer-side policy, all fail-closed, in order.** mode and kill file; `read_stop_state` (halt, kill, open breakers, strategy kill); arm attestation valid and covers the strategy; `strategy_stage == LIVE_ELIGIBLE` for the hash; wallet pubkey in allowlist; `size <= notional_cap`; UTC-day buy sum within cap (signer-persisted); `size <= 2 percent` of fresh wallet SOL balance (D6, ground-truth balance); mint facts re-fetched from the signer's own RPC under the section 1.6 rules; curve not complete. Sells pass the stop checks only for rule and flatten reasons, mirroring `EXIT_SKIP_STEPS`.

**Transaction build.** Recommendation: PumpPortal `trade-local` for v1, behind a `TxBuilder` interface, with mandatory decode-and-verify. Tradeoff: direct pump instruction building needs no third party but the official account lists change in breaking upgrades (17 versus 26 accounts, rotating fee recipients, Token-2022 versus legacy program, cashback and mayhem flags) and there is no official Python SDK, so a wrong hard-coded account costs funds or silently fails; PumpPortal tracks those upgrades but is an untrusted builder with an undocumented fee transfer (0.5 percent) and unstated priority-fee unit. Controls that make the untrusted builder safe: (a) program allowlist after decode: ComputeBudget, the pump program, Token and Token-2022 for the wallet's own accounts, associated-token-account create, System transfer only to a pinned recipient set (PumpPortal fee account pinned in version-controlled config after shadow observation, plus Jito tip accounts if enabled), exactly one signer (the wallet) as fee payer; (b) mint in the instruction accounts equals the intent mint; (c) compute budget price times limit within the fee cap; (d) mandatory pre-flight `simulateTransaction` with `replaceRecentBlockhash`, `accounts` returning the wallet and its token account post-state: reject unless SOL decrease is at most the cap bound plus fees and the only token delta is the intent mint with out-amount at least `other_amount_threshold`. Check (d) bounds the damage even when the instruction structure is unfamiliar. Direct building remains the fallback behind the same interface. Jupiter is post-graduation only (`/order`, sign, `/execute`), unverified before graduation.

**Fees.** Default policy: priority fee only, compute-unit limit from the simulation `unitsConsumed` plus 10 percent margin, price from `getRecentPrioritizationFees` capped by `signer.fee_cap_lamports`; Jito off by default. If enabled: tip inside the trade transaction (failure costs no tip), tip accounts from `getTipAccounts` at random, sizing from `tip_floor`, 70/30 priority/tip split, `bundleOnly`; skipped when the transaction uses lookup tables.

**Single send and persistence.** Per `exec_key` row states: RECEIVED, BUILT, SIMULATED, SIGNED, SUBMITTED, then CONFIRMED_OK, CONFIRMED_FAILED, DROPPED or UNKNOWN. The SIGNED row (signature, tx bytes, `lastValidBlockHeight`) is committed with fsync before `sendTransaction` runs; the send uses `maxRetries: 0` and the signer never rebroadcasts. After a restart any SIGNED or SUBMITTED row is reconciled, never re-signed or resent.

**Confirmation and classification.** Poll `getSignatureStatuses(searchTransactionHistory=true)` through the injected `Clock` for at most `limits.confirm_timeout_s`. Success at `confirmed`; `err` non-null is CONFIRMED_FAILED (custom code mapped from the pump IDL: 6002 and 6003 slippage, 6005 curve complete, 6022 and 6023 sell errors). Status null and block height above `lastValidBlockHeight` after a final finalized-commitment check is DROPPED (definitively not landed, reason `tx_dropped`). Anything else, including RPC unreachable, is UNKNOWN: persisted, reported as `status=unknown`, never retried; while any UNKNOWN row exists the signer reconciles it on its own clock and nothing else runs (no idle work).

**Reconciliation from chain.** `getTransaction` (`maxSupportedTransactionVersion=0`, finalized when available): token units from pre/post token balances for owner and mint; SOL from the wallet's lamport delta; `meta.fee` is the network cost; the TradeEvent (`Program data:` log, discriminator `bddb7fd34ee661ee`) splits venue and creator fee. Fill numbers come from the chain, not the quote or the builder response. Account rent for a new token account (about 0.002 SOL, 20 percent of the 0.01 SOL minimum trade) is counted in cost basis and flagged to Design B for the backtest fee model (OD-2).

**Keys and secrets.** Key in a file readable only by the signer uid, mounted from a secret store on the signer host, path in `DESK_SIGNER_CREDENTIAL_PATH` (name avoids the forbidden key-like substrings; the desk still refuses them). Placed by the human directly; never in git, compose files, desk env, chat, or the desk image. `PUMPGROK_CONFIRMATION_KEY` also lives only on the signer host and the human's arm terminal. Redaction: the signer's JSON log filter drops base58 strings of key length, signed bytes and key paths; frames returned to the desk contain signature and facts only. `.env.example` placeholders and G-3 stay green. Throwaway wallet limit unchanged.

## 5. Live adapter client (`execution/live`)

- `signer_client.py`: `SignerLiveAdapter` implements `ExecutionAdapter` (mode LIVE, venue `signer`) over the socket. It holds no key, no Solana client, no symbol from the INV-S-01 list; its verbs are `submit` and `reconcile`.
- `place()`: allocate via existing flow, `entry_gate.refresh`, `risk.check` inside the ledger transaction (`OrderPlaced` with `autonomous_live` approval consumed in the same `append_batch`), send frame, map response to `Fill` or `OrderRejectedError` or `OrderUnknownError`; unknown sets the halt and consumes the approval (exec.place already returns `status=unknown` and never resubmits).
- `Fill.venue_tx_ref` pattern becomes `^(dry_run:[ULID]|[1-9A-HJ-NP-Za-km-z]{64,88})$`; tests prove Paper never emits a signature form and Live never emits `dry_run`.
- Live ledger: `var/live/ledger.sqlite`, `source="live"` (new `EventSource`, additive contract change C-07; alternative reuse of `manual` rejected because it conflates human-authored rows with venue fills). Paper window rows stay pure.
- Registry and factory: `LIVE_ADAPTERS` in `execution/live/registry.py`; `execution.build_adapter` (sniper-owned) dispatches to it only when the effective mode is live and the gate is open.
- Startup and edge reconciliation (no timers in the desk): at construction, on each fill, before each `place`, and on `Timer(daily_rollover)`: list non-terminal live `OrderPlaced` rows, ask the signer `status(exec_key)`, append missing `FillRecorded` or `OrderRejected` with the deterministic order key; an unresolved UNKNOWN appends `HaltSet(live_unknown)`. At start and rollover also compare signer `balances` against the ledger fold; drift beyond `live.drift_tolerance_lamports` appends `HaltSet(wallet_drift)`. Restart recovery is exactly this path plus the signer's own SIGNED-row reconcile.
- `autonomous_live` approval: new `ApprovalRecord.kind` in `core/approvals.py`, minted by the engine only when mode is live, the arm is verified, and the strategy is listed; payload stays `ApprovalRecorded` with `kind` a string, so no schema change.

## 6. Guards and tests, changed deliberately

- INV-S-01 is tightened, not loosened: remove `EXEMPT_PREFIX`; forbid `sign`, `send_transaction`, `sendTransaction`, `Keypair` and the `solders`/`solana` imports everywhere under `src/pumpgrok`, including `execution/live/`. The desk never signs; signing exists only in `services/desk-signer`, which gets its own test: signing symbols allowed only in `signing.py`, no import of `pumpgrok.engine`, `pumpgrok.supervisor`, `pumpgrok.tools`.
- `test_import_graph_no_live.py`: `QUARANTINE_MODULE` stays the stub; add the signer client to the quarantined set for backtest, upgrade, paper adapter, strategies and promotion; the supervisor and CLI may reach the registry, not the client module.
- `test_no_live_adapter_registered.py`, `test_live_adapter_raises.py`, `test_no_backtest_to_live_path.py`, `test_gate_reports_adapter_unmet`, `test_live_refusal_lists_nine.py`: rewritten in the same PR as the registry. `build_adapter` still returns `PaperAdapter` for paper and replay; the "registry empty" assertion becomes "registry contains exactly `signer`, and live is refused without the gate". `LiveAdapterStub` stays as the refusing adapter for gate-closed live mode.
- Overlay test `test_live_disabled_overlays.py` unchanged: every overlay ships `enabled=false`.
- Shadow-live (pre-arm rehearsal): `execution/live/shadow.py` composes `PaperAdapter` for ledger and risk, and calls the signer `quote` and `simulate` frames (a shadow-mode signer needs no key and refuses `place`). It writes a `JournalNote(note_kind="review")` per order with the paper expected-out versus simulated-out gap, source `paper`. Those gaps feed `min_shadow_orders` and `max_shadow_slippage_gap_bps`, and the same entry gate runs.

## 7. Amendment

Exact text: `/tmp/v4/design/C-AMENDMENT-DRAFT.md`. It amends clauses 1, 2, 3, 8, 9, the SNIPER bullet and the closing paragraph, with matching copies in `core-directives.xml`, the skill, RISK_POLICY, SECURITY, LIVE_READINESS, SAFETY_INVARIANTS and PROJECT. Unchanged: human arm, caps, kill switch, human-only clears, clauses 4 to 7. Agents never apply it.

## 8. Arm and rollback runbook (target `docs/runbooks/go_live.md`, `signer.md`)

Arm, all human-run, in order: (1) amendment merged, live units merged, `pumpgrok live status` shows only rows 1, 2, 7 unmet. (2) On the signer host place the throwaway wallet key file (0400, signer uid), fund at most the cap plus fees. (3) Start the signer in shadow mode; run shadow-live until the strategy shows `min_shadow_orders` within the gap limit; the stage must read LIVE_ELIGIBLE. (4) Set the overlay: `enabled=true`, `wallet_allowlist`, `notional_cap_sol`, `adapter="signer"`; commit it with a human-approved receipt. (5) Desk env `PUMPGROK_LIVE_ENABLE=1`. (6) On the signer host run `pumpgrok live confirm --by human:<n> --notional-cap <x> --strategies <ids> --expires <t>` with the HMAC key in that terminal only. (7) Restart the signer in live mode; confirm attestation. (8) `pumpgrok live status` shows all nine met; start the desk.

Rollback, fastest first: kill switch (existing; signer refuses on the kill file) then `pumpgrok live disarm --by human:<n>` (deletes the record, appends `ConfigChanged(keys_changed=["live_arm"], new_hash="revoked")`); `pumpgrok promotion demote <id>`; stop the signer and remove the key file; the human sweeps remaining funds outside the system; set `enabled=false`. After an UNKNOWN: `pumpgrok live reconcile --ticket <id>` shows the signature and chain status; the human clears with the existing `halt_clear` approval. No agent runs any of these.

## 9. Requirements and acceptance (`uv run` prefix implied)

| ID | Requirement | Check |
|---|---|---|
| RSK-01 | Slice enforced in engine, reason on existing row | `pytest tests/risk/test_strategy_slice.py -q` |
| RSK-02 | Strategy kill written, read, human-clear only | `pytest tests/risk/test_strategy_kill.py -q` |
| RSK-03 | Feed staleness lazy, idle-quiet, live never-ticked fails closed | `pytest tests/risk/test_feed_health.py -q` |
| RSK-04 | Live failure classes feed `exec_errors`; UNKNOWN halts | `pytest tests/risk/test_exec_failure_breaker.py -q` |
| RSK-05 | Entry checks reject authority, extension, holder, list, BLIND cases | `pytest tests/risk/test_entry_checks.py -q` |
| RSK-06 | No order reaches a signer past a failed check | `pytest tests/safety/test_risk_choke_point.py tests/safety/test_signer_only_bypass.py -q` |
| RSK-07 | smoke-10m hash unchanged | `pytest tests/e2e/test_autonomous_paper_recorded.py tests/replay -q` |
| RSK-08 | 19 rows and `risk_json` shape unchanged | `pytest tests/risk/test_step_rows_stable.py -q` |
| PRM-01 | Stage machine, ledger rows, decision log | `pytest tests/promotion/test_stages.py -q` |
| PRM-02 | Thresholds load fail-closed, floors enforced | `pytest tests/promotion/test_thresholds.py -q` |
| PRM-03 | Gate checks reused; no second search | `pytest tests/promotion/test_gate_reuse.py tests/upgrade -q` |
| PRM-04 | Automatic demotion and hash-change reset | `pytest tests/promotion/test_demotion.py -q` |
| PRM-05 | Event-triggered; no timers, no Grok | `pytest tests/promotion/test_no_timers.py -q` |
| PRM-06 | `is_writer`, `verify_stored_content`, one hash | `pytest tests/promotion/test_writer_discipline.py -q` |
| LIV-03 | Rows 5 and 6 real, cap above 1.0 refused | `pytest tests/live/test_gate_rows56.py -q` |
| LIV-04 | Arm record verified, bound to config hash | `pytest tests/live/test_arm_record.py -q` |
| LIV-05 | `no_active_stop` reader | `pytest tests/ledger/test_stop_state.py -q` |
| LIV-06 | Row 8 through explicit registry | `pytest tests/live/test_registry.py -q` |
| LIV-07 | Default live start exits 3 | `pytest tests/safety/test_live_refusal_lists_nine.py -q` |
| LIV-08 | Signer policy refusals | `cd services/desk-signer && uv run pytest -q` |
| LIV-09 | Single send, persist before RPC, UNKNOWN | `pytest tests/live/test_single_send.py -q` and the signer suite |
| LIV-10 | Reconcile from chain, restart recovery | `pytest tests/live/test_reconcile.py -q` |
| LIV-11 | Desk holds no key or signer import; doctor flags the HMAC key in a live desk env | `pytest tests/safety/test_no_signing_outside_live_stub.py tests/test_doctor_probes.py -q` |
| LIV-12 | Shadow-live never sends | `pytest tests/live/test_shadow.py -q` |
| LIV-13 | Guard tests tightened and green | `pytest tests/safety -q` |
| LIV-14 | `live` source contract change passes G-4 | `python3 ci/gates/check_contracts.py --change contracts/changes/v4-live-source.yaml` |
| LIV-15 | `autonomous_live` minted only when armed | `pytest tests/live/test_autonomous_live.py -q` |
| LIV-16 | Amendment oracle matches draft | `pytest tests/safety/test_constitution_amendment_2026_10_28.py -q` |

Every unit also passes `make lint typecheck`, `make gates BOT=<seat> TASK=<unit>` and a receipt that records the smoke-10m hash.

## 10. Units

Approval-wait column: W means merge waits for owner approval of the amendment; designs may be drafted earlier. No ownership PR is needed: every new path I add resolves to its seat via existing rules (checked).

| Unit | Title | Seat | Files | Depends | Acceptance | Parallel | W |
|---|---|---|---|---|---|---|---|
| C-01 | Ledger readers: strategy state, stop state, ticket refs | risk | `ledger/strategy_state.py`, `ledger/stop_state.py`, `ledger/tickets.py`, `tests/ledger/` | PRs 17-20 merged | RSK-07, LIV-05 | start now, lane L1 | no |
| C-02 | Engine: slice, kill, reason mapping, strategy settings | risk | `risk/strategy_slice.py`, `risk/engine/{constants,core,steps}.py`, `config/settings.py`, `tests/risk/` | C-01, Design B `allocation.py` | RSK-01, RSK-02, RSK-07, RSK-08 | L1 serial | no |
| C-03 | Entry checks and lists | risk | `risk/entry_checks.py`, `config/mint_lists.toml`, `tests/risk/` | C-02 | RSK-05 | L1 serial | no |
| C-04 | Feed health, exec-failure classes | risk | `risk/feed_health.py`, `risk/breakers.py`, `tests/risk/` | C-02, Design A transports | RSK-03, RSK-04 | L1 serial | no |
| C-05 | Promotion package, thresholds, `promotion demote` verb | risk | `promotion/**`, `config/promotion_thresholds.toml`, `upgrade/gate.py`, `cli/{parsing,dispatch,verbs_ops}.py`, `tests/promotion/`, `tests/upgrade/` | C-01, Design A bus, Design B evidence | PRM-01..06 | parallel with L1 | no |
| C-06 | Gate rows 5, 6, 7, 9; settings; arm verifier; `live status`, `live disarm`; doctor key check | risk | `config/settings.py`, `execution/live/{live_gate,arm}.py`, `cli/{parsing,dispatch,verbs_ops}.py`, `doctor.py`, `tests/live/`, `tests/safety/test_live_refusal_lists_nine.py` | C-01 | LIV-03, LIV-04, LIV-07, LIV-11 | parallel | no |
| C-07 | Contract: `live` event source | risk | `ledger/events.py`, `ledger/store.py`, `ledger/paths.py`, `contracts/events/*.schema.json`, `contracts/changes/v4-live-source.yaml` | none | LIV-14 | parallel; start early, acks take a round-trip | no |
| C-08 | Signer protocol schema | risk | `core/signer_protocol.py`, `tests/core/` | none | `pytest tests/core/test_signer_protocol.py -q` | parallel | no |
| C-09 | desk-signer service | risk | `services/desk-signer/**`, `tests/services/desk_signer/`, `Dockerfile`, `docker-compose.yml`, `pyproject.toml` pin | C-08, C-01 | LIV-08, LIV-09, LIV-11 | lane L2 | W |
| C-10 | Live adapter client, registry, `autonomous_live`, `live reconcile` verb, guard changes | risk | `execution/live/{signer_client,registry,reconcile}.py`, `core/{adapter,approvals}.py`, `risk/engine/steps.py`, `cli/verbs_ops.py`, `tests/safety/`, `tests/live/` | C-06, C-07, C-08, C-04 (same engine files) | LIV-06, LIV-10, LIV-13, LIV-15, RSK-06 | L2, needs only the C-08 schema from the signer lane | W |
| C-11 | Shadow-live adapter | risk | `execution/live/shadow.py`, `tests/live/` | C-09, C-10 | LIV-12 | L2 serial | W |
| C-12 | `build_adapter` dispatch to registry | sniper | `execution/__init__.py`, `tests/execution/` | C-10 | `pytest tests/execution -q` and RSK-07 | after C-10 | W |
| C-13 | Apply amendment, risk-owned part | risk | `rules/pumpgrok-team.mdc`, `prompts/_shared/core-directives.xml`, `docs/RISK_POLICY.md`, `SECURITY.md`, `docs/LIVE_READINESS.md`, `docs/SAFETY_INVARIANTS.md`, `tests/safety/amendment_2026_10_28_frozen.txt` + test | owner approval | LIV-16 | with C-14 | W |
| C-14 | Apply amendment, chief-owned part | chief | `agents/*.md`, `prompts-assembled/*.xml` via `make prompts`, `skills/desk-operating-model/SKILL.md`, `.planning/PROJECT.md`, `README.md` | C-13 | `make check` | with C-13 | W |
| C-15 | Runbooks | chief | `docs/runbooks/{go_live,signer,live_rollback}.md` | C-09, C-10 | `./scripts/check.sh` | parallel after C-10 | W |
| C-16 | Changelog with replay hash before and after | journal | `CHANGELOG.md` | all | RSK-07 receipt hash | last | no |

Sequencing hazard OD-3: C-13 and C-14 cannot merge separately, because the pinned-text oracle (risk files) and `assemble-prompts --check` (chief files) each fail until the other lands, and a seat-pure split cannot be atomic. Owner decision needed: a one-time PR-number G-1 waiver for a single amendment PR (existing precedent), or a prior ownership PR. The plan assumes the waiver, scoped to that PR only.

Open decisions: OD-1 add `live` source versus reuse `manual` (recommend add); OD-2 rent drag versus 0.01 SOL minimum trade; OD-3 above; OD-4 REVIEW defaults (holder fraction 0.30, strategy loss 0.25, drift tolerance) need owner numbers before arming; OD-5 `cli/**` resolves to risk.
