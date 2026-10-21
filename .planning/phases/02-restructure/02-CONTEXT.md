# Phase 2: Restructure - Context
**Gathered:** 2026-10-21
**Status:** Ready for planning
**Mode:** Seeded from design docs (discuss replaced; decisions locked by R16-R49)

<domain>
## Phase Boundary
Port root tools and the vendor engine into src/pumpgrok under characterization tests; regenerate the seat instruction pack; expose CLI verbs; add the signing AST guard. Vendor tree and root tools/*.py stay as oracles.
Requirements (5, all owned here): STRUCT-002, STRUCT-003, STRUCT-005, STRUCT-007, SEC-003.
TOOL owned: none (Phase 3 owns TOOL-001..011). Backing modules only for onchain.authorities, onchain.top_holders, onchain.priority_fee, exec.quote (informational), GET-only tools/social.
</domain>

<decisions>
## Implementation Decisions

### Locked
Tools (STRUCT-002; MIGRATION_MAP rows 71, 73, 74, 77):
- `tools/onchain/rpc.py`: one httpx client, tenacity `sleep=clock.sleep`, ordered failover over `rpc.endpoints[]`, key never in URL or log (D8, R27). Replaces the three `rpc_call` copies (`tools/*.py:25,26,27`).
- `onchain/authorities.py`, `onchain/holders.py` (`onchain.top_holders`, RUG per R35), `onchain/priority_fee.py`: on rpc.py; holders via `getTokenLargestAccounts` (R47).
- `market/jupiter.py`: `GET https://api.jup.ag/swap/v2/order`, no `taker`, never /execute, /build, /submit (R44). Key from env `JUPITER_API_KEY` (SecretStr, `x-api-key`). Rate key `jupiter`: concurrency 1, quote TTL cache. Quote is informational, never the fill (R38). Replaces lite-api at `tools/jupiter_quote.py:22`.
- `notify/base.py` (abstract Notifier), `notify/stdout.py`, `notify/file.py`: always-on (D6). `social/__init__.py`: read-only (R31).
- `core/ratelimit.py` (`ops.py:90`), `core/budget.py` (`ops.py:187`), `core/llm.py` (GrokOps precheck `ops.py:235,248`; x.ai client; R27 recorder hook) (R43).

Engine (STRUCT-003; rows 97-104, 106, 110, 113-115; R31):
- `engine/`: `pipeline.py` (`pipeline.py:65`), `models.py` (domain half `models.py:26-270`), `monitor.py` (`:114`), `analyzer.py` (`:38`), `scoring.py` (`:35,58`), `reputation.py` (`:48`), `tune.py`, `exits.py` (bot-06-exit; `risk.py:219,238`), `watcher.py` (bot-05-rug; `risk.py:283`), `agents/*` (`agents/base.py:35`).
- Reason codes unchanged; tests assert ASCII codes only (MIGRATION_MAP sec 3.3). `! grep -rlP '\p{Cyrillic}' src/pumpgrok/engine/` (ROADMAP SC2) must be empty.
- Exit priority stop_loss > take_profit > trailing_stop > max_hold (`risk.py:238`). Day-rollover auto-clear (`risk.py:106-117`) NOT ported (R5). Live-flag code (`pipeline.py:18,490-540`) NOT ported; refusal is Phase 4 `LiveGateError`.
- No trade subscription (R45, R46): monitor sends `subscribeNewToken` only (`monitor.py:219`); delete `_subscribe_trades` (`:236,241,255-257`) and `_buyers` (`:126-153`). `passes_filter` (`monitor.py:95`) returns new ASCII code `data_unavailable` where `few_buyers` (`:110`) fires on missing trade evidence (fail closed). No logsSubscribe, no subscribeMigration.
- Websockets (R49 V-7; STACK.md:31): `from websockets.asyncio.client import connect`; every call `connect(url, proxy=None, max_queue=<data.ws_max_queue>)` (vendor `monitor.py:218`).
- pump.fun REST (R47): analyzer keeps `_get` (`analyzer.py:72-79`, None on failure) plus a per-source health flag. No entry decision rests solely on it.
- x.ai (R48): `grok.base_url=https://api.x.ai/v1` (vendor full path `models.py:279`). Strong `grok-4.3`, effort low, replaces `checker_model` (`models.py:281`; checker). Fast `grok-4.20-0309-non-reasoning` replaces `grok-4-fast` (`models.py:280`; narrative, timing). Auditor keeps fast (`agents/base.py:59`). Scoring makes no LLM call (`scoring.py:6`).
- Clock (R27): ported `time.time`, `asyncio.sleep`, `asyncio.wait_for` (`monitor.py:74-251`, `agents/base.py:149`, `agents/timing.py:65-93`, `risk.py:273,371`, `ops.py:44-193`) use `clock.*`.
- Pipeline: `run --mode paper --once --replay` prints the engine decision (`skip` or `buy`), appends one JournalNote. No fills.
- Characterization (`tests/characterization/`): `test_{authority_check,holder_check,jupiter_quote,priority_fee}.py`; `test_{agents,analyzer,monitor,reputation,scoring,tune,pipeline,exits,watcher}.py`. Vendor counts 21/16/21/18/13/15/37; exit/watcher subset of test_risk.py (of 36). Vendor suite stays green: 264 tests.
- Root oracle: `tests/test_tools_cli.py` has 11 unittest cases; six belong to the STRUCT-002 modules (`:33-71`, `:109`, `:119`, `:129`).
- Instruction pack (D2, R16-R18, R36, R40, R42): `prompts/_shared/core-directives.xml`, `prompts/bot-00..09-*.xml` (10 seats); `scripts/assemble-prompts.sh` -> `prompts-assembled/`; `scripts/generate-templates.py` -> `agents/<seat>.md` (bot-00-chief). 23 skills gain `bots:`, `gates:` (MIGRATION_MAP sec 4.2) and L1/L2 bodies. `jupiter-routing` drops `--max-micro` (`skills/jupiter-routing/SKILL.md:18`). Remove micro-live everywhere, incl. `rules/pumpgrok-team.mdc:46` (R42). Manifests: AGPL-3.0. Cron prompts wrap `pumpgrok` only (rows 24-29); `hermes/cron/jobs.yaml:79` kept.
- CLI (STRUCT-005; `docs/DISCOVERY.md:8-18`, R12, R40): absent subsystems return not-yet-implemented; `paper buy|sell --ticket --mint --size-sol --slippage-bps --approval-id` in help; forbidden_owners (sniper, exit) enforced.
- SEC-003: `tests/safety/test_no_signing_outside_live_stub.py` walks the AST of `src/pumpgrok/**`, flags exact `sign`, `send_transaction`, `sendTransaction`, `Keypair` (names, attributes, string constants) outside `src/pumpgrok/execution/live/`. `signature` (`analyzer.py:136`) does not match.

### Claude's Discretion
- Keys: `data.ws_max_queue` (default 16), `rpc.endpoints[]`, `grok.*`, `JUPITER_API_KEY` via Phase 1 settings.
- Absent verb: `{"ok": false, "status": "not-yet-implemented"}`, exit 2.
- Startup `GET /v1/models` result and smoke `engine_decision`/`disposition` recorded in JournalNote.
- Translate prompt text only where vendor text is Russian. Prompt edits change canonical_request_hash; author smoke LLM records last.
- Analyzer keeps pump.fun holders GET 1:1 (RPC holders in Phase 3). holders.py follows R35 (RUG), not sec 3.2 (WHALE); settle in ownership.yaml.
</decisions>

<code_context>
## Existing Code Insights
### Reusable Assets
- Vendor `vendor/grokbot-pumpfun/src/*` and `scripts/tune.py`; tests in `vendor/grokbot-pumpfun/tests/` (FakeWebSocket `test_filter.py:245`; httpx.MockTransport `test_analyzer.py:43`).
### Established Patterns
- Pydantic v2 models (`models.py:26`); analyzer injects httpx client (`analyzer.py:41`).
### Integration Points
- Phase 1 supplies core interfaces, replay/clock, settings, JournalNote ledger, cli doctor, contracts/tool-rosters, ownership.yaml (FOUND-004..013).
</code_context>

<specifics>
## Specific Ideas
- (a) Verification is automated: every success criterion is a command; no live network in tests; fixtures are recorded or hand-authored.
- (b) Checkpoint: `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` exits 0 printing one engine skip or buy; `uv run pumpgrok doctor` lists execution, risk, supervisor, reporting as not-yet-implemented.
- (c) Fixtures: `tests/fixtures/replay/smoke` (checkpoint) and `tests/fixtures/http/` (STRUCT-002).
</specifics>

<deferred>
## Deferred Ideas
- Phase 3: TOOL-001..011, SKILL-001..004; `tools/market/{pumpfun,pumpportal}.py`; `tools/notify/webhook.py`; WHALE transfers; RPC holders; logsSubscribe probe (R46).
- Phase 4: `risk/breakers.py`, `supervisor/lifecycle.py`, test_ops (STRUCT-004); `replay/{recorder,sources}.py` (PAPER-004); execution, LiveGate; subscribeMigration; vendor deletion (STRUCT-006).
- Phase 5: supervisor metrics and health; root `tools/` deletion (sec 7 batch 5).
- Conflicts: (1) sec 7 batch 2 lists pumpfun, pumpportal, webhook, breakers, recorder; ROADMAP puts them in Phases 3-4. (2) Plan 6.2 deletes `tools/` in Phase 2; sec 7 and STRUCT-007 keep it. (3) Plan 5.2 says lite-api; R44 and REQUIREMENTS say api.jup.ag/swap/v2/order (R44 applied). (4) ROADMAP SC1 names 11 cases for four files; they cover 6.
</deferred>

## Orchestrator resolutions (binding)
- R52 (placements): where docs/MIGRATION_MAP.md section 7 batch 2 conflicts with the ROADMAP, the ROADMAP wins. The pumpfun and pumpportal sources, the webhook notifier, breakers and the recorder are built in Phases 3-4 as the ROADMAP lists them.
- R53 (tools/ tree): tools/ is kept until Phase 5 (ROADMAP Phase 5 deletion). tests/test_tools_cli.py and the CLI contracts depend on it during Phases 2-4.
- R54 (Jupiter): R44 applies. The quote adapter targets api.jup.ag/swap/v2/order, quote-only. The lite-api path in plan section 5.2 is not built.
- R55 (criterion 1): the characterization set is the 6 root unittest cases for the four ported tools (Jupiter 3, authority 1, holder 1, priority 1), as corrected in ROADMAP Phase 2 criterion 1.
