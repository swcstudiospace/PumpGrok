# Phase 3: Tools and Skills - Research

**Researched:** 2026-10-21
**Domain:** Python 3.12 typed tool registry (pydantic v2, httpx, tenacity), least-privilege seat rosters, desk gateway (MCP-style JSON-RPC), skill manifests
**Confidence:** HIGH for repository state (every path and line cited was read in this session); MEDIUM for upstream Solana/pump.fun layouts (tagged [ASSUMED]); blockers in the next section need user or orchestrator decisions before planning.

<user_constraints>
## User Constraints (from CONTEXT.md)

Copied from `.planning/phases/03-tools-and-skills/03-CONTEXT.md` (status "Ready for planning"). The planner MUST honor the Locked list.

### Locked Decisions
```
- Ids (R19): tool `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`; seat `SEAT_RE = ^bot-0[0-9]-[a-z-]+$`; transport `_` form computed at exposure only.
- Rosters (R35): 8..15 tools incl. core eight; RISK = RUG = 15. chief 15, scout 15, risk 15, whale 14, sniper 15, rug 15, exit 15, shill 11, signal 14, journal 15. exec.place/cancel: sniper, exit (P, g6). risk.kill_switch: risk. notify.alert: chief, journal. ledger_write: nobody.
- Invariants I1-I5 (interfaces 2.10): PermissionDenied outside allowed_tools; ceiling paper-write; LIVE_WRITE never resolvable for any seat (LiveGateError, audited); seats write only journal_note, escalation.
- Retry: j4 = jitter(3,0.5,4); j5 = jitter(3,0.5,5); j8 = jitter(3,1,8) network sinks. Retry on timeout, 5xx, 429 only; waits via Clock (R27).
- Rate keys: solana_rpc primary (R46, R47); pumpfun_rest degradable only; `jupiter` replaces jupiter_lite (R44).
- Backends: exec.quote = GET api.jup.ag/swap/v2/order, no taker (R44). Market reads from Solana RPC (R46). PumpPortal only subscribeNewToken, subscribeMigration (R45).
- exec.place key = digest over (ticket_id, side, decision_id) only (R23); payload and bot excluded, so a repeat returns the first Fill. Buy approval human_buy; sell exit_rule, autonomous_paper or human_sell (R33).
- risk.kill_switch (R22): action enum {set, flatten_request} only. Clear is CLI only (`pumpgrok killswitch clear --by --reason`); halt clear `pumpgrok state halt --clear --by --reason`.
- Risk budget (R20), nine keys: max_trade_fraction 0.02, max_token_fraction 0.05, daily_loss_halt_fraction 0.05, drawdown_halt_fraction 0.15, max_open_positions 3, max_trades_per_day 20, liquidity_floor_multiple 10, partial_fill_fraction 0.02, paper_equity_sol 10 (REVIEW). Sniper defaults; exit trade and token 0, open 0; other seats trade keys 0.
- Money (R28): `*_lamports: int`, `*_units: int`, Decimal ratios; `--size-sol` only SOL input. Inputs extra=forbid; upstream extra=ignore; malformed gives DataStale or BLIND.
- Events (R32): note_kind scout lead, whale whale, shill social, signal signal, chief ticket|halt|note.
- notify (R39, R40): destinations = config notify.allowlist (Telegram chat ids, webhook URLs); empty means stdout and file only.
- social (R31, D7): tools/social/ GET only; no post, put, patch or delete word, no POST client.
- Gateway (D2, TOOL-010): thin projection, own pyproject and uv.lock; tools/list = seat roster + _core; per-seat token via hmac.compare_digest; cross-seat token 403; no tool logic.
- CLI (R12, R40): section 12 verbs as JSON wrappers; `paper buy|sell --ticket --mint --size-sol --slippage-bps --approval-id`; add `pumpgrok tools <id> --help`.
- Skills (interfaces 3, 3.2): frontmatter name, description (max 1024), bots, gates, required_tools, required_data, permissions (never live-write), fixtures. Body: L1 - Summary, L2 - Method, Failure modes, References; L3 = references/*.md when L2 points there. Max 350 lines; no emoji.
- 12 new per interfaces 3.2; 23 existing per 3.1 (converted by Phase 2 batch 2.3, STRUCT-007; Phase 3 SKILL-002 gates them).
- Plugins: "23 skills" becomes "35 skills" in plugin.json:4, .claude-plugin/plugin.json:3, .grok-plugin/plugin.json:3, .grok-plugin/marketplace.json:9.

Tool table: id, class (R read, P paper-write), timeout s, retry, rate key, idempotency (`-` none; d derived; sha sha256).
market.price R 10 j4 solana_rpc -          onchain.token_metadata R 15 j5 solana_rpc -
market.ohlcv R 10 j4 solana_rpc -          onchain.authorities R 15 j5 solana_rpc -
market.liquidity R 10 j4 solana_rpc -      onchain.lp_status R 20 j5 solana_rpc -
market.trades R 10 j4 solana_rpc -         onchain.top_holders R 15 j5 solana_rpc -
market.holders_snapshot R 10 j4 solana_rpc - onchain.deployer_history R 20 j5 solana_rpc -
onchain.large_transfers R 20 j5 solana_rpc - onchain.priority_fee R 15 j5 solana_rpc -
safety.score_report R 45 - solana_rpc -    exec.quote R 12 j4 jupiter -
exec.simulate R 10 - solana_rpc -          exec.place P 20 - exec d(ticket_id,side,decision_id)
exec.cancel P 10 - exec d(order_id,cancel) exec.positions R 10 - ledger -
portfolio.ledger_read R 5 - ledger -       portfolio.ledger_write P 5 - ledger required key, unique index
portfolio.exposure R 5 - ledger -          portfolio.pnl R 5 - ledger -
risk.check_limits R 5 - ledger -           risk.drawdown R 5 - ledger -
risk.kill_switch P 5 - killswitch d(tool,action,reason,minute)
risk.halt_status R 5 - ledger -            notify.alert P 10 j8 notify d(kind,ticket,severity,minute)
journal.append P 5 - ledger d(kind,ticket,sha(body))
journal.render_report P 30 - ledger d(period,as_of day)
desk.brief R 10 - desk -                   desk.docs_search R 10 - desk -
desk.memory_retain P 5 - desk d(tool,bot,sha(input))   desk.memory_recall R 5 - desk -
desk.ownership_resolve R 5 - desk -        desk.receipt_check R 60 - desk -
desk.event_emit P 5 - desk d(tool,bot,sha(input))      desk.doctor P 60 - desk d(tool,bot,sha(input))
```

### Claude's Discretion
- exec.cancel input (order_id, ticket_id, approval_id); adapter reads decision_id from the order.
- Modules by catalog suffix (onchain/lp_status.py); ownership.yaml reconciles ROSTER section 7 names.
- NotYetImplementedAdapter raises PumpgrokError until Phase 4; TOOL-004 transaction proof moves to Phase 4.

### Deferred Ideas (OUT OF SCOPE)
- Phase 4 (PaperAdapter, RiskEngine, ledger, breakers, live gate); Phase 5 (RISK-007, fault injection).

