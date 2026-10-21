# Phase 3: Tools and Skills - Context
**Gathered:** 2026-10-21
**Status:** Ready for planning
**Mode:** Seeded from design docs (discuss replaced; decisions locked by R16-R49)

<domain>
## Phase Boundary
Typed dotted tools, least-privilege rosters, desk gateway, CLI wrappers, 35-skill set. Covers TOOL-001..011, SKILL-001..004 (15 ids).

Tools (37): market.{price,ohlcv,liquidity,trades,holders_snapshot}; onchain.{token_metadata,authorities,lp_status,top_holders,deployer_history,large_transfers,priority_fee}; safety.score_report; exec.{quote,simulate,place,cancel,positions}; portfolio.{ledger_read,ledger_write,exposure,pnl}; risk.{check_limits,drawdown,kill_switch,halt_status}; notify.alert; journal.{append,render_report}; desk.{brief,docs_search,memory_retain,memory_recall,ownership_resolve,receipt_check,event_emit,doctor}.

Skills (35): browser-ops, desk-execution-protocol, desk-folders-and-journal, desk-incident-response, desk-monitoring, desk-operating-model, desk-post-trade-review, desk-risk-limits, desk-strategy-lab, desk-trade-lifecycle, discovery-tools, grokbot-pipeline, hermes-cron-desk, holder-and-flow-analysis, jupiter-routing, position-monitoring, pumpgrok-setup, risk-audit, social-sentiment, solana-api-reference, solana-market-data, solana-rpc-and-wallet, tool-connections; new: verification-receipts, paper-broker, replay-and-backtest, live-gate-procedure, kill-switch, rpc-hygiene, key-custody, safety-scoring, momentum-signals, portfolio-ledger, daily-report, desk-doctor.
</domain>

<decisions>
## Implementation Decisions

### Locked
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
```
market.price R 10 j4 solana_rpc -
market.ohlcv R 10 j4 solana_rpc -
market.liquidity R 10 j4 solana_rpc -
market.trades R 10 j4 solana_rpc -
market.holders_snapshot R 10 j4 solana_rpc -
onchain.token_metadata R 15 j5 solana_rpc -
onchain.authorities R 15 j5 solana_rpc -
onchain.lp_status R 20 j5 solana_rpc -
onchain.top_holders R 15 j5 solana_rpc -
onchain.deployer_history R 20 j5 solana_rpc -
onchain.large_transfers R 20 j5 solana_rpc -
onchain.priority_fee R 15 j5 solana_rpc -
safety.score_report R 45 - solana_rpc -
exec.quote R 12 j4 jupiter -
exec.simulate R 10 - solana_rpc -
exec.place P 20 - exec d(ticket_id,side,decision_id)
exec.cancel P 10 - exec d(order_id,cancel)
exec.positions R 10 - ledger -
portfolio.ledger_read R 5 - ledger -
portfolio.ledger_write P 5 - ledger required key, unique index
portfolio.exposure R 5 - ledger -
portfolio.pnl R 5 - ledger -
risk.check_limits R 5 - ledger -
risk.drawdown R 5 - ledger -
risk.kill_switch P 5 - killswitch d(tool,action,reason,minute)
risk.halt_status R 5 - ledger -
notify.alert P 10 j8 notify d(kind,ticket,severity,minute)
journal.append P 5 - ledger d(kind,ticket,sha(body))
journal.render_report P 30 - ledger d(period,as_of day)
desk.brief R 10 - desk -
desk.docs_search R 10 - desk -
desk.memory_retain P 5 - desk d(tool,bot,sha(input))
desk.memory_recall R 5 - desk -
desk.ownership_resolve R 5 - desk -
desk.receipt_check R 60 - desk -
desk.event_emit P 5 - desk d(tool,bot,sha(input))
desk.doctor P 60 - desk d(tool,bot,sha(input))
```

### Claude's Discretion
- exec.cancel input (order_id, ticket_id, approval_id); adapter reads decision_id from the order.
- Modules by catalog suffix (onchain/lp_status.py); ownership.yaml reconciles ROSTER section 7 names.
- NotYetImplementedAdapter raises PumpgrokError until Phase 4; TOOL-004 transaction proof moves to Phase 4.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- tools/jupiter_quote.py:22,33 -> market/jupiter.py; tools/authority_check.py:25, holder_check.py:26, priority_fee.py:27 duplicate rpc_call -> onchain/rpc.py.
- vendor/grokbot-pumpfun/src/executor.py:85 price_from_reserves; src/analyzer.py:85-86; src/alerts.py:40 Notifier.

### Established Patterns
- scripts/check.sh:45-46 name equals dirname; :51-52 description max 1024; :54-55 body max 350.

### Integration Points
- Phases 1-2 deliver the registry, rosters, RPC client, notify sinks and fixtures.
</code_context>

<specifics>
## Specific Ideas
(a) Verification is automated: every success criterion is a command; no human_verification items; no live network in tests; recorded or hand-authored fixtures only (respx for httpx; in-process fake for websockets).
(b) Checkpoint: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke`; ROADMAP criteria as commands.
(c) Fixtures: tests/fixtures/replay/smoke; tests/fixtures/http/<source>/; tests/fixtures/tools/exec/.
</specifics>

<deferred>
## Deferred Ideas
- Phase 4 (PaperAdapter, RiskEngine, ledger, breakers, live gate); Phase 5 (RISK-007, fault injection).
</deferred>