### Orchestrator resolution R63 (binding, from Phase 2 review)
- The --seat check that refuses sniper and exit (plan 02-04) is a policy filter on the caller-supplied value, not an authentication control. The control is the registry plus the approval record (invariants I1-I5 and ApprovalRecord). Phase 3 adds tests/safety/test_cron_seats_cannot_write.py proving that a cron-owner seat (sniper, exit per hermes forbidden_owners) cannot resolve any paper-write tool through the registry, and that a paper buy without a valid approval_id is rejected regardless of --seat.
- Research note: read literally, R63's first clause conflicts with TOOL-009 (sniper and exit MUST resolve exec.place). See blocker B2 for the reconciling reading.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description (REQUIREMENTS.md) | Research support |
|----|-------------------------------|------------------|
| TOOL-001 | market.* typed outputs with freshness and source; recorded fixtures, no live network | Section 1, 2; blocker B9 (backend conflict) |
| TOOL-002 | onchain.* through single RPC client rpc.py, tenacity jittered retries, ordered failover, key in solana.rpc_api_key | Section 2.4; blocker B12 (config name drift) |
| TOOL-003 | safety.score_report scored report, thresholds from config, BLIND never exception | Section 1.3 (config section missing) |
| TOOL-004 | exec.* call ExecutionAdapter; place/cancel g6; decision_id; key derived; approval consumed in same ledger tx | Section 1.4; blocker B7 (same-tx deferred) |
| TOOL-005 | portfolio/risk/journal tools with catalog schemas; kill_switch only set and flatten_request; ledger_write denied to all | Section 1.5, 3 |
| TOOL-006 | notify.alert via abstract Notifier; allowlist; escalation kinds; rate limited and idempotent | Section 6.1 |
| TOOL-007 | desk core eight resolvable by every seat; desk.doctor check same code path as pumpgrok doctor | Section 1.5 |
| TOOL-008 | pydantic v2 I/O models, side_effect, timeout_s, RetryPolicy, rate_limit_key; money int; no float money; extra=ignore upstream | Section 2 (9 float grep hits) |
| TOOL-009 | least-privilege suite (interfaces 4) passes; social GET only | Sections 3, 5; blockers B2, B3 |
| TOOL-010 | services/desk-gateway serves /mcp/<seat>; tools/list equals roster plus _core; per-seat token; cross-seat 403 | Section 4; blocker B4 (service absent) |
| TOOL-011 | section 12 verbs as thin JSON wrappers; paper buy/sell flags | Section 6.2; blocker B8 |
| SKILL-001 | 12 new skills (35 total), frontmatter and L1/L2 body; desk-post-trade-review owned by bot-09-journal | Section 7 |
| SKILL-002 | tests/test_skill_manifests.py: parse, name==dirname, required_tools granted, max_side_effect != LIVE_WRITE | Section 7.2; blocker B10 |
| SKILL-003 | tests/test_bot_manifests.py: exactly ten BotManifests from contracts/tool-rosters/*.yaml, R35 sizes | Section 3.2; blocker B6 |
| SKILL-004 | seat prompts list load="always" skills and a `<tools contract=...>` section; agents and plugins match | Section 7.4 |
</phase_requirements>

## Summary

Phase 3 turns the Phase 1-2 scaffolding into a working typed tool layer. Today the package has the registry, the frozen contract models and the rosters, but **zero tools are registered** and the five read-only ports (RPC client, authority check, holder snapshot, priority fee, Jupiter quote) are plain dict-returning functions that predate the typed contract. Phase 3 must add 37 tools (plus `safety.score_report`, the `_core` eight) as `ToolSpec` objects, wire retry and rate limiting that are currently declared but not applied, build a `BotManifest` loader (the roster YAML does not carry the required manifest fields), add a GET-only social module, create the desk gateway (which does not exist in this repository), and bring 12 new skills plus 23 retrofitted skills under manifest tests.

The most consequential findings are not missing code but contradictions between locked decisions, requirements and the repository. Several success-criterion commands **cannot pass as written** (ROADMAP SC5 fails on 9 existing source lines; SC2 and SC3 reference artifacts that do not exist; SC4's social grep passes vacuously when the directory is absent). The blockers below must be resolved by the orchestrator or user before the planner writes task lists; the planner should not silently pick one.

**Primary recommendation:** resolve blockers B1-B4 first (they change scope), then build in this order: registry fixes and `ToolSpec` contract changes, then the tool packages in parallel (3A-3E from upgrade plan 6.3), then the manifest loader and least-privilege suite, then the gateway, then skills and prompts, then CLI wrappers. Verify with the commands in the Validation Architecture section.

## Blockers: decisions required before planning

These are ordered by impact. Each lists the evidence, the options, and a default recommendation the planner may use only after the orchestrator confirms it.

**B1. ROADMAP SC5 grep fails today on nine existing lines (scope conflict with vendor-parity code).**
Evidence: `grep -rnE "(lamports|units|sol)[A-Za-z_]*: *float" src/pumpgrok/` currently prints 9 lines:
`src/pumpgrok/cli.py:120` (`def size_sol_to_lamports(size_sol: float) -> int:`),
`src/pumpgrok/engine/models.py:49,50,85,264` (`market_cap_sol: float`, `sol_in_curve: float`, `sol_amount: float`, `sol_spent: float`),
`src/pumpgrok/engine/reputation.py:56,147` (`realized_pnl_sol: float`, `pnl_sol: float,`),
`src/pumpgrok/engine/tune.py:40` (`pnl_sol: float | None`).
The engine fields are pinned by locked characterization tests: `tests/characterization/test_analyzer.py:179` asserts `tok.sol_in_curve == pytest.approx(30.0)`, and `tests/characterization/test_holder_check.py:53-54` pins float outputs. Changing them to Decimal breaks `approx` against floats; renaming them breaks the pins.
Options: (a) convert only `cli.py:120` (param type to `Decimal`/`str`) and move the engine fields behind a typed boundary, leaving vendor-parity floats in `engine/`; the grep still fails, so SC5 must be re-scoped to `src/pumpgrok/tools/ src/pumpgrok/core/ src/pumpgrok/cli.py` (a textual change to the success criterion, needs user approval); (b) rewrite engine fields to Decimal and update characterization assertions (violates "locked" characterization pins); (c) keep the literal grep and accept a failing SC5.
Default recommendation: option (a) plus explicit user sign-off on the scope change. Never silently shrink.

**B2. R63 "cron-owner seats cannot resolve any paper-write tool" conflicts with TOOL-009 "only sniper and exit resolve exec.place".**
Evidence: `contracts/tool-rosters/bot-04-sniper.yaml` and `bot-06-exit.yaml` grant `exec.place` and `exec.cancel` (paper-write); TOOL-009 (REQUIREMENTS.md) and interfaces section 4 require that. `hermes/cron/jobs.yaml:79` declares `forbidden_owners: [sniper, exit]`, i.e. the cron job owners, not a registry identity.
Reconciling reading (recommended): a cron-owned invocation is resolved with `max_side_effect=SideEffect.READ`. The existing `ToolRegistry.find()` signature already takes `max_side_effect` (`src/pumpgrok/core/registry.py:98-104`), so a cron-context `find("exec.place", max_side_effect=READ, bot=sniper)` raises `PermissionDenied` with reason `exceeds_requested_max`, while the interactive `find(..., max_side_effect=PAPER_WRITE)` resolves. The test then proves both halves and is not vacuous.
Needs confirmation from orchestrator. Without it, the R63 test cannot be written as specified.

**B3. TOOL-009 wording "chief has no exposure tools" conflicts with the roster and with interfaces 4.**
Evidence: `contracts/tool-rosters/bot-00-chief.yaml` grants `exec.positions` (line 14), `portfolio.exposure` (line 32), `portfolio.pnl` (line 46) as reads; ROSTER.md section 6 matrix shows chief with those cells; interfaces 3.1 `desk-monitoring` requires `portfolio.exposure` for bot-00-chief. Interfaces section 4 asserts only "chief resolves no `exec.place`, `exec.cancel`, `market.*` tools".
Recommended reading: "exposure tools" means exposure-creating tools (exec.place, exec.cancel, market.*); keep the roster; rewrite TOOL-009's wording to match interfaces section 4. Needs user confirmation; do not remove `portfolio.exposure` from chief, because it breaks desk-monitoring.

**B4. `services/desk-gateway/` does not exist in this repository.**
Evidence: `find . -iname '*gateway*'` returns nothing; `services/` is absent. `docs/DISCOVERY.md:70-74`, `:190-204` and `:228` describe `services/desk-gateway/` as the reference implementation in the separate programming-desk repository; nothing in this repository implements it. Upgrade plan 6.3 unit 3E and ownership.yaml line 328 (`services/desk-gateway/**` owner `bot-00-chief`) expect it.
Consequence: the gateway is a new package built from scratch, not a port. Its design is in section 4. SC3 and the checkpoint depend on it.
Default: build it per section 4 with its own `pyproject.toml` and `uv.lock`.

**B5. TOOL-011 "every verb of section 12 ... prints JSON" vs backends that Phase 3 does not have.**
Evidence: section 12 verbs `killswitch clear`, `state halt --clear`, `live confirm`, `audit`, `risk audit`, `chief pickup`, `rug watch`, `report --daily` depend on ledger approvals, RiskEngine, the supervisor (Phase 4-5). Current CLI returns `not-yet-implemented` JSON with exit 5 (`src/pumpgrok/cli.py:127-131`).
Recommendation: a Phase 3 verb is "wired" when it calls the catalog tool through the registry; when the tool's backend raises `NotYetImplementedAdapter` (a `PumpgrokError`), the CLI prints the JSON error envelope and exits 5. This is the existing absent-subsystem contract. The orchestrator must confirm that this satisfies TOOL-011, because the literal "can run every verb" is not achievable before Phase 4.

**B6. The roster YAML cannot load as `BotManifest`.**
Evidence: `src/pumpgrok/core/bot.py:46-67` requires `id, display, channel, purpose, inputs, outputs, skills, allowed_tools, risk_budget, forbidden, fail_safe, schedule, escalation, owned_paths, receipts_dir, prompt_source` (+ `writes_to_exchange`). `contracts/tool-rosters/bot-04-sniper.yaml` has only `version, seat, short, endpoint, scope, core, packs_allowed, consumers, tools`. ROSTER.md section 5 says "The YAML form of the same fields lives in the BotManifest model", i.e. nowhere.
Options: (a) add a `manifest:` block to each seat roster file (changes a contract surface: G-4 change document; `ownership.yaml` contract_consumers for `contracts/tool-rosters/**` lists all ten seats, so acks are needed from all ten); (b) a new contract directory `contracts/seats/` (new surface, same G-4 burden, plus ownership entries); (c) generate the manifest from ROSTER.md section 5 (not machine-readable; rejected).
Default: (a), version bump 1.0.0 to 1.1.0 (additive, non-breaking), change document `contracts/changes/phase-3-seat-manifests.yaml` listing each roster file individually, plus acks from all ten consumers.

**B7. TOOL-004 same-transaction approval consumption is deferred to Phase 4, but TOOL-004 is a Phase 3 requirement.**
Evidence: CONTEXT.md Claude's Discretion and deferred notes: "TOOL-004 transaction proof moves to Phase 4"; R23 (upgrade plan line 189) requires consumption "inside the same ledger transaction as the order". `LedgerStore.append` (`src/pumpgrok/ledger/store.py:117-125`) raises on duplicate idempotency keys and has no read-by-key method, so "a repeat returns the first Fill" needs a new read path.
Recommendation: Phase 3 delivers the input contract (decision_id required, idempotency key derived from `(ticket_id, side, decision_id)`, approval_id required, g6 flags) with tests; the atomic consume-and-order proof is deferred. The orchestrator must explicitly accept the partial TOOL-004 coverage; otherwise the planner has to implement a ledger transaction that Phase 4 owns.

**B8. `pumpgrok tools <id> --help` conflicts with the R40 canonical verb list.**
Evidence: CONTEXT.md locks "add `pumpgrok tools <id> --help`". Upgrade plan section 9 item 4 says R40 has no `tools` verb and treats it as a hidden developer verb; its acceptance line uses `uv run pumpgrok tools exec.quote --help`.
Default: implement it (locked CONTEXT wins), as a hidden verb not listed in the top-level help summary, if the orchestrator prefers; otherwise document it in SETUP.md.

**B9. `market.price` backend conflict: catalog says pump.fun REST; R46/R47 say Solana RPC; no RPC bonding-curve decoder exists.**
Evidence: `docs/TOOL_CATALOG.md:54` backend `GET https://frontend-api.pump.fun/coins/{mint}`; `docs/TOOL_CATALOG.md:169` says `onchain.lp_status` reads "JSON-RPC getAccountInfo on the bonding-curve PDA". Locked CONTEXT: "Market reads from Solana RPC (R46)" and R47 says pump.fun REST returns HTTP 530 / error 1016 on all tested paths (STATE.md). Grep for bonding-curve or virtual-reserve decoding in `src/pumpgrok` finds nothing; the only price code is the vendor's `price_from_reserves` (`vendor/grokbot-pumpfun/src/executor.py:85-91`) which reads REST JSON fields `virtual_sol_reserves` and `virtual_token_reserves`.
Consequence: market.price and onchain.lp_status over RPC require a new account-layout decoder. The layout is [ASSUMED] (Anchor-style 8-byte discriminator then five u64 reserve fields and a bool `complete`); it cannot be verified offline and the tests must use hand-authored fixtures. Also: `docs/TOOL_CATALOG.md:54` lists a fallback to `lite-api.jup.ag/swap/v1/quote`, which R44 forbids; the implementation must not use it.
Default: market reads from RPC with the [ASSUMED] layout behind a `curve_layout.py` module and a fixture marked ASSUMED; user confirmation required.

**B10. Bot and skill assignments disagree between two design documents; the current frontmatter follows MIGRATION_MAP 4.2, not interfaces 3.1.**
Evidence: interfaces 3.1 (`docs/design/interfaces.md:1170-1190`) and MIGRATION_MAP 4.2 (`docs/MIGRATION_MAP.md:438-470`) give different `bots` lists. The current frontmatter matches MIGRATION_MAP 4.2 (checked for all 23 skills). Against interfaces 3.1: 15 of 23 `bots` lists differ and 6 `gates` lists differ (e.g. `desk-incident-response` current `bots: all`, 3.1 `bot-00-chief, bot-02-risk`).
More important, 8 skills fail SKILL-002 with the current frontmatter `bots` (which follow MIGRATION_MAP 4.2) because their 3.1 `required_tools` are not granted to every listed bot. Under the 3.1 `bots` lists these eight pass. Examples: `desk-monitoring` (bots chief, rug; requires `risk.halt_status`, `portfolio.exposure`, `exec.positions`; rug holds none of the three), `desk-trade-lifecycle` (bots all; requires `journal.append`, not granted to risk, sniper, rug, exit), `desk-incident-response` (bots all; requires `risk.halt_status`, granted only to chief and risk), `holder-and-flow-analysis` (bots include risk; risk lacks `onchain.top_holders`), `position-monitoring` (bots include exit; exit lacks `onchain.lp_status`), `risk-audit` (bot-02-risk; requires `safety.score_report`, which only rug holds), `solana-rpc-and-wallet` (bots include risk; requires `onchain.priority_fee`, which risk lacks), `desk-post-trade-review` (bots include exit and chief; requires `portfolio.ledger_read`, `portfolio.pnl`, `journal.append`; exit lacks all three and chief lacks `portfolio.ledger_read`).
Resolution rule (recommended): a skill's `bots` = seats whose prompt `<skills>` list contains it (MIGRATION_MAP 4.2 says the prompt XML is the single source) AND that hold every `required_tools` entry; where the intersection is empty or differs, the orchestrator decides. Test SKILL-002 then passes by construction.

**B11. Test naming and existence for the success criteria.**
`tests/test_skill_manifests.py`, `tests/test_bot_manifests.py`, `tests/test_registry_least_privilege.py`, `tests/safety/test_cron_seats_cannot_write.py`, `tests/safety/test_no_manipulation_tools.py` and `tests/tools/` do not exist (verified). `uv run pytest -q -k "least_privilege or gateway"` exits 5 (no tests collected) until matching tests exist in the root test paths (`pyproject.toml` testpaths are `tests` and `ci/tests`).

**B12. TOOL-002 names `solana.rpc_api_key`; the setting is `rpc.api_key`.**
Evidence: `src/pumpgrok/config/settings.py:55-65` (`class RpcSettings`, `endpoints: list[str]`, `api_key: SecretStr`). Env name becomes `PUMPGROK_RPC__API_KEY`. Recommend keeping `rpc.api_key` and correcting the requirement text; needs user confirmation.

**B13. `respx` is required by TOOL-001 but is not in the dev group or `uv.lock`.**
Evidence: `pyproject.toml` `[dependency-groups] dev` lists requests, ruff, mypy, pytest, pytest-asyncio, pip-audit, types-PyYAML; `uv.lock` has no `respx` (grep). The existing convention is `httpx.MockTransport` (`tests/conftest.py` docstring; `tests/characterization/*`). Registry reports `respx` 0.23.1 (`pip index versions respx`), but a registry hit is not a legitimacy check.
Default: use `httpx.MockTransport` and do not add respx; if respx is wanted, add it through the package-legitimacy gate.

## Current state (verified this session)

| Area | State | Evidence |
|------|-------|----------|
| Registry, ToolSpec, ToolInput/Output, Bot/Skill manifests | Implemented, frozen | `src/pumpgrok/core/{registry,tool,bot,skill,side_effect,risk_budget,errors,approvals,adapter,idempotency,ratelimit,datasource}.py` |
| Registered tools | **None** (`tools/__init__.py` is a docstring only) | `src/pumpgrok/tools/__init__.py` |
| Ported read tools (dict outputs) | 4 functions + RpcClient | `tools/onchain/{rpc,authorities,holders,priority_fee}.py`, `tools/market/jupiter.py` |
| Rosters | 11 files present, sizes match R35 | `contracts/tool-rosters/*.yaml`; see section 3.1 |
| Roster manifest fields | Missing (B6) | `contracts/tool-rosters/bot-04-sniper.yaml` top keys |
| Settings | rpc, data, jupiter, risk, live, replay, filter, scoring, exits, ops; **no** notify, safety, tools, social, gateway sections | `src/pumpgrok/config/settings.py:214-237` |
| CLI | 19 verbs; `paper buy|sell` parse all flags and return exit 5 | `src/pumpgrok/cli.py:262-267, 388-401` |
| Skills | 23 directories, all with name, description, bots, gates, L1/L2, Failure modes, References; **no** required_tools or permissions | `skills/*/SKILL.md`; Phase 2 summary 02-05 says "required_tools left empty on all skills" |
| Plugin "23 skills" | 4 hits (plugin.json:4, .claude-plugin/plugin.json:3, .grok-plugin/plugin.json:3, .grok-plugin/marketplace.json:9) | `grep -rn "23 skills" ...` |
| Gateway | **Absent** (B4) | `services/` does not exist |
| Social | **Absent** (`src/pumpgrok/tools/social/` does not exist) | `ls` |
| Gate tests | `tests/test_forbidden_owners.py:88-94` asserts `paper buy` for seat `desk` exits 5 with `not-yet-implemented` (will change) | |
| Checkpoint | `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` passed in Phase 2 (512 tests green) | `02-VERIFICATION.md` |

## 1. Tool modules and the typed dotted registry (TOOL-001..007)

### 1.1 What exists and where it maps

| Existing module (verified) | Current contract | Target catalog tool(s) | Notes |
|---|---|---|---|
| `tools/onchain/rpc.py` `RpcClient.call` | dict/Any return; retries every `httpx.HTTPError` (`rpc.py:125-127`: `retry=retry_if_exception_type(httpx.HTTPError)`), including 4xx; `resp.json()` at `rpc.py:107` is not caught, so a malformed body escapes | shared by all onchain.* | See 2.4 for required changes |
| `tools/onchain/authorities.py` `check_mint` | returns dict with `ok` | `onchain.authorities` | Output keys are pinned by characterization; wrap, do not edit |
| `tools/onchain/holders.py` `holder_snapshot` | dict; `float` ratios and `totalUiAmountSampled` | `onchain.top_holders` (getTokenLargestAccounts); also candidate backend for `market.holders_snapshot` | Catalog `market.holders_snapshot` backend is pump.fun REST (`TOOL_CATALOG.md:114`); see B9 |
| `tools/onchain/priority_fee.py` `estimate_priority_fee` | dict | `onchain.priority_fee` | Keep `recommended_lamports_per_cu` alias as documented |
| `tools/market/jupiter.py` `get_quote` | dict; `ratio: float` (`jupiter.py:73-76`) mapped to `priceImpactRatio` | `exec.quote` (through ExecutionAdapter; B7/B9) | Characterization pins `priceImpactRatio == approx(0.005)` (`tests/characterization/test_jupiter_quote.py:66`) |
| root `tools/*.py` (authority_check, holder_check, jupiter_quote, priority_fee, paper_sim, desk_state, ticket_helper, pipeline_evidence) | oracle | CLI ports (`paper`, `state`, `ticket`) | Remain until Phase 5 (R53; `pyproject.toml` dev comment; `tests/test_tools_cli.py` loads them). Do not delete in Phase 3 |
| `engine/*` | vendor port, characterization-pinned | none directly (seats use engine via pipeline) | Not a tool layer; do not wrap as tools in Phase 3 |

The ported functions must not be edited (characterization pins). The typed tool layer wraps them: a tool's `fn` calls the existing function and converts the dict into the typed output model. Decimal conversion happens in the wrapper (`Decimal(str(value))`), never inside the ported module.

### 1.2 Registry defects that block TOOL-001..007 as written

1. **Namespace resolution refuses early instead of skipping.** `src/pumpgrok/core/registry.py:117-136`: for a prefix capability the loop calls `_refuse(... "exceeds_requested_max")` (line 136) and `_refuse(... "exceeds_grant")` (line 134) on the first candidate that fails, instead of continuing. The find() docstring (`registry.py:98-104`) promises "resolves to the first granted tool in that namespace whose side effect does not exceed max_side_effect". Example: sniper, `find("exec", max_side_effect=READ)` sorted-first candidate `exec.cancel` (PAPER_WRITE) raises even though `exec.quote` (READ) is granted. Fix: for prefix matches, skip (`continue`) on `exceeds_grant` and `exceeds_requested_max`; keep exact-name refusals; keep the LIVE_WRITE refusal (I3) for any candidate.
2. **Retry is refused.** `src/pumpgrok/core/tool.py:88-90` (`_retry_is_not_wired`): `if self.retry.attempts > 1: raise ValueError(...)`. `tests/core/test_registry.py:96-110` (`test_retry_is_refused_until_wired`) asserts this. TOOL-002/008 need j4/j5/j8 on READ tools. Fix: allow attempts > 1 only when `side_effect is READ`; writes keep attempts=1 (catalog: exec.place "retry none"). Update that test to assert the write-side refusal. Wire retry in `_wrap` (`registry.py:186-212`) with `tenacity.AsyncRetrying(sleep=clock.sleep, ...)` and the injected `random.Random` (same pattern as `rpc.py _SeededWait`, which must not use global `random`).
3. **Rate limit is recorded but not enforced.** `tool.py:69` (`rate_limit_key ... # recorded only; no limiter yet`) and `registry.py:207-208` comment. `src/pumpgrok/core/ratelimit.py` `RateLimiter` exists. Wire one limiter per key inside the registry, built from config.
4. **Idempotency derivation does not match R23.** `src/pumpgrok/core/idempotency.py:49-63` `derive_idempotency_key(tool, bot, payload, scope=...)` always includes `tool` and `bot` in the digest. R23 and the catalog require exec.place keyed on `(ticket_id, side, decision_id)` only. Add a separate function `exec_place_key(ticket_id, side, decision_id)` and `exec_cancel_key(order_id)`; do not change `derive_idempotency_key`, because `_skip_cycle` (`cli.py:351-356`) and the replay ledger rely on its current output.
5. **Approval gate does not check the approval.** `registry.py:208-214` calls `limits_checker(req, bot.id)` only. Approval matching (`ApprovalRecord.matches`, `core/approvals.py`) is not enforced by the wrapper; exec.place must do it itself and fail closed. In Phase 3 no ApprovalRecord store exists, so every approval lookup returns "not found".
6. **Limits checker default must fail closed.** The composition root must not inject `lambda ...: True`. Use a checker that returns False (refuse) until RiskEngine lands; the CLI and gateway build the registry through one `build_registry()` function (new, in `src/pumpgrok/tools/__init__.py`).
7. **`ToolSpec.timeout_s` is applied** (`registry.py:209`) through `clock.timeout`; OK.

### 1.3 Tool specs to create (37 catalog tools plus the core eight)

Module layout by catalog suffix (Claude's Discretion; matches upgrade plan 6.3):

| Package | Files | Tools |
|---|---|---|
| `tools/market/` | `price.py`, `ohlcv.py`, `liquidity.py`, `trades.py`, `holders_snapshot.py`, `jupiter.py` (existing) | market.price, ohlcv, liquidity, trades, holders_snapshot |
| `tools/onchain/` | `token_metadata.py`, `authorities.py`, `lp_status.py`, `top_holders.py`, `deployer_history.py`, `large_transfers.py`, `priority_fee.py`, `rpc.py`, `holders.py` (existing) | onchain.* (7) |
| `tools/safety/` | `score_report.py`, `checks/*.py` | safety.score_report (45 s timeout); thresholds from a new `safety` config section (see 1.6) |
| `tools/exec/` | `quote.py`, `simulate.py`, `place.py`, `cancel.py`, `positions.py` | exec.* (5) against `ExecutionAdapter`; NotYetImplementedAdapter in Phase 3 |
| `tools/portfolio/` | `ledger_read.py`, `ledger_write.py`, `exposure.py`, `pnl.py` | portfolio.* (4); ledger_write wraps `LedgerStore.append` (`ledger/store.py:117`) |
| `tools/risk/` | `check_limits.py`, `drawdown.py`, `kill_switch.py`, `halt_status.py` | risk.* (4) |
| `tools/journal/` | `append.py`, `render_report.py` | journal.* (2) |
| `tools/notify/` | `alert.py`, `telegram.py`, `webhook.py`, `allowlist.py`, `notifier.py` (abstract) | notify.alert (1) |
| `tools/desk/` | `brief.py`, `docs_search.py`, `memory_retain.py`, `memory_recall.py`, `ownership_resolve.py`, `receipt_check.py`, `event_emit.py`, `doctor.py` | desk.* core eight (8) |
| `tools/social/` | GET-only client module(s) | see blocker B14 / section 5 |

**B14 (new blocker): `tools/social/` has no catalog tool.** TOOL_CATALOG has no `social.*` section and the shill roster (`bot-07-shill.yaml`) grants only `onchain.token_metadata`, `market.trades`, `journal.append`. SC4 requires the directory to exist (its grep is non-vacuous only if it exists; see section 5.3). Options: (a) put the pump.fun GET client used by `market.trades`/`onchain.token_metadata` metadata enrichment under `tools/social/` (name is then a misnomer; ROSTER section 5.8 says shill is "social sentiment detection only"); (b) create a real read-only social-data client with no registered tool (a module with no caller is scaffolding and violates the completeness contract); (c) add a `social.*` catalog tool (catalog change, out of Phase 3 scope). Needs orchestrator decision.

Each spec is one `ToolSpec(...)` with: `name` (dotted), `description` (10-1000 chars), `input_model` (ToolInput subclass, extra forbid), `output_model` (ToolOutput subclass with `meta: ToolMeta`), `side_effect` (READ or PAPER_WRITE only), `timeout_s` (from catalog table), `retry` (RetryPolicy: `none` for paper-write; `jitter(3,0.5,4)`, `jitter(3,0.5,5)`, `jitter(3,1,8)` for j4/j5/j8 READ tools), `rate_limit_key` (catalog key; pattern `^[a-z][a-z0-9_]*$`), `requires_approval` (True for exec.place, exec.cancel per g6), `idempotent` (True for every write), `backend` (module path).

Registration: `ToolRegistry.register_all` (`registry.py:~85`). Duplicate names raise `ValueError` (existing).

### 1.4 Execution tools and the unimplemented adapter

- `ExecutionAdapter` protocol (`core/adapter.py`) has `quote`, `simulate`, `place`, `cancel`, `positions`.
- Phase 3 `NotYetImplementedAdapter` (new, `src/pumpgrok/execution/`): every method raises a `PumpgrokError` subclass with code `not_yet_implemented`. It MUST NOT return fake fills or quotes (completeness contract). Under `execution/`, the signing-symbol AST guard (section 2.4) applies.
- exec.quote: informational Jupiter quote path (R44) is a read-only HTTP call. Decide in planning whether exec.quote delegates to the adapter (raises until Phase 4) or to `tools/market/jupiter.get_quote`; CONTEXT says the adapter, so default to the adapter.
- exec.place validation that must exist in Phase 3 regardless of the adapter: `ticket_id` pattern (`OrderRequest` already encodes it, `core/adapter.py`), `decision_id` ULID (`ULID_RE`), size fields match side (`OrderRequest._size_matches_side`), `approval_id` pattern `^apr-[0-9A-HJKMNP-TV-Z]{26}$` (`core/adapter.py`), and the seat rule "exit cannot place BUY": implement as `bot.risk_budget.may_open_exposure` (`src/pumpgrok/core/risk_budget.py`, property already exists) returning False for exit, refusing with rule id `seat_may_trade`.
- exec.cancel: adapter reads decision_id from the order (CONTEXT discretion); key `exec_cancel_key(order_id)`.
- exec.simulate: no ledger write (TOOL-004).

### 1.5 Portfolio, risk, journal, notify, desk tools

- `risk.kill_switch` input: `action: Literal["set", "flatten_request"]` only (R22). No `clear` in the model; a validation error on any other value is the test (interfaces 4 `test_kill_switch_tool_has_no_clear_action`). Note `contracts/tool-rosters/bot-02-risk.yaml` `risk.kill_switch` declares `gates: []` (no g6), which G-7 accepts (`ci/gates/check_desk_integrity.py:59-66`), but `contracts/README.md` says write tools need g6; the README is stale. Choose: keep roster, fix README (planner decision).
- `journal.append` / `desk.event_emit`: `kind` is a `Literal` of exactly `journal_note` and `escalation` for seats (I5). Engine-only kinds are not accepted.
- `notify.alert` alert kinds enum: must include `bot_restart_exhausted, heartbeat_stale, persistence_down, clock_skew, ledger_inconsistent` (TOOL-006, R40) plus the seat-emitted `escalation` relay kinds. `docs/TOOL_CATALOG.md` section 7 (line 480-497) is the authoritative list; read it at planning time.
- `desk.doctor check` must be the same code path as `pumpgrok doctor` (TOOL-007). Current `doctor_report(settings)` (`src/pumpgrok/doctor.py`) prints text lines; the tool must call the same function and return structured rows. The catalog marks `desk.doctor` as paper-write (`TOOL_CATALOG` section 9; `_core.yaml`); keep it, because `check` would otherwise need a read/write split.

### 1.6 Config additions required (new sections; each needs overlay, forbidden-key and settings tests)

| Section | Keys | Source |
|---|---|---|
| `notify` | `allowlist` (telegram chat ids, webhook URLs); empty means stdout and file only | R39; TOOL_CATALOG "notify.allowlist config key name and shape [INFERENCE]" (line ~540) |
| `safety` | thresholds for score_report checks | TOOL-003 "thresholds read from config" |
| `tools` (optional) | timeouts/rate limits | catalog says "all are config fields under tools.<name>" [INFERENCE]; recommend keeping timeout_s in code (catalog table) to avoid drift |
| `live` | unchanged | - |

Secrets stay env-only: Telegram token via env (not TOML); `JUPITER_API_KEY` is read in the composition root (`tools/market/jupiter.py:resolve_api_key`) and must stay out of Settings. `FORBIDDEN_SUBSTRINGS` (`src/pumpgrok/config/settings.py:153-161`) covers PRIVATE_KEY, SECRET_KEY, SEED, MNEMONIC, PHANTOM, WALLET_SECRET, KEYPAIR. Names such as `PUMPGROK_TELEGRAM_TOKEN` or `DESK_GATEWAY_TOKEN_*` do not contain those fragments and are allowed.

## 2. Schema and money typing (TOOL-008)

### 2.1 Base models (exist)

- `ToolInput` (`core/tool.py:43-48`): `ConfigDict(extra="forbid", frozen=True)`, field `correlation_id: str | None`.
- `ToolOutput` (`core/tool.py:51-54`): `extra="forbid"`, field `meta: ToolMeta`.
- `ToolMeta` (`core/tool.py:32-40`): `source`, `fetched_at: datetime`, `freshness_s: float (>=0)`, `correlation_id`, `stale: bool`, `reason`. `freshness_s` is a time, not money; float is allowed there.
- `ToolSpec.input_json_schema()` forces `additionalProperties: false` (`tool.py:93-96`).
- `OrderRequest`, `Quote`, `SimulationResult`, `Fill`, `Position` (`core/adapter.py`) already use `int` for `*_lamports`/`*_units` and `Decimal` for prices/ratios. Reuse them as the exec tool contracts.
- `ApprovalRecord` (`core/approvals.py`): `extra="forbid"`; amounts `size_lamports`, `token_units` as int.

### 2.2 Required additions

- `UpstreamModel(BaseModel)` with `model_config = ConfigDict(extra="ignore")` for parsing pump.fun, PumpPortal, Jupiter, RPC and x.ai payloads (TOOL-008). Each DataSource parse maps `pydantic.ValidationError` or `TypeError/ValueError` to `DataStale` (last good value available) or `DataBlind` (none). Never let a validation error escape a tool (`src/pumpgrok/core/errors.py` defines both codes).
- Output models: money as `int` named `*_lamports` / `*_units`; prices and ratios as `Decimal`. `model_dump(mode="json")` serializes Decimal as a JSON string. `canonical_json` (`core/idempotency.py`) already converts Decimal to str and rejects float leaves (`_normalize`, lines ~20-30). Tests must assert `canonical_json` raises on any float.
- `RetryPolicy` (`core/tool.py:16-29`) has `base_s: float` and `max_s: float`. These are seconds, not money (allowed). Document that in the model docstring.

### 2.3 Float inventory (what the SC5 grep matches and what it does not)

- Grep-matching (see B1): 9 lines (cli.py:120; engine models 49, 50, 85, 264; reputation 56, 147; tune 40).
- Non-matching floats that TOOL-008 still forbids for money: `tools/market/jupiter.py:73-76` (`ratio: float`; output `priceImpactRatio` pinned), `tools/onchain/holders.py:26` (`ui = float(...)`; `totalUiAmountSampled` pinned, `top1Pct` pinned at `test_holder_check.py:54`), `tools/onchain/priority_fee.py` (int, fine), `engine/*` floats (vendor parity). The typed tool layer converts these to Decimal strings at the boundary; the ported functions keep floats because characterization pins them.
- CLI: `_size_sol(value: str) -> float` (`cli.py:94`) parses SOL; `size_sol_to_lamports(size_sol: float)` (`cli.py:120`) converts with `Decimal(str(size_sol))` (correct rounding per WR-05, but typed float). Change the parameter to `Decimal` (or str), keep `ROUND_HALF_UP`. This removes one grep hit and is the only place `--size-sol` is converted (R28).

### 2.4 Retry, failover and redaction in `rpc.py` (TOOL-002)

Required changes to `src/pumpgrok/tools/onchain/rpc.py` (verified current behavior):
1. Retry classification: retry only on timeouts, HTTP 5xx and 429 (catalog section 0 and vendor precedent). Current code (`rpc.py:127`) retries every `httpx.HTTPError`, including 4xx `HTTPStatusError`. Fix with a predicate.
2. Policy values: current `_SeededWait(base=0.1, cap=5.0)` (`rpc.py:52`) does not match `jitter(n, base_s, max_s)`; take base and max from the tool's `RetryPolicy` (j4 base 0.5 max 4; j5 base 0.5 max 5; j8 base 1 max 8) and attempts from `n`.
3. Decode failures: `resp.json()` (`rpc.py:107`) can raise `json.JSONDecodeError` (a `ValueError`), which `call()` does not catch (`rpc.py:137` catches only `httpx.HTTPError` and `RetryError`). Convert to a typed failover or `DataStale`.
4. Key handling: `api_key` travels as `x-api-key` header (`rpc.py:_headers`); never in the URL. Keep. Settings path is `rpc.api_key` (B12).
5. Failover: ordered over `rpc.endpoints` (`settings.py:64`); RPC JSON error fails over immediately (`rpc.py:132-134`); keep.

### 2.5 Signing guard constraints on the new code (applies to all of src/pumpgrok)

`tests/safety/test_no_signing_outside_live_stub.py:25-30` forbids: names `sign`, `send_transaction`, `sendTransaction`, `Keypair` anywhere (function names, arguments, keyword names and string literals, see `_names` lines ~38-55); imports of `solders` or `solana`; in `execution/live/live_adapter.py` only, the names `Transaction`, `VersionedTransaction`, `Message`. Consequences: a parameter named `sign` or a literal `"sign"` (e.g. a field name in a JSON schema description) fails the test. The notify module must avoid `sign` in HMAC helpers; name them `digest_*`.

## 3. Least-privilege rosters, manifests and the cron-seat guard (TOOL-009, TOOL-007, SKILL-003)

### 3.1 Roster audit against R35 (verified)

| Seat | Own tools (file) | Core | Effective | R35 target | Status |
|---|---|---|---|---|---|
| chief | 7 (exec.positions, portfolio.exposure, portfolio.pnl, risk.check_limits, risk.halt_status, notify.alert, journal.append) | 8 | 15 | 15 | count ok; B3 wording |
| scout | 7 (market.price, market.liquidity, market.trades, market.holders_snapshot, onchain.token_metadata, onchain.authorities, journal.append) | 8 | 15 | 15 | ok |
| risk | 7 (portfolio.ledger_read, exposure, pnl, risk.check_limits, drawdown, halt_status, kill_switch) | 8 | 15 | 15 | ok; kill_switch only here |
| whale | 6 (onchain.top_holders, deployer_history, large_transfers, market.trades, market.holders_snapshot, journal.append) | 8 | 14 | 14 | ok |
| sniper | 7 (market.price, exec.quote, exec.simulate, exec.place g6, exec.cancel g6, exec.positions, onchain.priority_fee) | 8 | 15 | 15 | ok |
| rug | 7 (market.price, market.liquidity, onchain.token_metadata, onchain.authorities, onchain.lp_status, onchain.top_holders, safety.score_report) | 8 | 15 | 15 | ok |
| exit | 7 (same exec set as sniper plus market.price, priority_fee) | 8 | 15 | 15 | ok; BUY refused by budget (1.4) |
| shill | 3 (onchain.token_metadata, market.trades, journal.append) | 8 | 11 | 11 | ok |
| signal | 6 (market.price, ohlcv, liquidity, trades, holders_snapshot, journal.append) | 8 | 14 | 14 | ok |
| journal | 7 (exec.positions, portfolio.ledger_read, exposure, pnl, notify.alert, journal.append, journal.render_report) | 8 | 15 | 15 | ok |

Counts were read from `contracts/tool-rosters/bot-*.yaml` `tools:` lists (the top-level `- name:` lines). `contracts/README.md` (roster table) agrees.

Existing invariant check that the planner must keep green: `python3 ci/gates/check_desk_integrity.py --repo .` (G-7) enforces 8..15 tools (`ROSTER_MIN_TOOLS = 8`, `ROSTER_MAX_TOOLS = 15`, lines 41-42), dotted names, `additionalProperties: false`, and no `exec.live*` name (`LIVE_TOOL_PREFIX`, line 50).

### 3.2 BotManifest loader (SKILL-003; blocker B6)

- Loader: `src/pumpgrok/core/manifests.py` (new): `load_bot_manifests(contracts_dir: Path) -> dict[str, BotManifest]`. Reads each `bot-*.yaml` (`yaml.safe_load`), merges `_core.yaml` tools into `allowed_tools` (ToolGrant name plus side_effect, from each tool's `side_effect` field), validates with `BotManifest.model_validate`. Fails closed on any error (no silent skip).
- `BotManifest` validator (`core/bot.py:76-93`): paper-write `exec.*` only for `bot-04-sniper` and `bot-06-exit`; `writes_to_exchange` must be True for them; `risk.kill_switch` only for `bot-02-risk`; `notify.alert` refused for `bot-02-risk` and `bot-05-rug`; `portfolio.ledger_write` refused everywhere. Existing roster data satisfies these (verified above).
- R20 risk_budget keys: each seat manifest needs all nine keys (`RiskBudget` defaults cover missing keys; the SKILL-003 test must assert presence explicitly, since defaults hide absence). Trade keys 0 for seats that never trade (ROSTER section 5).
- `writes_to_exchange` true only for sniper and exit (SKILL-003).
- Test: `tests/test_bot_manifests.py` asserts exactly ten manifests, ids `bot-00-chief`..`bot-09-journal` (SEAT_RE), R35 sizes, RISK = RUG = 15, `forbidden` non-empty, `risk_budget` nine keys.

### 3.3 Least-privilege suite (TOOL-009) on the registry

Files: `tests/test_registry_least_privilege.py` (name fixed by interfaces 4 and ROADMAP SC3 `-k least_privilege`). Test names from interfaces 4, each to be implemented:

- `test_no_bot_resolves_live_write`: for every manifest, `find(name, max_side_effect=PAPER_WRITE, bot=m)` raises `LiveGateError` for a LIVE_WRITE spec; an audit row with `reason == "live_write_never_resolvable"` (I3, I4). Needs a probe `exec.live_place` registered in the test registry only (the real registry must not contain a live tool; keep `register()`'s warning path).
- `test_sniper_cannot_resolve_kill_switch`: `find("risk.kill_switch", ...)` raises `PermissionDenied`, `reason == "not_in_roster"`.
- `test_only_sniper_and_exit_resolve_exec_place`: for the ten seats, resolve succeeds only for sniper and exit.
- `test_exit_cannot_place_buy`: exit `exec.place` with `side=buy` refused, rule `seat_may_trade` (section 1.4).
- `test_chief_has_no_exposure_tools` (interfaces wording): chief cannot resolve `exec.place`, `exec.cancel`, any `market.*` (per B3).
- `test_shill_has_no_write_except_journal`: shill's only paper-write grant is `journal.append`.
- `test_nobody_resolves_ledger_write`: `portfolio.ledger_write` raises for all ten seats (PermissionDenied: not granted, or unknown tool if not registered; the test must say which).
- `test_kill_switch_tool_has_no_clear_action`: input model accepts only `set`, `flatten_request`.
- `test_manifest_tools_subset_of_registry`: every `allowed_tools[].name` is registered.
- `test_grant_side_effect_never_exceeds_spec`.
- `test_live_write_audited_and_alerted`: audit row present; "and alerted" needs the notify path (`notify.alert severity critical`); Phase 3 can assert the audit row only and must say so in the test docstring (alert wiring is Phase 4).
- `test_every_roster_name_exists_in_registry` (TOOL-009 last clause).

Registry helper used by tests: build the registry through `build_registry(...)` (section 1.2 item 6) with a `FixtureClock` (`src/pumpgrok/replay/clock.py`) and a list-backed audit sink.

### 3.4 Cron-seat guard (R63; `tests/safety/test_cron_seats_cannot_write.py`)

Model: a cron-owned invocation of sniper or exit is resolved with `max_side_effect=SideEffect.READ` (B2, reconciling reading). Test:

1. For `bot-04-sniper` and `bot-06-exit`, and for every registered tool whose `side_effect` is PAPER_WRITE: `find(name, max_side_effect=READ, bot=m)` raises `PermissionDenied` (reason `exceeds_requested_max`). This is the "cannot resolve any paper-write tool" clause.
2. `find("portfolio.ledger_write", ...)` raises for every seat (R63 and TOOL-005).
3. Non-vacuity: `find("exec.place", max_side_effect=PAPER_WRITE, bot=sniper)` resolves, and the same with exit (otherwise (1) could pass because nothing is granted).
4. CLI half: `main(["paper", "buy", "--ticket", T, "--mint", M, "--size-sol", "0.5", "--slippage-bps", "100", "--approval-id", A, "--seat", seat])` for seat in `{sniper, exit, bot-00-chief, desk}` with a well-formed `A` absent from the ledger returns exit 1 and writes no `OrderPlaced` row (assert ledger row count unchanged). Keep `--seat` refusal for sniper/exit (existing `_refuse_forbidden_seat`, `cli.py:134-139`); the approval rejection is the control that matters (R63).
5. A paper buy without `--approval-id` is rejected by argparse (`cli.py:168-173`; `UsageError` exit 1).

Existing test to migrate: `tests/test_forbidden_owners.py::test_allowed_seat_reaches_absent_verb` (lines 88-94) asserts exit 5 for `paper buy --seat desk`. Under Phase 3 that path becomes an approval rejection (exit 1). The planner must update this test and say so in the plan; it is a Phase 2 test that the change invalidates.

### 3.5 Registry test that changes

`tests/core/test_registry.py:96-110` (`test_retry_is_refused_until_wired`) becomes "write tools refuse attempts > 1; READ tools accept attempts 3". Flag the change in the plan.

## 4. Desk gateway (TOOL-010)

### 4.1 Layout (new; owner bot-00-chief per `ownership.yaml`)

```
services/desk-gateway/
  pyproject.toml          # own project; deps: pumpgrok (path ../..), pydantic, pyyaml; dev: pytest, pytest-asyncio
  uv.lock                 # committed
  src/desk_gateway/
    __init__.py
    config.py             # per-seat token env names; no secrets in code
    server.py             # HTTP + JSON-RPC handler; no tool logic
  tests/
    conftest.py
    test_auth.py
    test_tools_list.py
    test_transport_names.py
    test_call_dispatch.py
```

Upgrade plan 3E lists `src/desk_gateway/tools/core.py`; "tools/core" would hold tool logic, which D2 forbids. Do not create it; the desk core tools live in `src/pumpgrok/tools/desk/`.

### 4.2 Behaviour (TOOL-010)

- Endpoint: `POST /mcp/<short>` where `<short>` is the roster `short` (chief, scout, risk, whale, sniper, rug, exit, shill, signal, journal). Roster `endpoint` must equal `/mcp/<short>` (checked by G-7, `contracts/README.md`).
- Authentication: `Authorization: Bearer <token>`. For the presented token, compare against each seat's expected token with `hmac.compare_digest` (constant-time, loop over all seats so the matched seat does not leak through timing). Outcomes: no seat matches, 401; matched seat is not the path seat, **403** (TOOL-010); matched seat equals path seat, proceed. A seat with no configured token fails closed (its path returns 503 with no token detail).
- Token source: env only, one variable per seat, e.g. `DESK_GATEWAY_TOKEN_SNIPER`. Names must not contain the forbidden fragments (section 1.6). Tokens are never logged; log the seat short name and status code only.
- Methods: JSON-RPC 2.0 over POST with `application/json` responses: `initialize`, `notifications/initialized` (no response body), `tools/list`, `tools/call`. Other methods return JSON-RPC error -32601. GET and other verbs return 405.
- `tools/list`: effective roster = core eight plus the seat's own tools from the roster files (`contracts/tool-rosters/_core.yaml` and `bot-*.yaml`). Each entry: `name` = transport name (`name.replace(".", "_")`), `description` from the roster, `inputSchema` = the roster's `input` block (source of truth for G-7 gates; verbatim). Equality test: the set of transport names equals the set derived from the two YAML files for that seat.
- `tools/call`: the transport name is mapped back to the dotted id through a dict built from the seat's roster. **Never reverse by `replace("_", ".")`**: names contain underscores (`onchain.token_metadata`, `risk.check_limits`), so the reverse mapping is ambiguous. Then `registry.find(dotted, max_side_effect=PAPER_WRITE, bot=manifest)` and run the tool with a bound correlation id. A `PumpgrokError` returns an MCP result with `isError: true` and the error code (no stack, no path).
- Transport name uniqueness: a registry-wide test asserts that the `.`-to-`_` mapping is injective over all registered tools (no two dotted names collide).
- Phase 3 `tools/call` will mostly return `not_yet_implemented` for exec/portfolio/risk tools; that is correct and must be asserted, not hidden.

### 4.3 Why stdlib HTTP (recommendation; needs orchestrator confirmation)

- Adding `mcp`, `starlette` or `uvicorn` adds dependencies that need a package-legitimacy check. `uv.lock` (root) contains none of `mcp`, `starlette`, `fastapi`, `uvicorn` (grep, verified). `pip index versions mcp` reports 2.3.0 (registry only, not a legitimacy check).
- Recommended: `http.server.ThreadingHTTPServer` plus `asyncio.run` per request for the async registry. No new third-party packages. Shape of JSON-RPC is simple.
- The gateway uses `pumpgrok.replay.clock.WallClock` (the only allowed time source inside `src/pumpgrok`; the gateway lives outside `src/` so the AST guard does not scan it, but use the same Clock to keep replay semantics).

### 4.4 Test invocation and root-level selectors

- `pyproject.toml` `testpaths` for root is `["tests", "ci/tests"]` (verified), so `services/desk-gateway/tests` is not collected by root `uv run pytest -q`. The gateway suite runs as `cd services/desk-gateway && uv sync --frozen && uv run pytest -q` (ROADMAP SC3 wording "passes under uv run pytest -q" is read as this).
- `uv run pytest -q -k "least_privilege or gateway"` runs from root and must collect at least one gateway-named test in root `tests/`: add `tests/test_gateway_projection.py` that imports the pumpgrok-side projection helper (`effective_roster(seat)` and transport-name map) from `src/pumpgrok/contracts/` or `src/pumpgrok/core/manifests.py`, so the projection logic is unit-tested in the root suite and the service only serves it. If the projection lives only in the service, root `-k gateway` collects nothing and exits 5.
- Root gateway projection test also verifies that the roster-to-transport mapping is injective.

### 4.5 Secret-gate constraints for gateway fixtures

`ci/gates/check_secrets.py` flags a quoted value of 20+ characters with Shannon entropy above 3.5 on any line that names a secret-like variable (`SECRET_NAME_RE`, lines 82-87: names containing secret, password, token, api_key, auth, credential, etc.). Keep test token literals under 20 characters, or use a value matching `PLACEHOLDER_RE` (lines 91-95), e.g. `fake_token_chief` (`fake[_-]?\w*` matches; a hyphen is not in `\w`, so use underscores). Do not assemble secret-looking literals at runtime to evade the gate; the literal value must be a placeholder.

## 5. Social GET-only constraint and the grep check (TOOL-009, TOOL-011, RISK-007 skeleton)

### 5.1 Constraint

- D7/R31/R39: `src/pumpgrok/tools/social/` issues GET requests only. No POST client; no method named post, put, patch or delete; no `httpx.AsyncClient.post|put|patch|delete` call sites; no `method=` argument with a write verb.
- `tests/safety/test_no_manipulation_tools.py` is a skeleton in Phase 3 (upgrade plan 3F; completed by RISK-007 in Phase 5). The skeleton asserts the static grep and AST scan over `src/pumpgrok/tools/social/`, `tools/notify/` and registered tool names (`post|reply|like|follow|dm|broadcast|wash|volume`, upgrade plan RISK-007 text).

### 5.2 The SC4 grep (literal)

`! grep -rnE "\b(post|put|patch|delete)\b|method=['\"](POST|PUT|PATCH|DELETE)" src/pumpgrok/tools/social/`

Notes for the planner:
- `\b(post)\b` also matches the word "post" in comments and docstrings ("post-trade", "post-graduation"). Keep those words out of the social module's text, or the check fails on prose.
- The pattern is case-sensitive for the bare words; `client.post(` is caught; `method="POST"` is caught by the second alternative.

### 5.3 Non-vacuity (required fix)

Verified: with `src/pumpgrok/tools/social/` absent, `grep -rnE ... ` exits 2 (error), so `!` makes the command exit 0 while printing "No such file or directory" to stderr. The ROADMAP text says "prints nothing". Fix: create the directory with real content (B14) and make the check non-vacuous in the test suite: `tests/safety/test_no_manipulation_tools.py` asserts `SOCIAL.is_dir()` and that at least one `.py` file exists before scanning. The shell command in SC4 cannot be made non-vacuous by itself; flag this in the plan.

## 6. Notify, CLI wrappers and operator verbs (TOOL-006, TOOL-011)

### 6.1 Notify (TOOL-006)

- Abstract `Notifier` (`tools/notify/notifier.py`): `async send(alert) -> SendResult`. Sinks: stdout (always), file (always, `var/` path), Telegram and webhook (only when config `notify.allowlist` contains the destination).
- Telegram token: env var (e.g. `PUMPGROK_TELEGRAM_TOKEN`, catalog section 7 unverified item; hermes profile `chief` holds the token). Not in TOML.
- Idempotency: `d(kind, ticket, severity, minute)` (catalog). `minute` from Clock. Derive with a dedicated function (section 1.2 item 4), not `derive_idempotency_key`, to keep exact semantics.
- Rate limit: `notify` key with j8 retry (jitter(3,1,8)) per catalog; network sink retry only on timeout/5xx/429.
- RISK and RUG rosters never carry `notify.alert` (validator in `core/bot.py`); they escalate via `desk.event_emit kind=escalation`, and the supervisor relay is Phase 4 (note in plan).

### 6.2 CLI (TOOL-011) gaps verified in `src/pumpgrok/cli.py`

| Required (catalog section 12, R22, R40) | Current | Change |
|---|---|---|
| `paper buy|sell --ticket --mint --size-sol --slippage-bps --approval-id` | flags present (`cli.py:150-173`); returns exit 5 (`cli.py:388-401`) | call exec.simulate then exec.place through registry; approval rejection (section 3.4) |
| `killswitch set --reason` | `set` has no args (`cli.py:259`) | add `--reason` (required) |
| `killswitch flatten --reason` | verb missing | add |
| `killswitch clear --by --reason` | `clear` has no args (`cli.py:260`) | add `--by`, `--reason`; human-only; no tool (R22); write ApprovalRecord kind `killswitch_clear` in Phase 4, return not-yet-implemented in Phase 3 |
| `state halt --clear --by --reason` | present (`cli.py:245-247`) | keep |
| `tools <id> --help` | missing | add hidden verb (B8) |
| all verbs JSON by default | `doctor` and `run` print text lines | decision: JSON default for section-12 wrappers; keep text for `run` (replay checkpoint prints `engine decision=`) and document; flag to orchestrator |

Forbidden-owner check `_refuse_forbidden_seat` (`cli.py:134-139`) returns exit 1 with `refused:` on stderr; `test_forbidden_owners.py` asserts that string; keep the message.

### 6.3 Wrapper design

- Thin: each verb builds a typed input model from argv, calls `registry.find(<tool>, max_side_effect=..., bot=<seat manifest>)`, awaits, prints `model_dump(mode="json")` as one JSON object. Errors print the `PumpgrokError` code and message in the JSON envelope, exit code from the mapping in `cli.py` docstring (0,1,2,3,4,5).
- The CLI must not import tool implementations directly; it goes through the registry (keeps I1 enforced on every verb).
- `_size_sol` parses to `Decimal`; conversion once (section 2.3).

## 7. Skills and manifests (SKILL-001..004)

### 7.1 Manifest model (exists)

`SkillManifest` (`src/pumpgrok/core/skill.py:32-52`): `name` pattern `^[a-z][a-z0-9-]{1,60}$`; `description` 1-1024 chars; `bots` non-empty, each `all` or starting `bot-0`; `gates`, `required_tools`, `required_data`, `fixtures` lists; `permissions: SkillPermissions` (`max_side_effect` default READ, validator refuses LIVE_WRITE; `network`; `filesystem` in none/var/repo). `extra="forbid"`.

Note `required_data` values must be DataSource names (`core/datasource.py` docstring: `'pumpfun_rest' | 'pumpportal_ws' | 'jupiter' | 'solana_rpc' | 'xai_grok'`). Interfaces 3.2 `paper-broker` uses `jupiter_lite`; that name is forbidden by R44. Use `jupiter`.

### 7.2 Test design

`tests/test_skill_manifests.py`:
- Enumerate `skills/*/` directories (README.md is a file, skip it). Expect exactly 35 (ROADMAP SC2).
- Parse each `SKILL.md` frontmatter (between the first two `---` lines, `yaml.safe_load`; pyyaml is a dependency). Validate with `SkillManifest.model_validate`.
- `name == dirname`; `len(description) <= 1024`; body `<= 350` lines (also `scripts/check.sh` rule); L1, L2, Failure modes, References headings present.
- `required_tools` each registered (exact name) and granted to every bot in `bots` (expand `all` to the ten seat ids). Fails today for B10 skills.
- `permissions.max_side_effect != LIVE_WRITE` (validator), and `fixtures` paths exist.
- The 12 new names from interfaces 3.2 exist.

### 7.3 Retrofit of 23 existing skills

- Add `required_tools` (interfaces 3.1 column) and `permissions` (`max_side_effect: paper-write` for skills that name write tools, else read) to each frontmatter. Keep existing bodies except where content references Phase 2 names.
- Resolve bots/gates per B10 before editing.
- Mandatory text fixes: remove `jupiter_lite` (R44); the 3.1 table row for `solana-market-data` says "Jupiter lite-api"; that phrase must not be copied into the skill body (STRUCT-007 grep `! grep -rn -e lite-api -e '--max-micro' skills/`).

### 7.4 New skills (12) and grants check

Per interfaces 3.2 (bots, gates, required_tools). Grant check against the rosters in this repo (verified):

| Skill | bots | gates | required_tools | grants satisfied by bots |
|---|---|---|---|---|
| verification-receipts | all | G-2 | desk.receipt_check | yes (core) |
| paper-broker | bot-04-sniper, bot-06-exit | G-2, G-6 | exec.quote, exec.simulate, exec.place, exec.cancel, exec.positions, market.price, onchain.priority_fee | yes both |
| replay-and-backtest | bot-08-signal, bot-06-exit | G-2 | none | yes |
| live-gate-procedure | bot-02-risk, bot-00-chief | G-2, G-6 | risk.halt_status | yes both |
| kill-switch | bot-02-risk, bot-00-chief | G-2, G-6 | risk.halt_status | yes both (chief must not get risk.kill_switch) |
| rpc-hygiene | scout, whale, sniper, rug, exit | none | none | yes |
| key-custody | bot-02-risk, bot-04-sniper, bot-06-exit | G-3 | none | yes |
| safety-scoring | bot-05-rug | G-2 | safety.score_report | yes |
| momentum-signals | bot-08-signal | G-2 | market.ohlcv, market.trades, market.holders_snapshot | yes |
| portfolio-ledger | bot-09-journal, bot-02-risk | G-2 | portfolio.ledger_read, portfolio.exposure, portfolio.pnl | yes both |
| daily-report | bot-09-journal | G-2 | journal.render_report | yes |
| desk-doctor | all | G-7 | desk.doctor | yes (core) |

Body: L1 Summary, L2 Method (numbered S1..Sn steps naming `pumpgrok ...` verbs or catalog tool names), Failure modes table, References. ASCII only. Under 350 lines.

### 7.5 Prompts, agents, plugins (SKILL-004)

- Seat prompt sources (`prompts/bot-*.xml`) have `<skills><skill>...</skill></skills>` (e.g. `prompts/bot-04-sniper.xml:7-14`) and no `<tools contract=...>` element and no `load` attribute. `scripts/prompt_sources.py:121-126` reads only `skills/skill` text. Extend the loader to accept `load="always"` (default) on `<skill>` and a `<tools contract="contracts/tool-rosters/<seat>.yaml"/>` element; emit it in `prompts-assembled/*.xml` (assembled output already renders `<roster endpoint=... effective-tools=...>` at `prompts-assembled/SNIPER.xml:70`, so add the `contract` attribute there).
- `agents/<seat>.md` is generated by `scripts/generate-templates.py` from the same prompt source (`agents/sniper.md` frontmatter `skills:` list matches the prompt today). After editing prompts run `bash scripts/assemble-prompts.sh` and `python3 scripts/generate-templates.py` (both `--check` modes are part of `make check`).
- Plugins: replace "23 skills" with "35 skills" in the four files (section 0 summary). `.cursor-plugin/plugin.json` has no count string (verified).
- `skills/README.md` (a file): update "Twenty-three" and the tables to 35 (3G).
- README.md lines 5 and 12 say "23 skills"; not in SC2's grep but is the same stale claim; update (planner decision; recommended).

## Validation Architecture

### 8.1 ROADMAP Phase 3 success criteria: literal commands, what each proves, and status today

Commands are copied verbatim from `.planning/ROADMAP.md` Phase 3 "Success Criteria". "Status today" was checked by reading the repository and was not executed (no builds or tests were run for this research).

**SC1** (SKILL-002, SKILL-003): `uv run pytest -q tests/test_skill_manifests.py tests/test_bot_manifests.py` exits 0
- Proves: every SKILL.md parses into SkillManifest with name==dirname; required_tools granted to listed bots; exactly ten BotManifests from the roster files with R35 sizes and nine R20 risk keys.
- Status today: FAILS (files do not exist; pytest reports file not found, exit 4). Blockers B6, B10 must be resolved first.

**SC2** (SKILL-001, SKILL-004): `test "$(ls -d skills/*/ | wc -l)" -eq 35` and `grep -q 'bot-09-journal' skills/desk-post-trade-review/SKILL.md` both exit 0, and `! grep -rn "23 skills" plugin.json .claude-plugin .grok-plugin .cursor-plugin agents` prints nothing
- Proves: 35 skill directories; journal ownership string present; no stale "23 skills" in plugin manifests and agents.
- Status today: FAILS on the first clause (23 directories) and the third clause (4 hits: plugin.json:4, .claude-plugin/plugin.json:3, .grok-plugin/plugin.json:3, .grok-plugin/marketplace.json:9). The second clause passes (1 match).

**SC3** (TOOL-009, TOOL-010): `uv run pytest -q -k "least_privilege or gateway"` exits 0, and the desk gateway suite in `services/desk-gateway/` passes under `uv run pytest -q`
- Proves: least-privilege invariants on the registry; gateway serves tools/list = roster + core, 403 on cross-seat tokens.
- Status today: FAILS (no matching tests; `-k` collects zero and pytest exits 5; `services/desk-gateway/` absent). Run the gateway suite as `cd services/desk-gateway && uv run pytest -q` (section 4.4).

**SC4** (TOOL-011, TOOL-009): `uv run pumpgrok paper buy --help` lists `--ticket`, `--mint`, `--size-sol`, `--slippage-bps` and `--approval-id`, and `! grep -rnE "\b(post|put|patch|delete)\b|method=['\"](POST|PUT|PATCH|DELETE)" src/pumpgrok/tools/social/` prints nothing
- Proves: operator CLI exposes the paper trade flags; the social tool directory has no write verbs.
- Status today: the `--help` half PASSES (verified in Phase 2). The grep half is **vacuous** today (directory missing: exit 2, so `!` exits 0 and prints an error to stderr). Requires B14 and the non-vacuity test (section 5.3).

**SC5** (TOOL-008): `! grep -rnE "(lamports|units|sol)[A-Za-z_]*: *float" src/pumpgrok/` prints nothing and `uv run pytest -q` exits 0
- Proves: no float-typed money field in the package; full suite green.
- Status today: FAILS (9 matching lines; B1). `uv run pytest -q` is green today (512 tests, Phase 2 verification) and must stay green.

**Checkpoint** (all phases): `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` completes one cycle; canonical gates pass.
- Status today: PASSES (Phase 2 verification: `engine decision=skip reason=data_unavailable`, ledger_seq 1).

### 8.2 Proposed additional selectors for requirements the success criteria do not cover (files to create)

These are not ROADMAP criteria; the planner should add them to each plan's verification so TOOL-001..008 and SKILL coverage is exercised.

| Req | Command (after files exist) | Proves |
|---|---|---|
| TOOL-001 | `uv run pytest -q tests/tools/market` | typed market outputs with freshness/source; MockTransport fixtures; no network |
| TOOL-002 | `uv run pytest -q tests/tools/onchain/test_rpc.py` | retry only on timeout/5xx/429; ordered failover; key never in URL or log; malformed JSON typed |
| TOOL-003 | `uv run pytest -q tests/tools/safety` | scored report, per-check reasons, BLIND not exception |
| TOOL-004 | `uv run pytest -q tests/tools/exec` | g6 approval required; decision_id required; key derived from (ticket_id, side, decision_id) only; simulate writes nothing; NotYetImplementedAdapter raises |
| TOOL-005 | `uv run pytest -q tests/tools/portfolio tests/tools/risk tests/tools/journal` | catalog schemas; kill_switch set/flatten only; journal kinds for seats; ledger_write denied |
| TOOL-006 | `uv run pytest -q tests/tools/notify` | allowlist-only Telegram/webhook; stdout and file always; escalation kinds; idempotent send |
| TOOL-007 | `uv run pytest -q tests/tools/desk` | core eight resolvable by all ten seats; doctor check uses pumpgrok doctor code path |
| TOOL-008 | `uv run pytest -q tests/tools/test_money_types.py` | canonical_json rejects float; Decimal serialized as string; ToolInput/Output extra forbid; upstream extra ignore |
| TOOL-009 | `uv run pytest -q tests/test_registry_least_privilege.py tests/safety/test_cron_seats_cannot_write.py tests/safety/test_no_manipulation_tools.py` | interfaces 4 suite; R63 guard; social GET-only |
| TOOL-010 | `uv run pytest -q tests/test_gateway_projection.py` and `cd services/desk-gateway && uv run pytest -q` | projection equals roster+core; 401/403 behaviour; transport names injective |
| TOOL-011 | `uv run pumpgrok tools exec.quote --help` and `uv run pumpgrok killswitch clear --help` | hidden tools verb; killswitch clear takes --by and --reason |
| SKILL-004 | `bash scripts/assemble-prompts.sh --check` and `python3 scripts/generate-templates.py --check` | prompt <skills> and <tools contract=...> regenerated; agents match |

### 8.3 Gates and whole-suite commands (required at every checkpoint)

- `uv run pytest -q` (full suite; must include the Phase 2 characterization pins unchanged)
- `make lint typecheck test audit` (CI runs the same; note CI pins uv 0.13.4 while the local uv is 0.11.26)
- `./scripts/check.sh`
- `python3 ci/gates/check_desk_integrity.py --repo .` (G-7; roster sizes and names)
- `python3 ci/gates/check_ownership.py --validate-manifest` (G-1; every new path has exactly one owner; new `.py` files fall under `**/*.py` owner bot-02-risk)
- `python3 ci/gates/check_secrets.py --base origin/main` (G-3; fixture tokens per 4.5)
- `python3 ci/gates/check_contracts.py --base origin/main --change contracts/changes/<change-id>.yaml` (G-4; roster edits need one document listing every changed roster file and acks from every `contract_consumers` entry for `contracts/tool-rosters/**`, which is all ten seats)
- `python3 -m pytest ci/tests/ -q`
- `uv run python scripts/generate-event-schemas.py --check` (ledger events unchanged in Phase 3 unless a model changes)
- `bash scripts/assemble-prompts.sh --check` and `python3 scripts/generate-templates.py --check`
- `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke`

## 9. Current files affected (verified paths)

Modified:
- `src/pumpgrok/core/registry.py` (find() prefix semantics; `_wrap` retry and rate limit; build helper)
- `src/pumpgrok/core/tool.py` (`_retry_is_not_wired` at lines 88-90; `RetryPolicy` docstring; `ToolSpec.rate_limit_key` comment at line 69)
- `src/pumpgrok/core/bot.py` (no logic change expected; loader feeds it)
- `src/pumpgrok/core/idempotency.py` (add exec_place_key, exec_cancel_key; keep derive_idempotency_key)
- `src/pumpgrok/core/ratelimit.py` (wire usage; no change expected)
- `src/pumpgrok/core/__init__.py` (exports)
- `src/pumpgrok/tools/__init__.py` (currently a docstring only; becomes build_registry)
- `src/pumpgrok/tools/onchain/rpc.py` (retry predicate, policy values, JSON decode handling)
- `src/pumpgrok/tools/market/jupiter.py` (no change to ported function; typed wrapper added alongside)
- `src/pumpgrok/tools/onchain/holders.py`, `authorities.py`, `priority_fee.py` (unchanged; wrapped)
- `src/pumpgrok/cli.py` (size_sol type at line 120; killswitch args; tools verb; paper JSON output; registry calls for paper and state)
- `src/pumpgrok/config/settings.py` (new notify, safety sections; forbidden-key tests affected)
- `src/pumpgrok/config/overlays/{paper,dev,live}.toml` (new sections)
- `src/pumpgrok/engine/*` (NOT modified; B1)
- `src/pumpgrok/doctor.py` (structured rows for desk.doctor; same code path)
- `src/pumpgrok/ledger/store.py` (read-by-key method only if the planner adopts it; B7)
- `contracts/tool-rosters/*.yaml` (add manifest blocks; B6; G-4 change document)
- `contracts/tool-rosters/_core.yaml` (version bump if shape changes)
- `contracts/README.md` (write-tool gates statement; section 3.1 note)
- `prompts/bot-*.xml` (skills and tools contract; 10 files)
- `scripts/prompt_sources.py` (load attribute and tools element; `load_seat` at line ~111)
- `prompts-assembled/*.xml` and `agents/*.md` (generated)
- `skills/*/SKILL.md` (23 existing: frontmatter additions; B10 bots/gates)
- `skills/README.md` (23 to 35)
- `plugin.json`, `.claude-plugin/plugin.json`, `.grok-plugin/plugin.json`, `.grok-plugin/marketplace.json` (description count)
- `README.md` (lines 5 and 12: "23 skills")
- `tests/core/test_registry.py` (lines 96-110: retry test)
- `tests/test_forbidden_owners.py` (lines 88-94: absent-verb expectation changes)
- `ownership.yaml` (only if new owned path patterns are required; `services/desk-gateway/**`, `src/pumpgrok/tools/**`, `tests/tools/**`, skill paths already pre-declared)

Created:
- `src/pumpgrok/tools/{market,onchain,safety,exec,portfolio,risk,journal,notify,desk,social}/**` (per section 1.3)
- `src/pumpgrok/core/manifests.py` (loader)
- `src/pumpgrok/execution/not_yet_implemented.py` (or equivalent) - NotYetImplementedAdapter
- `services/desk-gateway/**` (section 4.1)
- `tests/test_skill_manifests.py`, `tests/test_bot_manifests.py`, `tests/test_registry_least_privilege.py`, `tests/test_gateway_projection.py`
- `tests/safety/test_cron_seats_cannot_write.py`, `tests/safety/test_no_manipulation_tools.py`
- `tests/tools/**` (market, onchain, safety, exec, portfolio, risk, journal, notify, desk, social, test_money_types.py)
- `tests/fixtures/http/<source>/**` (new fixtures; do NOT move existing flat `tests/fixtures/http/*.json`, which characterization tests load by flat path, e.g. `tests/characterization/test_holder_check.py:30`)
- `tests/fixtures/tools/exec/**`
- `contracts/changes/<id>.yaml` (G-4 document)
- `skills/{verification-receipts,paper-broker,replay-and-backtest,live-gate-procedure,kill-switch,rpc-hygiene,key-custody,safety-scoring,momentum-signals,portfolio-ledger,daily-report,desk-doctor}/SKILL.md`

Not modified in Phase 3: root `tools/` (oracle until Phase 5), `vendor/`, `src/pumpgrok/engine/*` (B1 aside), `src/pumpgrok/execution/live/*` (RISK-owned stub).

## 10. Risks and landmines (ordered by impact)

1. **SC5 cannot pass as written** (B1). Nine lines match; engine fields are characterization-pinned.
2. **R63 literal vs TOOL-009** (B2). Writing the guard as stated makes one of the two requirements false.
3. **Registry prefix resolution refuses early** (1.2 item 1). A seat with a PAPER_WRITE tool sorted before a READ tool cannot resolve the READ tool by namespace.
4. **Retry validator blocks TOOL-002/008** (1.2 item 2). Removing it requires updating `tests/core/test_registry.py::test_retry_is_refused_until_wired`.
5. **Idempotency derivation mismatch** (1.2 item 4). `derive_idempotency_key` mixes in tool and bot; using it for exec.place violates R23 and would make two seats' identical orders distinct.
6. **RPC retries 4xx and escapes JSON errors** (2.4). Violates "retry only on timeout, 5xx, 429" and TOOL-008 typed errors.
7. **Roster YAML lacks manifest fields** (B6). SKILL-003 cannot pass without a contract change touching all ten seats' acks.
8. **Prefix tool-name reversal is ambiguous** (4.2). `replace("_", ".")` on transport names corrupts `onchain.token_metadata`; use the roster map.
9. **Transport name collisions** are possible because TOOL_NAME_RE allows underscores inside segments. Add an injectivity test.
10. **Social grep vacuity** (5.3). SC4 passes without the directory and prints to stderr.
11. **`grep -w` style false positives in social** (5.2): prose "post-trade" fails SC4.
12. **Skill bots/required_tools contradiction** (B10): 8 skills cannot satisfy SKILL-002 under either design doc without a rule decision.
13. **Plugin "23 skills" in four files plus README** (SC2 and stale docs).
14. **Test fixture secret gate** (4.5): entropy rule can fail gateway test tokens.
15. **Signing AST guard applies to new code** (2.5): the names `sign`, `Keypair`, `send_transaction`, and string literals with those values, fail in any new src module.
16. **Characterization pins** (2.3, 1.1): float ratios in ported tools must stay float; typed wrappers convert. Do not "fix" them in place.
17. **Fixture layout drift**: CONTEXT says `tests/fixtures/http/<source>/`; existing characterization tests use flat paths. Creating subdirectories is safe; moving files is not.
18. **Test that breaks by design**: `tests/test_forbidden_owners.py:88-94` (paper buy exit 5 becomes rejection). List it in the plan.
19. **TOOL-011 "prints JSON by default"** conflicts with `doctor` and `run` text output (6.2). Needs an explicit exemption list.
20. **Killswitch CLI gaps** (6.2): `set --reason`, `flatten --reason`, `clear --by --reason` missing; TOOL-011 and R22 require them.
21. **Catalog market.price fallback to lite-api** (`docs/TOOL_CATALOG.md:54`). R44 forbids lite-api; implement without it.
22. **Unregistered `DataSource` names**: `required_data` must use `jupiter` (R44), not `jupiter_lite` (interfaces 3.2 example).
23. **Stale contracts/README.md claim** that every write tool needs g6 vs G-7 accepting `gates: []` on risk.kill_switch and desk.* writes (`ci/gates/check_desk_integrity.py:59-66`).
24. **Local uv version** 0.11.26 vs CI-pinned 0.13.4 and `uv_build>=0.13.4,<0.14.0` (`pyproject.toml` build-system). Use the CI version for gate evidence.
25. **Settings env-name forbidding**: `refuse_forbidden_env` runs over the whole process environment on settings load (`settings.py:393`); the gateway process must not load Settings for its token names, or the env var names must avoid forbidden fragments (they do).
26. **Ownership G-1**: every new file must resolve to exactly one owner; check the `ownership.yaml` last-match order before adding patterns.
27. **R23 same-transaction and duplicate-returns-first-Fill** (B7) need a ledger read-by-key that does not exist.
28. **ROADMAP SC4 `--help` already passes**; do not let plan tasks regress it.
29. **`check_contracts.py` error text references `skills/contract-first-changes/SKILL.md`** (`ci/gates/check_contracts.py:346`), a skill that does not exist. Harmless message, but any test that follows the link will fail; not in Phase 3 scope.
30. **Phase 2 test count 512** is the baseline; adding tests must not reduce it or change characterization counts (SC of Phase 4 requires >=164 characterization tests collected).

## Assumptions Log

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | pump.fun bonding-curve account layout (8-byte discriminator, five u64 reserves, bool complete) | B9, 1.1 | market.price and onchain.lp_status decode wrong; fixture-only tests would still pass; live wrong |
| A2 | `respx` not required if httpx.MockTransport is used | B13 | none if MockTransport chosen |
| A3 | MCP JSON-RPC over POST with application/json responses is acceptable for the gateway | 4.3 | a client expecting SSE would need more work; documented as recommendation |
| A4 | `derive_idempotency_key` behavior must stay unchanged for skip-cycle replay | 1.2 item 4 | changing it alters the Phase 1 checkpoint ledger hash |
| A5 | Phase 3 `exec.quote` delegates to ExecutionAdapter (raises until Phase 4) | 1.4 | if the user wants a working Jupiter quote in Phase 3, the design changes |
| A6 | The 3.1 roster counts (chief 15 ... journal 15) are the R35 target | 3.1 | counted from YAML, verified |

## Sources

Primary (repository, read in this session): `.planning/phases/03-tools-and-skills/03-CONTEXT.md`; `.planning/REQUIREMENTS.md` (TOOL-001..011, SKILL-001..004 at lines 39-56); `.planning/ROADMAP.md` (Phase 3 at lines 78-99); `.planning/STATE.md`; `.planning/phases/02-restructure/02-VERIFICATION.md`, `02-REVIEW.md`, `02-REVIEW-FIX.md`, `02-05-SUMMARY.md`; `src/pumpgrok/core/*.py`; `src/pumpgrok/tools/**`; `src/pumpgrok/cli.py`; `src/pumpgrok/config/settings.py`; `contracts/tool-rosters/*.yaml`; `contracts/README.md`; `contracts/changes/README.md`; `ci/gates/check_desk_integrity.py`, `check_contracts.py`, `check_secrets.py`; `scripts/check.sh`; `scripts/prompt_sources.py`; `tests/**` (named above); `ownership.yaml`; `docs/design/interfaces.md` (sections 2.10, 3, 3.1, 3.2, 4); `docs/TOOL_CATALOG.md` (sections 0, 1, 2, 4, 7, 9, 12); `docs/ROSTER.md` (sections 5, 6); `docs/MIGRATION_MAP.md` (4.2); `docs/upgrade-plan-desk-v2.md` (R19-R46, 6.3, 9); `docs/DISCOVERY.md` (gateway references); `AGENTS.md`; `hermes/profiles.yaml`, `hermes/cron/jobs.yaml`.

Registry check (not a legitimacy check): `pip index versions respx` -> 0.23.1; `pip index versions mcp` -> 2.3.0. Neither is adopted.

Provenance tags used above: facts about repository files are [VERIFIED: path:line] (read this session); design statements are [CITED: docs/... section]; upstream Solana/pump.fun layouts and any unverified behaviour are [ASSUMED].

## Metadata

**Confidence breakdown:**
- Repository state and roster facts: HIGH (read this session)
- Registry defects and fixes: HIGH (code read; behaviour inferred from code, not executed)
- Upstream data layouts (B9): LOW ([ASSUMED])
- Gateway design (section 4): MEDIUM (no existing precedent in this repo)
- Blocker resolutions: require user or orchestrator decision

**Research date:** 2026-10-21
**Valid until:** until the next commit touching `src/pumpgrok/core`, `contracts/tool-rosters`, `skills/`, or `tests/test_forbidden_owners.py`
