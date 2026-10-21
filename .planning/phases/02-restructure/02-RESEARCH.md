# Phase 2: Restructure - Research

**Researched:** 2026-10-21
**Domain:** Python port of the vendor screening engine and four read-only root tools into `src/pumpgrok`, CLI verb surface, skill frontmatter, AST signing guard
**Confidence:** HIGH for repo facts (read this session, file:line cited); MEDIUM for external API shapes (tagged `[CITED]` to repo research docs or `[ASSUMED]`)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
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

### Deferred Ideas (OUT OF SCOPE)
- Phase 3: TOOL-001..011, SKILL-001..004; `tools/market/{pumpfun,pumpportal}.py`; `tools/notify/webhook.py`; WHALE transfers; RPC holders; logsSubscribe probe (R46).
- Phase 4: `risk/breakers.py`, `supervisor/lifecycle.py`, test_ops (STRUCT-004); `replay/{recorder,sources}.py` (PAPER-004); execution, LiveGate; subscribeMigration; vendor deletion (STRUCT-006).
- Phase 5: supervisor metrics and health; root `tools/` deletion (sec 7 batch 5).
- Conflicts: (1) sec 7 batch 2 lists pumpfun, pumpportal, webhook, breakers, recorder; ROADMAP puts them in Phases 3-4. (2) Plan 6.2 deletes `tools/` in Phase 2; sec 7 and STRUCT-007 keep it. (3) Plan 5.2 says lite-api; R44 and REQUIREMENTS say api.jup.ag/swap/v2/order (R44 applied). (4) ROADMAP SC1 names 11 cases for four files; they cover 6.

### Orchestrator resolutions (binding)
- R52 (placements): where docs/MIGRATION_MAP.md section 7 batch 2 conflicts with the ROADMAP, the ROADMAP wins. The pumpfun and pumpportal sources, the webhook notifier, breakers and the recorder are built in Phases 3-4 as the ROADMAP lists them.
- R53 (tools/ tree): tools/ is kept until Phase 5 (ROADMAP Phase 5 deletion). tests/test_tools_cli.py and the CLI contracts depend on it during Phases 2-4.
- R54 (Jupiter): R44 applies. The quote adapter targets api.jup.ag/swap/v2/order, quote-only. The lite-api path in plan section 5.2 is not built.
- R55 (criterion 1): the characterization set is the 6 root unittest cases for the four ported tools (Jupiter 3, authority 1, holder 1, priority 1), as corrected in ROADMAP Phase 2 criterion 1.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description (REQUIREMENTS.md) | Research Support |
|----|-------------------------------|------------------|
| STRUCT-002 | `tools/{jupiter_quote,authority_check,holder_check,priority_fee}.py` re-implemented as `src/pumpgrok/tools/{market/jupiter.py,onchain/authorities.py,onchain/holders.py,onchain/priority_fee.py}` over `src/pumpgrok/tools/onchain/rpc.py` (httpx + tenacity `sleep=clock.sleep` + failover); characterization tests reproduce the root unittest cases. | Root cases: `tests/test_tools_cli.py:33,41,73` (Jupiter), `:107` (authority), `:119` (holder), `:131` (priority). Section "Port Map: root tools". Pitfalls 1-6. |
| STRUCT-003 | Vendor `monitor, analyzer, scoring, reputation, agents/*, tune` ported to `src/pumpgrok/engine/`; vendor `risk.py` exit rules and `PositionWatcher` to `engine/{exits,watcher}.py`; translated strings, unchanged reason codes; 1:1 characterization tests green; vendor pytest still green; `run --replay` prints one engine decision. | Section "Port Map: vendor engine"; Pitfalls 7-16. |
| STRUCT-005 | `cli.py` exposes every verb of `docs/DISCOVERY.md:11-16` plus R12 and R40; absent subsystems return `not-yet-implemented`; six Hermes cron prompts wrap `pumpgrok` only; `hermes-*.sh` rewritten for `PUMPGROK_*` env; `forbidden_owners` enforced by CLI. | Section "CLI verb surface"; Pitfalls 17-21. |
| STRUCT-007 | 23 skills gain `bots` and `gates` frontmatter and L1/L2 bodies; `jupiter-routing` quote/route preparation; quote-only Jupiter path; `--max-micro` removed; `tools/README.md` lists `desk_state.py`; four plugin manifests AGPL-3.0, no `your-org`; README/ARCHITECTURE/setup runbook describe `src/pumpgrok/`. | Section "Skill frontmatter"; Pitfalls 22-26. |
| SEC-003 | `tests/safety/test_no_signing_outside_live_stub.py` walks the AST and fails on any `sign`, `send_transaction`, `sendTransaction` or `Keypair` symbol outside `src/pumpgrok/execution/live/`; the live stub builds no transaction. | Section "Signing guard design"; Pitfall 27. |
</phase_requirements>

## Summary

Phase 2 is a port, not a rewrite. Four root tools (`tools/{jupiter_quote,authority_check,holder_check,priority_fee}.py`, 6 unittest cases in `tests/test_tools_cli.py`) and the vendor screening engine (`vendor/grokbot-pumpfun/src/{monitor,analyzer,scoring,reputation,agents/*,pipeline,models(domain),risk(exits/watcher)}.py`, 264 vendor tests) move into `src/pumpgrok` behind characterization tests. Vendor and root `tools/` stay as oracles (R53).

The Phase 1 foundation constrains almost every port. The static guard (`tests/safety/test_static_guards.py`) bans `import time`, `asyncio.sleep`, `asyncio.wait_for`, `time.time`, `uuid`, `secrets`, and ambient `random` in `src/pumpgrok`. The vendor uses all of them, so each port must route through the injected `Clock` (`replay/clock.py`) and a seeded RNG. The network-blocking conftest (`tests/conftest.py:30-35`) and the `websockets.connect` ban (`tests/test_network_block.py:50-70`) force httpx `MockTransport` fixtures and the `websockets.asyncio.client` import. The settings loader (`config/settings.py`) has no `data`, `rpc`, `grok`, `jupiter`, `filter`, `scoring` or exit sections yet and refuses unknown `PUMPGROK_*` env names, which affects both the engine config and the Hermes scripts.

Several CONTEXT.md decisions conflict with the code as it exists. The most consequential are: the absent-verb exit code (CONTEXT says 2; the CLI reserves 2 for ledger inconsistency and the existing test expects 5), the Hermes scripts exporting `PUMPGROK_ROOT`/`PUMPGROK_DESK` (which makes `pumpgrok` exit 1), the 1:1 monitor characterization claim versus R45/R46 (about 7 of 21 `test_filter.py` cases depend on trade events that Phase 2 no longer subscribes to), and the root skill-text oracle test that pins `ticket_helper.py next` in a skill that the design wants rewritten. Each is listed under Open Questions with a recommendation.

**Primary recommendation:** Build in this order: (1) add `tenacity` and the Settings sections, (2) port the four root tools with fixtures under `tests/fixtures/http/` and their characterization tests, (3) port the engine with injected clock and RNG, (4) expand the CLI verb tree, (5) rewrite the 23 skills and cron prompts, (6) add the signing AST guard last so it runs against the finished tree.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Solana JSON-RPC calls (authority, holders, priority fee) | API / Backend (`src/pumpgrok/tools/onchain/rpc.py`) | — | Single httpx client with failover; no browser role |
| Jupiter quote (informational) | API / Backend (`tools/market/jupiter.py`) | — | Quote-only HTTP GET; never the fill price (R38) |
| pump.fun / PumpPortal ingestion, filter, buffer | API / Backend (`engine/monitor.py`) | — | Websocket consumer; no entry/exit decision here beyond filter |
| Analyzer metrics and veto | API / Backend (`engine/analyzer.py`, `engine/scoring.py`) | — | Pure computation over httpx GETs (injected client) |
| Grok agents (checker, narrative, timing, auditor) | API / Backend (`engine/agents/*`) | — | Outbound x.ai POST; prompts are server-side constants |
| Exit rules and position watch | API / Backend (`engine/exits.py`, `engine/watcher.py`) | — | Pure function plus poll loop; sells via injected callback |
| Config, mode gate, overlays | API / Backend (`config/settings.py`, `execution/live/live_gate.py`) | — | Phase 1 owns startup refusal; live stays disabled |
| CLI verbs and exit codes | API / Backend (`cli.py`) | Hermes cron prompts (wrap `pumpgrok` only) | Single entrypoint; prompts are thin wrappers |
| Skill documentation (`skills/*/SKILL.md`) | Static docs | Instruction pack (`prompts/`, `agents/`) | Frontmatter is the manifest parsed by SkillManifest |
| Signing guard | Test (`tests/safety/`) | CI gate | Static AST proof over `src/pumpgrok` |

Browser / CDN / database tiers have no Phase 2 responsibilities. The ledger (`ledger/`) is only touched by the existing replay JournalNote path.

## Standard Stack

### Core

| Library | Version (verified) | Purpose | Why Standard |
|---------|--------------------|---------|--------------|
| httpx | 0.28.1 installed in `.venv` (`pyproject.toml` pin `>=0.28.1,<0.29`) | Async HTTP for RPC, Jupiter, pump.fun REST, x.ai | Injectable client (`analyzer.py:41`); `httpx.MockTransport` is what conftest expects |
| websockets | 17.3 installed in `.venv` (pin `>=17.3,<18`) | PumpPortal feed | `websockets.asyncio.client.connect` is the only allowed path (`test_network_block.py:50-70`); legacy path deprecated [CITED: .planning/research/STACK.md:50,124] |
| tenacity | **9.2.1 — NOT in `pyproject.toml` or `uv.lock`; must be added** | Retry with `sleep=clock.sleep` on RPC | Locked by STRUCT-002 and STACK.md:52 (`AsyncRetrying`) |
| pydantic | 2.14.1 in `.venv` (pin `>=2.14.1,<3`) | Engine domain models, SkillManifest | Existing pattern `models.py:26` |
| pydantic-settings | 2.16.1 in `.venv` | Layered settings | Phase 1 loader `config/settings.py:112` |
| pytest | 9.1.1 in `.venv` | Test runner (`addopts=-q --strict-markers`) | `pyproject.toml` `[tool.pytest.ini_options]` |
| pytest-asyncio | 1.4.0 in `.venv` | Async tests, `asyncio_mode = "auto"` | Already configured; `asyncio_default_fixture_loop_scope = "function"` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| requests | 2.34.2 in `.venv` (dev group) | Only used by root `tools/*.py` (oracle) | Keep until Phase 5 (R53). Its `pyproject.toml` comment "removed with tools/ in Phase 2" is wrong and should be corrected |
| pyyaml | 6.0.3 | Hermes/ownership YAML only | Not needed by `src/pumpgrok/engine` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tenacity | hand-rolled loop (vendor `agents/base.py` `_backoff`) | Locked to tenacity for RPC (STRUCT-002). Agents may keep their own loop only if jitter is seeded (Pitfall 9) |
| tenacity `wait_random_exponential` | custom `wait` callable using injected rng | `wait_random_exponential` draws from the global `random` module, which breaks replay determinism (R27) [ASSUMED: source behaviour; STACK.md:52 names the class] |
| respx (MIGRATION_MAP sec 6) | `httpx.MockTransport` | conftest comment and `tests/test_network_block.py:33` already use `MockTransport`; respx adds a dev dep for no gain. Do not add respx |
| `requests` in `src/` | httpx | Synchronous, no injectable clock/transport. Not used in `src/pumpgrok` |

**Installation (lockfile change required):**
```bash
# edit pyproject.toml: add "tenacity>=9.2.1,<10" to [project] dependencies (FOUNDATION_STACK.md:125 already names it)
uv lock            # regenerates uv.lock; network required
uv sync --frozen   # the lockfile must be committed with the change
```

### Version verification

- `.venv` site-packages dist-info (read this session): httpx-0.28.1, pydantic-2.14.1, pydantic_settings-2.16.1, websockets-17.3, pytest-9.1.1, pytest_asyncio-1.4.0, requests-2.34.2, pyyaml-6.0.3. tenacity absent.
- `python3 -m pip index versions tenacity` (this session): latest `9.2.1`.
- `uv` on PATH is `0.11.26`; `pyproject.toml` and STACK.md V-2 require uv `0.13.4` with `uv_build>=0.13.4,<0.14.0`. Not blocking, but record the version used for `uv lock`.

## Package Legitimacy Audit

Only one new external package is introduced in Phase 2 (tenacity). The `gsd_run query package-legitimacy` seam was not executed in this session; the verdict below rests on the registry query plus repo documentation.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| tenacity | PyPI | Long-running project; 9.2.1 is the current major (FOUNDATION_STACK.md:83) | not measured in this session | https://github.com/jd/tenacity (cited in STACK.md:290) | OK (registry existence `pip index versions tenacity` -> 9.2.1; repo cited by STACK.md) | Approved; add with `>=9.2.1,<10` |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.
Dropped from consideration: respx (not needed), solders/solana (vendor lists them but never imports them; grep of `vendor/grokbot-pumpfun/{src,tests,scripts}` finds only a comment at `src/executor.py:150`). Do not add them.

## Architecture Patterns

### System Architecture Diagram

```
                    ┌──────────────────────── composition root (cli.py) ─────────────────────────┐
  settings (env/TOML) ─► Settings ─► Clock (FixtureClock | WallClock) ─┬─► rng (make_rng)          │
                                                                      │                           │
  CLI verb ──► run --mode paper --once --replay DIR                    │                           │
                 │  load_dataset (digest check) ─► ticks               │                           │
                 ▼                                                     ▼                           │
           engine.pipeline.decide(tick, evidence) ──► scoring ──► JournalNote (1 row, ledger)       │
                 ▲                                                                                 │
     engine.monitor.passes_filter / analyzer.fetch (httpx, injected) ◄── tools/onchain/rpc.py ◄─────┘
     engine.agents.* (httpx POST x.ai, injected ops budget, rng for jitter)
     engine.exits.exit_signal(position, price, cfg, now) ─► engine.watcher.PositionWatcher(book, price_fn, sell_fn)
  Absent verbs (paper buy, state, ticket, …) ─► not-yet-implemented (exit 5, JSON on stdout)
```

The replay path is a single synchronous-looking pass over fixture events driven by `FixtureClock.advance_to`. It must not start the monitor `stream()` loop (it would block on `FixtureClock.sleep`, see `replay/clock.py:121-130`).

### Recommended Project Structure (end of Phase 2)

```
src/pumpgrok/
├── cli.py                      # full verb tree; absent verbs -> not-yet-implemented
├── doctor.py                   # SUBSYSTEMS: engine and tools flip to ok
├── config/settings.py          # + data, rpc, grok, jupiter, filter, scoring, exits, ops sections
├── core/ratelimit.py           # ops.py:90 RateLimiter (clock.sleep)
├── core/budget.py              # ops.py:187 CallBudget (clock.now)
├── core/llm.py                 # ops.py:235,248 GrokOps precheck + x.ai client hook
├── engine/
│   ├── __init__.py             # docstring only (translated)
│   ├── models.py               # vendor models.py:26-270 (domain half), clock injected
│   ├── monitor.py              # ops ported; trade subscription removed
│   ├── analyzer.py
│   ├── scoring.py
│   ├── reputation.py
│   ├── pipeline.py             # engine decision only; no live flags
│   ├── tune.py                 # from scripts/tune.py; no print() (ruff T20)
│   ├── exits.py                # ExitSignal, pnl_pct, stop_loss_triggered, exit_signal
│   ├── watcher.py              # PositionWatcher over a PositionBook Protocol
│   └── agents/{__init__,base,auditor,checker,narrative,timing}.py
├── tools/
│   ├── __init__.py             # must exist: doctor's find_spec("pumpgrok.tools") flips to ok
│   ├── onchain/{__init__,rpc,authorities,holders,priority_fee}.py
│   ├── market/{__init__,jupiter}.py
│   ├── notify/{__init__,base,stdout,file}.py     # CONTEXT-locked; path per ownership.yaml:306
│   └── social/__init__.py                        # read-only, GET-only (R31)
└── execution/live/live_adapter.py   # unchanged; SEC-003 exempt path
tests/
├── characterization/           # FLAT names required by ROADMAP SC1-2
│   ├── test_authority_check.py test_holder_check.py test_jupiter_quote.py test_priority_fee.py
│   └── test_agents.py test_analyzer.py test_monitor.py test_reputation.py test_scoring.py
│       test_tune.py test_pipeline.py test_exits.py test_watcher.py
├── fixtures/http/*.json        # hand-authored, labelled "source": "hand-authored"
├── safety/test_no_signing_outside_live_stub.py
tools/                          # unchanged oracle (R53); tools/README.md gains desk_state.py row
vendor/grokbot-pumpfun/         # untouched oracle
```

### Port Map: root tools (STRUCT-002)

| Root (oracle) | Lines | New home | Notes for the port |
|---|---|---|---|
| `tools/jupiter_quote.py` | `:26` `JUPITER_QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"`; `get_quote` `:29-65`; `main` `:68-85`; timeout `:39` 12s | `tools/market/jupiter.py` | New URL `https://api.jup.ag/swap/v2/order` (R44/R54). Drop `taker`. Add `x-api-key` from `JUPITER_API_KEY`. Field trap below. |
| `tools/authority_check.py` | `DEFAULT_RPC` `:24`; `rpc_call` `:27-39`; `check_mint` `:42-75`; `main` `:78-86`; timeout `:34` 15s | `tools/onchain/authorities.py` | Method `getAccountInfo` with `{"encoding": "jsonParsed"}` `:44`. Output keys `ok,mint,mintAuthority,freezeAuthority,decimals,supply,isInitialized,extensions,hasMintAuthority,hasFreezeAuthority,rpc` `:61-73`. Error path returns `ok:false` `:47,75`. |
| `tools/holder_check.py` | `DEFAULT_RPC` `:26`; `rpc_call` `:29-41`; `holder_snapshot` `:44-86`; `main` `:89-102` | `tools/onchain/holders.py` | `getTokenLargestAccounts` `:46`; `top1/top5/top10` `:65-67`; sampled-only `note` `:79-83` must be kept verbatim (it is a disclosure). Default `--limit` 20 `:93`. |
| `tools/priority_fee.py` | `DEFAULT_RPC` `:26`; `rpc_call` `:29-41`; `estimate_priority_fee` `:44-93`; `main` `:96-115` | `tools/onchain/priority_fee.py` | `getRecentPrioritizationFees` with `[[]]` `:49`; percentile index `:65`; defaults percentile 50, multiplier 1.2 `:99-110`. Key `recommended_lamports_per_cu` `:85` is a mislabelled alias (MIGRATION row 77); decide whether to keep. |
| `tests/test_tools_cli.py` (oracle) | `JupiterQuoteContract` `:32-86`; `test_authority_main_exits_nonzero_on_error` `:107-117`; `test_holder_main_exits_nonzero_on_error` `:119-129`; `test_priority_fee_main_exits_nonzero_on_error` `:131-141` | `tests/characterization/test_*.py` | Six cases (R55): `:33`, `:41`, `:73` (Jupiter), `:107`, `:119`, `:131`. The `:109/:119/:129` references in CONTEXT are mock lines inside those bodies. |

Jupiter characterization is **not** 1:1 and must say so in the test module:
- `test_quote_url_is_current_lite_swap_api` (`:33-39`) and `test_get_quote_calls_configured_url` (`:41-71`) assert `lite-api.jup.ag/swap/v1/quote`. The port asserts `api.jup.ag/swap/v2/order` (R44).
- Unit trap: v1 `priceImpactPct` is a decimal ratio; v2 `priceImpact` is percentage points. Map `Ratio = priceImpact / 100` (STACK.md:196, SUMMARY.md:34). The root test fake at `:50-61` returns `priceImpactPct: "0"`; the port fixture must return `priceImpact`.
- Routing trap: without `taker`, all routers compete (STACK.md:197). Quote is informational only (R38).
- The root test monkeypatches `mod.requests.get` (`:67`). The port injects an `httpx.AsyncClient(transport=httpx.MockTransport(...))`.

Recorded v2 fields (STACK.md:195, observed live 2026-10-21 without key): `router`, `priceImpact`, `priceImpactPct` (deprecated), `otherAmountThreshold` (string), `routePlan`, `swapUsdValue`, `requestId`, `taker` (optional). Fields `inAmount`/`outAmount` are not listed in STACK.md's v2 note; treat them as [ASSUMED] until a fixture is recorded.

### Port Map: vendor engine (STRUCT-003)

| Vendor module | Key lines (verified) | New home | Phase 2 action |
|---|---|---|---|
| `src/monitor.py` | import `:23`; `passes_filter` `:95-111` (`few_buyers` `:110`); `LaunchMonitor` `:114`; `_buyers` `:126,142,152-153,198`; `handle_event` `:131-162`; `_promote` `:164-178` (`too_young`/`few_buyers` branch `:172`); `sweep` `:180-194` (`time.time` `:182`); `_evict_if_crowded` `:200-208`; `stream` `:212-252`; `connect` `:218`; `subscribeNewToken` `:219`; `time.time` `:222,242,243`; `wait_for` `:225`; `asyncio.sleep` `:251`; `_subscribe_trades` `:236,241,254-258`; `parse_create_event` `:74` `time.time` | `engine/monitor.py` | Clock everywhere; delete `_buyers` and trade subscribe; `few_buyers` -> `data_unavailable`; `connect(url, proxy=None, max_queue=…)`; `wait_for` -> `clock.timeout`. |
| `src/analyzer.py` | `httpx` `:17`; `Analyzer` `:38`; `__init__` `:41` (client injection); `Bearer` header `:51`; `_get` `:72-79`; 3-way gather `:83-86`; `parse_holder` `:114`; `parse_trade` `:128-136` (`signature=` `:136`); `compute_metrics` `:168`; `_veto_reason` `:285` | `engine/analyzer.py` | Keep `_get` returning None on failure (R47) plus health flag. Remove pump.fun `Bearer` unless a setting exists (Open Q). |
| `src/scoring.py` | `normalized_weights` `:21`; `compute_scores` `:35`; `passes_threshold` `:58`; `weakest_component` `:66`; docstring LLM note `:6` | `engine/scoring.py` | 1:1 logic; translate docstrings; no LLM. |
| `src/reputation.py` | `CreatorRecord` `:31`; `ReputationBook` `:48`; `time.time` `:72,94,147` | `engine/reputation.py` | Clock; persistence path comes from settings (`ops.reputation_path` `models.py:382`, becomes `var/reputation.json`). |
| `src/agents/base.py` | `GrokAgent` `:35`; `use_checker_model` `:41`; `model` property `:57-59`; payload `temperature: 0` (`_payload`); `_call`; `asyncio.sleep` `:149`; `random.random()` `:189`; `extract_json` `:223` | `engine/agents/base.py` | Clock for `:149`; injected rng for `:189`; `base_url` + `/chat/completions` (models.py:279 shows the full path today). |
| `src/agents/{checker,narrative,timing,auditor}.py` | checker `:53,57` (`use_checker_model=True`); narrative `:44` (Russian prompt `:18-40`); timing `:47`, `time.time` `:65,78,93`; auditor `:51` | `engine/agents/*.py` | Translate Russian prompt text (checker/narrative/timing/auditor have 27/19/26/24 Cyrillic lines). Prompt edits change `canonical_request_hash` (CONTEXT Discretion). |
| `src/risk.py` (exit half) | `ExitSignal` `:219`; `pnl_pct` `:226`; `stop_loss_triggered` `:232`; `exit_signal` `:238-280` (rules `:255,258,264,272`; `time.time` `:273`); `PositionWatcher` `:283-382`; `BLIND_AFTER` `:297`; `PEAK_PERSIST_STEP` `:293`; `__init__` `:299-307` (needs `RiskManager`); `check_once` `:317-352`; `run` `:362-371` (`asyncio.sleep` `:371`); `start`/`stop` `:373-382` | `engine/exits.py`, `engine/watcher.py` | See Pitfalls 12-13 (RiskManager dependency; Protocol). |
| `src/models.py` (domain half) | `Token` `:26` (`age_seconds` `time.time` `:53`); `Holder` `:64`; `Trade` `:75`; `TokenMetrics` `:89`; `AuditResult` `:114`; `NarrativeResult` `:156`; `TimingResult` `:181`; `CheckerResult` `:202`; `Scores` `:221`; `Analysis` `:231`; `Position` `:243`; `TradeDecision` `:258`; imports `copy,os,time,yaml` `:12-18` | `engine/models.py` | Domain classes only. `time` import must go (Pitfall 10). |
| `src/models.py` (config half) | `SecretModel` `:271`; `GrokConfig` `:277` (`base_url` `:279`, `fast_model` `:280`, `checker_model` `:281`); `JitoConfig` `:291` (**do not port**); `SolanaConfig` `:297` (`wallet_private_key` `:299`, **do not port**); `DataConfig` `:307` (`rest_url` `:309`, `ws_url` `:310`); `RiskConfig` `:318`; `FilterConfig` `:331`; `ScoringWeights` `:345`; `ScoringConfig` `:352`; `OpsConfig` `:378`; `Config` `:454` | `config/settings.py` (new sections) | Phase 1 `Settings` has none of these. See Pitfall 14. |
| `src/pipeline.py` | `Pipeline` `:65`; `time.time` `:99,100,198,394,403`; live flag `LIVE_WARNING` `:490`, `--i-understand-the-risk` `:509`, `load_and_check` `:514-540` | `engine/pipeline.py` | Keep engine stages only; drop live flags (CONTEXT). |
| `src/ops.py` (Phase 2 subset) | `Metrics` clock `:44`; `RateLimiter` `:90` (`time.monotonic` default `:97`, `asyncio.sleep` `:128`); `CallBudget` `:187` (`time.time` default `:193`); `GrokOps` `:235` (`precheck` `:248`); `CircuitBreaker` `:131` and `HealthServer` `:336` are **not** Phase 2 | `core/{ratelimit,budget,llm}.py` | Clock injection. `CircuitBreaker` belongs to Phase 4 `risk/breakers.py` (R52). |
| `scripts/tune.py` | 234 lines, 53 Cyrillic lines; `print` calls | `engine/tune.py` | Use `sys.stdout.write` (ruff T20 is selected and `engine` is not exempt). |

### Pattern 1: Injected Clock, RNG and HTTP client

Every ported class takes its dependencies in `__init__`, the way `analyzer.py:41` already injects `client`. The composition root (cli) builds `FixtureClock` for replay and `WallClock` for live, and `make_rng(seed)` from `replay/rng.py`.

```python
# Illustrative shape; not final code. Names follow Phase 1 modules.
class RpcClient:
    def __init__(self, endpoints: Sequence[str], client: httpx.AsyncClient, clock: Clock) -> None: ...
```

### Pattern 2: Replacing `asyncio.wait_for` and `asyncio.sleep`

`asyncio.wait_for(x, timeout=t)` is banned. Use the Clock's context manager (`replay/clock.py:65-68` for WallClock, `:132-158` for FixtureClock, raising builtin `TimeoutError`):

```python
# monitor.py:225 pattern
try:
    async with clock.timeout(sweeper_delay):
        raw = await ws.recv()
except TimeoutError:
    raw = None
```

### Pattern 3: CLI verb tree with absent subsystems

Current `cli.py` (`build_parser` `:66-80`) defines only `run` and `doctor`; `run` without `--once --replay` returns `EXIT_NOT_IMPLEMENTED = 5` (`:103-105`). Add every verb from the CLI verb surface table below as a subparser. Verbs whose subsystem is absent print one JSON object and exit 5. `paper buy`/`paper sell` must parse all five flags so `--help` lists them.

### Pattern 4: Skill frontmatter + body

`core/skill.py` `SkillManifest` (`extra="forbid"`, `bots` required, `min_length=1`, bot ids must start `bot-0` or equal `all`) is the schema that the frontmatter must satisfy. The `scripts/check.sh` parser (`:13-25`) reads `key: value` lines only and enforces name == directory, description ≤1024 chars, body ≤350 lines (`check.sh:44-55`).

### Pattern 5: Signing guard design

See the Validation Architecture section for the probe list. The walker must check `ast.Name.id`, `ast.Attribute.attr`, `ast.alias` (import names and `asname`), `ast.FunctionDef`/`AsyncFunctionDef`/`ClassDef` `.name`, `ast.arg.arg`, `ast.keyword.arg`, and `ast.Constant` string values, all by **exact** equality.

### Anti-patterns to avoid

- Copying vendor `time.time()` defaults into signatures (`risk.py:45`, `ops.py:44,97,193`). A default arg is still a banned reference.
- `now or time.time()` (`monitor.py:182`, `risk.py:273`, `reputation.py:147`, `timing.py:78`): `0.0` is falsy and becomes wall time. Take `now: float` explicitly.
- Building new skill bodies from design §3.1 verbatim (it contains `Jupiter lite-api`, see Pitfall 23).
- Adding an HTTP fixture as `*.jsonl` under `tests/fixtures/replay/smoke/` (Pitfall 20).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RPC retry with backoff | Custom loop with `random` jitter | tenacity `AsyncRetrying` with `sleep=clock.sleep` and a rng-seeded `wait` | STRUCT-002 locks tenacity; global `random` breaks R27 replay determinism |
| Websocket client | Raw socket or legacy `websockets.connect` | `websockets.asyncio.client.connect(url, proxy=None, max_queue=…)` | `test_network_block.py:50-70` forbids legacy; default proxy would silently reroute PumpPortal (STACK.md:125) |
| Timeouts | `asyncio.wait_for` / `asyncio.timeout` | `clock.timeout(seconds)` | Static guard `tests/safety/test_static_guards.py:25-37,88-92` |
| Virtual time / sleeps | `asyncio.sleep` | `clock.sleep` | Same guard; FixtureClock advances only via `advance_to` |
| HTTP mocking in tests | respx | `httpx.MockTransport` | conftest and test_network_block already use it |
| Settings and secrets | `os.environ` reads scattered in modules | Settings fields with `SecretStr` (for example `GrokConfig.api_key` `models.py:278`) | Phase 1 refuses key-bearing values in env, TOML and CLI (`settings.py:71,341-358`) |
| Jupiter fill price | Using the quote as fill | Bonding-curve reserves (`price_from_reserves`, `executor.py:85`) in Phase 4 | R38: quote is informational |
| Decision reason codes | Free-text reasons | ASCII codes (`no_metadata`, `curve_too_full`, `too_young`, `data_unavailable`, `stop_loss`, `take_profit`, `trailing_stop`, `max_hold`) | MIGRATION_MAP sec 3.3; tests assert codes only |
| Signature scanning | Regex over source text | AST walk with exact name match | Regex would flag `signature` (`analyzer.py:136`) and docstrings |
| Skill frontmatter parsing in tests | Hand regex | `SkillManifest` (`core/skill.py:32`) | Phase 1 model is designed for this (`docs/design/interfaces.md:1120-1123`) |

## Runtime State Inventory

Phase 2 is a migration (old paths retained as oracles until Phase 5). Answers per category:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Vendor `state/creators.json` (`ops.reputation_path`, `models.py:382`) holds creator reputation records. The new `ReputationBook` must read the same JSON shape or migrate. No `var/reputation.json` exists yet. Replay ledger `var/replay/smoke/ledger.sqlite` is recreated each run (`cli.py:119`), so no migration. | Code edit: point `ReputationBook` at settings path; no data migration in Phase 2 unless a live file exists. Verify with `ls state/` before planning. |
| Live service config | Hermes cron jobs are installed into Hermes HERMES_HOME (`hermes/cron/jobs.yaml:1-3`) with `prompt_file` pointers (`jobs.yaml:19,30,41,52,64,75`). The installed copies embed prompt text at install time. | Re-run `scripts/hermes-install-cron.sh` after prompts change. This is an operator action, not a repo change; list it in the phase close-out. |
| OS-registered state | `scripts/hermes-bootstrap.sh` and `hermes-install-cron.sh` set `PUMPGROK_ROOT`, `PUMPGROK_DESK`, `PUMPGROK_ROLE` (`hermes-bootstrap.sh:129-131`; `hermes-install-cron.sh:43-50`). Systemd or cron env files may hold them. | Code edit plus operator re-install. These names are refused by Settings (Pitfall 19). |
| Secrets and env vars | `JUPITER_API_KEY` (new, not `PUMPGROK_`-prefixed; R44), x.ai key (vendor name `GROKBOT_GROK_API_KEY`, `models.py:405`; new name not yet decided). `.env.example` says every key must be declared in Settings (`.env.example:4`). | Decide new names (Open Q 6); add `.env.example` lines; never commit values; `check_secrets.py` gate must still pass. |
| Build artifacts / installed packages | `.venv` lacks tenacity; `uv.lock` lacks tenacity. Root `tools/__pycache__/*.pyc` (MIGRATION rows 63, 66-70) stay until Phase 5 deletions. `vendor/grokbot-pumpfun` has `.ruff_cache`. | `uv lock && uv sync --frozen` after adding tenacity. No artifact deletion in Phase 2. |

**Canonical question answered:** after every file in the repo is updated, runtime systems still holding the old strings are: installed Hermes cron prompts (operator re-install), Hermes env files exporting `PUMPGROK_ROOT`/`PUMPGROK_DESK` (operator re-install), and `.venv` (re-sync). Nothing in the x.ai or Jupiter side changes names.

## Common Pitfalls

### Pitfall 1: Root test asserts `lite-api`, R44 forbids it
**What goes wrong:** Porting `test_quote_url_is_current_lite_swap_api` verbatim fails; asserting the new URL in the root oracle breaks R53.
**Why it happens:** `tests/test_tools_cli.py:37` and `:70` pin the old URL; `tools/jupiter_quote.py:26` still has it.
**How to avoid:** Leave root `tools/` and its test byte-identical (oracle). The characterization test asserts the new URL and documents each deviation in its module docstring.
**Warning signs:** Edits to `tools/jupiter_quote.py`.

### Pitfall 2: Jupiter field-name and unit trap
**What goes wrong:** Reading `priceImpactPct` from v2 gives percent points as if they were a ratio (100x error).
**How to avoid:** `priceImpact / 100` into a `Ratio` (STACK.md:196). Name the output field so the unit is explicit.

### Pitfall 3: `JUPITER_API_KEY` is not `PUMPGROK_`-prefixed
**What goes wrong:** Settings reads `PUMPGROK_*` only (`env_prefix="PUMPGROK_"`, `settings.py:115-119`). A plain `JUPITER_API_KEY` is silently ignored, so the adapter runs keyless (0.5 RPS, R44) without warning.
**How to avoid:** See Open Question 6. R44 requires a WARNING when the key is absent (autonomous-paper startup, later phase). Phase 2 should at least log the keyless state.

### Pitfall 4: `rpc.endpoints[]` URLs with embedded keys are refused
**What goes wrong:** Paid RPC providers often put the key in the query string. `KEY_BEARING_VALUE_RE` (`settings.py:71`: `api-key=|token=|key=`) refuses such values in env, TOML and CLI (`settings.py:218-313,341-358`), so startup fails.
**How to avoid:** Endpoints are keyless URLs; the provider key travels in a header or a separate SecretStr. Confirm provider support before choosing (Open Q 7).

### Pitfall 5: Failover must not leak the URL in errors
**What goes wrong:** `httpx` exception strings include the request URL; `raise_for_status` messages too. Root tools return `str(e)` directly (`tools/jupiter_quote.py:43`, `authority_check.py:75`).
**How to avoid:** Keyless URLs make this safe today, but redact at the RPC client boundary and never include headers.

### Pitfall 6: `test_get_quote_calls_configured_url` monkeypatches `requests`
**What goes wrong:** Patching `mod.requests.get` has no equivalent for httpx; a naive port makes the test hit the network, which conftest blocks (`tests/conftest.py:32`).
**How to avoid:** Inject `httpx.AsyncClient(transport=httpx.MockTransport(handler))`. Assert on `request.url` in the handler.

### Pitfall 7: `monitor.py` 1:1 claim is wrong after R45/R46
**What goes wrong:** MIGRATION_MAP row 110 and sec 3.1 say monitor is 1:1 (21 tests). About 7 `test_filter.py` cases depend on trade events or the trade subscription: `:69-73` (`test_buyers_boundary`, `few_buyers`), `:137-156` (buy events), `:158-168` (`unique_buyers == 1`), `:199-207` (buy event in sweep), `:285-304` (asserts `subscribeTokenTrade`/`unsubscribeTokenTrade` `:303-304`), `:307-327` (buy events `:311-313`), `:329-343` (buy events `:341-343`).
**How to avoid:** Rewrite those as `data_unavailable` / no-trade-subscription cases; state in the module docstring which vendor tests were adapted and why. Do not count them as 1:1.

### Pitfall 8: `few_buyers` must become `data_unavailable` and fail closed
**What goes wrong:** A token with no trade evidence would otherwise pass the buyer check (the count is 0 but the ASCII code is missing).
**How to avoid:** Missing trade evidence returns `data_unavailable` (CONTEXT). `passes_filter` must not return `ok` in that case. Test both branches.

### Pitfall 9: Agent jitter uses ambient `random`
**What goes wrong:** `agents/base.py:189` (`random.random()`) is banned by `_is_ambient_random` (`test_static_guards.py:40-42`). MIGRATION_MAP row 101 says "own `_backoff` kept", which fails the static test as written.
**How to avoid:** Pass the seeded `random.Random` from `make_rng` (`replay/rng.py`) into `GrokAgent`. Use `rng.random()` (instance method, not module function; ruff S311 targets the module).

### Pitfall 10: `Token.age_seconds` and the domain "verbatim" claim
**What goes wrong:** `models.py:53` calls `time.time()` inside a domain model method. The "domain half verbatim" claim (MIGRATION row 109) cannot hold.
**How to avoid:** Change the method to take `now: float` (or store a clock reference). Update every caller (`monitor.py`, `scoring`, tests).

### Pitfall 11: `clock.timeout` replaces `wait_for` only as a context manager
**What goes wrong:** Passing `timeout=` or treating the result as a value fails.
**How to avoid:** Use Pattern 2. `FixtureClock.timeout` cancels the task and raises `TimeoutError` (`clock.py:149-153`).

### Pitfall 12: `PositionWatcher` depends on `RiskManager`
**What goes wrong:** `PositionWatcher.__init__` takes `manager: RiskManager` (`risk.py:299-307`) and reads `manager.positions`, `manager.risk`, `manager.persist()` (`:315,322,339,351,363`). `RiskManager` is Phase 4 (`risk/engine.py`, MIGRATION row 114). Porting the class as-is pulls in the whole risk module.
**How to avoid:** Define a `PositionBook` Protocol in `engine/watcher.py` exposing `positions`, `exit_config`, `poll_seconds`, `persist()`. Phase 2 test doubles implement it. The real implementation arrives in Phase 4. The test fixture `manager` (test_risk.py:42-44) is replaced by the double, not a behaviour change.

### Pitfall 13: `exit_signal` default `now`
**What goes wrong:** `exit_signal(..., now: float | None = None)` (`risk.py:242`) with `now or time.time()` (`:273`).
**How to avoid:** `now: float` required in the ported signature; the watcher passes `clock.now()`.

### Pitfall 14: Settings has no engine sections and `extra="forbid"`
**What goes wrong:** Only `mode`, `execution`, `risk`, `replay`, `live` exist (`settings.py:123-127`). `extra="forbid"` (`:118`) rejects unknown keys in TOML. The engine cannot read `data.ws_url`, `grok.*`, `filter.*`, `scoring.*`, `exits.*`, `rpc.endpoints`.
**How to avoid:** Add sections in Phase 2 and add matching overlay keys to `src/pumpgrok/config/overlays/{dev,paper,live}.toml`. `allowed_env_names()` derives from model fields (`settings.py:200-214`), so new fields are auto-allowed; `.env.example` must list the ones that carry values.

### Pitfall 15: `risk` name collision
**What goes wrong:** Phase 1 `risk` is `RiskBudget` (R20 keys, `settings.py:125`). Vendor `RiskConfig` (`models.py:318-327`) holds exit thresholds (`stop_loss_pct` 30.0, `take_profit_pct` 120.0, `trailing_stop_pct` 35.0, `max_hold_seconds` 3600.0) and `stop_loss_poll_seconds`.
**How to avoid:** Put exit thresholds in a separate settings section (for example `exits`). Do not extend `RiskBudget`, which belongs to the R20 surface.

### Pitfall 16: Engine replay cannot produce `buy` from the smoke fixture
**What goes wrong:** `tests/fixtures/replay/smoke/events.jsonl` has four `kind: tick` rows with `mint`, `S`, `T`, `complete`, `source` and no `txType`, holders, trades or metadata (verified this session). The engine has nothing to score.
**How to avoid:** Map each tick to a candidate with no evidence, so `passes_filter` returns `data_unavailable` (fail closed) and the decision is `skip`. The CONTEXT and ROADMAP wording "skip or buy" both pass. Document the adapter. Do not edit the smoke dataset (its manifest digest is fixed, `manifest.json`).

### Pitfall 17: Absent verb exit code is 5, not 2
**What goes wrong:** CONTEXT (Discretion) says exit 2. `cli.py:5-6` reserves 2 for ledger inconsistency. `tests/test_skip_cycle.py:93-94` asserts exit 5 for `run` without replay.
**How to avoid:** Use `EXIT_NOT_IMPLEMENTED = 5` (`cli.py:48`). See Open Q 1.

### Pitfall 18: `doctor` expectations
**What goes wrong:** `tests/test_skip_cycle.py:157` asserts `warn engine` and `warn tools`. Both become `ok` once `src/pumpgrok/engine/` and `src/pumpgrok/tools/` exist (`doctor.py:16-28`). CONTEXT's checkpoint line names `risk` and `reporting`, which are not in `SUBSYSTEMS`.
**How to avoid:** Update the test list to `("gateway", "supervisor", "reports")` and keep the `SUBSYSTEMS` tuple. Note the mismatch in the phase summary.

### Pitfall 19: Hermes scripts export names Settings refuses
**What goes wrong:** Any `PUMPGROK_*` env name not declared in Settings is refused (`find_unknown_env`, `settings.py:293-295`, run on the full process env via `collect_startup_problems(os.environ)` at `:335`). `PUMPGROK_ROOT`, `PUMPGROK_DESK`, `PUMPGROK_ROLE` would make `pumpgrok` exit 1 inside those scripts (cron env, `hermes-install-cron.sh:43-50`).
**How to avoid:** Do not export them, or declare them as settings. Preferred: cron runs `uv run --project "$ROOT" pumpgrok ...` with `cwd` set. See Open Q 5.

### Pitfall 20: Fixtures must not break the replay loader
**What goes wrong:** `replay/fixtures.py` rejects any `*.jsonl` in a dataset dir not listed in the manifest (`fixtures.py:117-118`). Adding HTTP fixtures there breaks the checkpoint.
**How to avoid:** HTTP fixtures go in `tests/fixtures/http/*.json` (STRUCT-002 names this path). Leave `tests/fixtures/replay/smoke/` untouched.

### Pitfall 21: `JournalNote` is a closed model
**What goes wrong:** `JournalNote` has `extra="forbid"` (`ledger/events.py:46-49`) and only `source, seat, note_kind, text, refs` (`:282-289`). CONTEXT wants `engine_decision`/`disposition` recorded there; those fields do not exist. `note_kind` must come from `NoteKind` (`events.py:75-...`), which has no `cycle`.
**How to avoid:** Encode the decision in `text` (single line, ASCII codes, e.g. `engine decision=skip reason=data_unavailable`). Choose a `NoteKind` member. `test_skip_cycle.py:71` asserts `note_kind == "note"` and will need an update if the kind changes.

### Pitfall 22: The replay path must not start network or loops
**What goes wrong:** `FixtureClock.sleep` only resumes on `advance_to` (`clock.py:121-130`). Calling `LaunchMonitor.stream()` in replay hangs. Startup `GET /v1/models` (CONTEXT Discretion, R48) is network access; FOUND-013's goal is "no network access" (ROADMAP Phase 1 goal).
**How to avoid:** Replay calls pure engine functions; `/v1/models` resolution runs only on the live path. In replay, record `model resolution: skipped (replay)` in `text`.

### Pitfall 23: Skill text must not contain `lite-api`
**What goes wrong:** Design §3.1 `solana-market-data` row says "Jupiter lite-api" (`docs/design/interfaces.md` table row), and R14 says rewrite to lite-api. Both conflict with criterion 3 and R44.
**How to avoid:** Write skill prose with `api.jup.ag/swap/v2/order`. R14 is superseded by R44/R54.

### Pitfall 24: `--max-micro` lingers in more places than the skill
**What goes wrong:** `skills/jupiter-routing/SKILL.md:18` has it (criterion 3 catches it). `tools/README.md:38` and `ARCHITECTURE.md:242` also name it. The root `priority_fee.py` has no `--max-micro` flag at all (argparse `:97-110`), so the example was never valid.
**How to avoid:** Remove from skills (required) and from docs. Leave `tools/priority_fee.py` as the oracle. The field name `max_micro_lamports` stays (R40; `contracts/tool-rosters/bot-04-sniper.yaml:239`).

### Pitfall 25: Cron prompts call root tools today
**What goes wrong:** All six prompts run `python "$PUMPGROK_ROOT/tools/desk_state.py"`, `pipeline_evidence.py` or `ticket_helper.py` (verified in `hermes/cron/prompts/*.md`, e.g. `risk-audit.md:12-13`, `scout-pipeline.md:13-18`, `chief-pickup.md:13-17`). STRUCT-005 requires `pumpgrok` only.
**How to avoid:** Rewrite to `pumpgrok state status`, `pumpgrok risk audit --pending`, `pumpgrok scout pipeline --candidates --limit 5`, `pumpgrok ticket next`, etc. (MIGRATION_MAP sec 4.3). Because those verbs return not-yet-implemented, each prompt must handle exit 5 (`status: not-yet-implemented`) without writing fake results.

### Pitfall 26: Skill oracle test pins `ticket_helper.py`
**What goes wrong:** `tests/test_tools_cli.py:191-195` requires `skills/desk-trade-lifecycle/SKILL.md` to contain `ticket_helper.py next` and `ticket_helper.py create`. The design (§3.1) rewrites that skill to `pumpgrok ticket next|create|list`. Rewriting the skill fails the root oracle; leaving it violates the clean cutover.
**How to avoid:** See Open Q 10. `tools/README.md` must keep `ticket_helper.py next` (`test_tools_cli.py:197-200`) and gains the `desk_state.py` row (STRUCT-007).

### Pitfall 27: Signing guard false negatives
**What goes wrong:** A walker that checks only `Name` and `Attribute` misses `def sign(...)`, `sign=` keyword args, `from x import Keypair as K` (alias name is `Keypair`), and `getattr(obj, "sendTransaction")`.
**How to avoid:** Check every node type listed in Pattern 5. Add a PROBES list like `test_static_guards.py:147-200` with positive and negative probes.

### Pitfall 28: `ruff` and `mypy` gates on ported code
**What goes wrong:** `select` includes `T20` (print), `S` (bandit), `PL` (pylint complexity), `ASYNC`, `RUF` (`pyproject.toml` `[tool.ruff.lint]`). `mypy --strict` runs on `pumpgrok` (`[tool.mypy]`, Makefile `typecheck: mypy src/`). `scripts/tune.py` uses `print`; `pipeline.py` is large and branchy (PLR0911/0912/0915 risk).
**How to avoid:** Write CLI output with `sys.stdout.write`; split functions instead of adding `noqa`; type every ported signature (vendor `Any`s need concrete types).

### Pitfall 29: Cyrillic check silently passes without a UTF-8 locale
**What goes wrong:** `grep -P '\p{Cyrillic}'` only matches multibyte text under a UTF-8 locale. Under `LANG=C` the gate passes trivially.
**How to avoid:** Run as `LC_ALL=C.UTF-8 grep -rlP '\p{Cyrillic}' src/pumpgrok/engine/` and add a positive control in the test (grep the vendor tree and expect hits). Confirmed in this session: the vendor tree produces hits under the default shell locale.

### Pitfall 30: Shell `grep` wrapper in this environment
**What goes wrong:** In this shell `grep` is a builtin wrapper that rejected `grep -rn -e lite-api -e '--max-micro' skills/` (usage error). Criterion 3 would then fail for the wrong reason.
**How to avoid:** Verify with `/usr/bin/grep` (GNU) or `grep -rn -e lite-api -e '\-\-max-micro' skills/`. Record which binary the CI uses.

### Pitfall 31: Ownership manifest does not cover flat characterization names
**What goes wrong:** `ownership.yaml:379-394` assigns owners to `tests/characterization/engine/**`, `execution/**`, `risk/**`, `ledger/**` subdirectories only. Flat `test_monitor.py` falls through to `tests/characterization/**` -> bot-02-risk, which contradicts R36 ("owner of the module it pins"). `src/pumpgrok/engine/reputation.py` (MIGRATION sec 3.2 says bot-05-rug) has no specific rule and defaults to bot-08-signal (`ownership.yaml:316`).
**How to avoid:** Add flat-file rules for each `tests/characterization/test_<module>.py` and for `engine/reputation.py`, placed after the directory rules (last match wins). `check_ownership.py --validate-manifest` must still pass.

### Pitfall 32: Test basename collisions
**What goes wrong:** Only `tests/harness/__init__.py` exists; the rest of `tests/` has no packages (`find`). Under pytest's default prepend import mode, two `test_X.py` basenames in different directories collide.
**How to avoid:** Check `test_monitor.py`, `test_pipeline.py`, `test_tune.py` against the existing tree before creating them. The flat names in ROADMAP SC1 are fixed, so verify no other `test_<name>.py` exists under `tests/` or `ci/tests/`.

### Pitfall 33: Plugin manifests and placeholder org
**What goes wrong:** `plugin.json:8,11`, `.claude-plugin/plugin.json`, marketplace files use `your-org`, and `"license": "MIT"` (`.claude-plugin/plugin.json:8`, `plugin.json:10`, `.grok-plugin/plugin.json:8`, `.cursor-plugin/plugin.json:8`). `scripts/check.sh` placeholder scan covers these files.
**How to avoid:** Set `"license": "AGPL-3.0"` and replace the org with `swcstudiospace` (repo remote and `pyproject.toml` Homepage use it). See Open Q 17.

### Pitfall 34: `pyproject.toml` requests comment
**What goes wrong:** The dev-group comment says `requests` is "removed with tools/ in Phase 2" (`pyproject.toml`, dev group). R53 keeps `tools/` until Phase 5, so `requests` must stay for `tests/test_tools_cli.py`.
**How to avoid:** Keep `requests`, correct the comment to "Phase 5".

### Pitfall 35: CLI `forbidden_owners` needs caller identity
**What goes wrong:** Enforcing `forbidden_owners: [sniper, exit]` (`hermes/cron/jobs.yaml:79`) requires knowing which seat calls the verb. Nothing in `cli.py` or `settings.py` carries a seat identity; `bind_seat` (`logging/json.py`) is used only for the replay cycle (`cli.py:121`).
**How to avoid:** See Open Q 12.

### Pitfall 36: `uv` and dependency sync
**What goes wrong:** Adding tenacity without `uv lock` leaves `uv.lock` inconsistent (`uv sync --frozen` fails). The `.venv` lacks tenacity, so `from tenacity import AsyncRetrying` fails at import.
**How to avoid:** Lock and commit `uv.lock` in the same change as `pyproject.toml`.

## Code Examples

Patterns grounded in repo APIs. Signatures marked [ASSUMED] must be confirmed against the installed package before use.

### Websocket connect (R49 V-7)
```python
# Source: .planning/research/STACK.md:31 (verified against websockets 17.3 source per STACK.md:15)
from websockets.asyncio.client import connect

async with connect(url, proxy=None, max_queue=max_queue) as ws:
    await ws.send(json.dumps({"method": "subscribeNewToken"}))
```

### RPC retry with virtual sleep [ASSUMED signature]
```python
# Source: STACK.md:52 names AsyncRetrying; `sleep=` keyword and the rng-seeded wait are ASSUMED
from tenacity import AsyncRetrying, stop_after_attempt, retry_if_exception_type

async for attempt in AsyncRetrying(
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((httpx.TimeoutException, RpcRetryable)),
    wait=seeded_jitter_wait(rng),          # custom callable; avoids global random
    sleep=clock.sleep,                     # R27
    reraise=True,
):
    with attempt:
        ...
```

### Explicit `now` in exit rules
```python
# Source: risk.py:238-280 rewritten; rule order preserved (risk.py:255,258,264,272)
def exit_signal(position: Position, price: float, cfg: ExitConfig, now: float) -> ExitSignal | None: ...
```

### Settings-declared secret
```python
# Source: models.py:278 pattern (SecretStr), placed in settings.py under a new section
class JupiterSettings(BaseModel):
    api_key: SecretStr = SecretStr("")  # populated from JUPITER_API_KEY; see Open Q 6
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `lite-api.jup.ag/swap/v1/quote` | `api.jup.ag/swap/v2/order` (quote-only) | Swap V1 "no longer actively maintained" (STACK.md:193) | Root tool and its test stay on V1 as oracle; new port uses V2 |
| `websockets.connect` (legacy) | `websockets.asyncio.client.connect` | Deprecated since 14.0 (STACK.md:50) | Enforced by test_network_block.py:50-70 |
| Default websocket proxy | `proxy=None` explicit | websockets 15.0 default `proxy=True` (STACK.md:31,125) | PumpPortal path must not follow env proxies |
| Default `max_queue=16` | explicit `max_queue` | STACK.md:126 recommends explicit for bursts | Open Q 16 |
| x.ai `grok-4`, `grok-4-fast` | `grok-4.3` (effort low), `grok-4.20-0309-non-reasoning` | Retired per xAI notice, effective 2026-05-15 (R48) | Config values only, never hard-coded |

**Deprecated/outdated in repo docs (update in Phase 2):**
- `README.md:18` names `tools/paper_sim.py` and `micro-live`.
- `ARCHITECTURE.md:26,173,234,242` (lite-api, micro-live, `--max-micro`).
- `AGENTS.md:90,123,209,256,264,342` says keep lite-api v1 "behind a config flag with a removal date" (`AGENTS.md:264`), which R44 forbids ("removed, not kept behind a flag"). AGENTS.md is bot-02-risk owned (ownership `**/*.md`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | tenacity `AsyncRetrying` accepts `sleep=<async callable>` and a custom `wait` callable | Standard Stack; Code Examples | RPC retries cannot be virtualized; retry tests hang or hit real sleep |
| A2 | Jupiter v2 `order` response includes `inAmount` and `outAmount` (not listed in STACK.md:195) | Port Map: root tools | Quote fixture or mapper wrong; live shape differs |
| A3 | x.ai `reasoning_effort` (or equivalent) field name for effort low on `grok-4.3` | Standard Stack (no); Architecture (agents) | Strong checker request rejected at runtime |
| A4 | `GET /v1/models` returns the configured IDs in a form usable for resolution | Pitfall 22 | Startup resolution logic wrong; live-only so no replay impact |
| A5 | `scripts/hermes-*.sh` cron env is the only place `PUMPGROK_ROOT/DESK/ROLE` reach the process | Runtime State | Other env files may also carry them |
| A6 | `ledger/events.py` `NoteKind` members beyond `note` are all unused by Phase 1 tests | Pitfall 21 | Changing note kind breaks a test not yet found |
| A7 | Hand-authored Jupiter/RPC fixtures match live shapes closely enough for characterization | Port Map | Characterization passes but live fails; Phase 3 must re-record |

## Open Questions

1. **Absent-verb exit code.**
   - What we know: CONTEXT says 2; `cli.py:5-6` reserves 2 for ledger inconsistency; `cli.py:48` defines `EXIT_NOT_IMPLEMENTED = 5`; `tests/test_skip_cycle.py:93-94` asserts 5.
   - Recommendation: exit 5 with the JSON `{"ok": false, "status": "not-yet-implemented", "verb": "<name>"}` on stdout and one stderr line. Record the deviation from CONTEXT in the summary.

2. **Engine decision row shape.**
   - What we know: one `JournalNote` (closed model), `NoteKind` without `cycle`; the test asserts `note_kind == "note"` (`test_skip_cycle.py:71`).
   - Recommendation: keep `seat="desk"`, use a `NoteKind` member that fits a verdict (for example `verdict`), put `engine decision=<skip|buy> reason=<ASCII>` in `text`, and update the test line. Do not add columns.

3. **Startup model resolution in replay.**
   - Recommendation: skip the `/v1/models` GET in replay and in tests; write `model resolution: skipped (replay)` into the JournalNote text. Live resolution is Phase 4 wiring but its code lands now.

4. **Smoke ticks to engine input.**
   - Recommendation: a documented adapter that turns a tick into an evidence-less candidate; `passes_filter` returns `data_unavailable`; decision `skip`. Covered by a test. Do not edit the smoke dataset.

5. **Hermes env names.**
   - Recommendation: stop exporting `PUMPGROK_ROOT`, `PUMPGROK_DESK`, `PUMPGROK_ROLE` into the process env. Run the CLI with `cwd` set (the cron job already sets `cwd: "${DESK}"`, `hermes-bootstrap.sh:197`) and reference the repo via `uv run --project`. Re-run the installer afterwards. Alternative (declare the names in Settings) widens the config surface for no benefit.

6. **`JUPITER_API_KEY` and the x.ai key names.**
   - Recommendation: `JUPITER_API_KEY` is read once in the composition root and wrapped in `SecretStr`; it is not a Settings field because Settings is `PUMPGROK_`-only and TOML must never hold it. The x.ai key is `PUMPGROK_GROK__API_KEY` (follows the Phase 1 nested-delimiter convention in `.env.example:2`). Both need `.env.example` lines with placeholders.

7. **Paid RPC keys.**
   - Recommendation: `rpc.endpoints` holds keyless URLs; a separate `rpc.api_key` SecretStr is sent as a header if the provider supports headers. Confirm provider support before Phase 3 (not blocking Phase 2, which can use keyless public RPC in tests).

8. **Settings schema.**
   - Recommendation: add `data` (`rest_url`, `ws_url`, `ws_max_queue`=16), `rpc` (`endpoints`), `grok` (`base_url`=`https://api.x.ai/v1`, `strong_model`=`grok-4.3`, `strong_effort`=`low`, `fast_model`=`grok-4.20-0309-non-reasoning`, `api_key`), `jupiter` (`quote_url`), `filter`, `scoring`, `exits` (distinct from `risk`), `ops` (`reputation_path`). Mirror keys into the three overlay TOMLs.

9. **Skill `bots`/`gates` source.**
   - What we know: MIGRATION_MAP sec 4.2 and design §3.1 disagree for several skills (for example `desk-incident-response`: sec 4.2 `[all]`/`[G-2, G-5]` vs design `[bot-00-chief, bot-02-risk]`/`[G-2]`; `desk-monitoring`; `desk-strategy-lab`). MIGRATION says ROSTER.md and ownership.yaml are authoritative. `docs/ROSTER.md` was **not** read in this research.
   - Recommendation: the planner reads `docs/ROSTER.md` and `contracts/tool-rosters/*.yaml`, then records one table that wins. Until then, use the MIGRATION_MAP sec 4.2 values with a note.

10. **Root skill-text oracle.**
    - Recommendation: move the two skill/README text assertions (`test_tools_cli.py:190-200`) into a docs test that asserts the new names, and document the change, because the skill is being rewritten (clean cutover). Keep `tools/README.md` containing `ticket_helper.py next` (oracle) plus the `desk_state.py` row.

11. **Root Jupiter oracle.**
    - Recommendation: leave `tools/jupiter_quote.py` and its two lite-api assertions unchanged (R53). The characterization file documents the divergence. Note that R44 "removed, not kept" applies to the new adapter, not the oracle.

12. **`forbidden_owners` enforcement.**
    - What we know: no seat identity exists on the CLI today.
    - Recommendation: add a required `--seat` option to the paper and state verbs (not exposed to cron prompts), refused when the value is `sniper` or `exit`. Confirm with the user; this is a design decision, not derivable from repo docs.

13. **Scope of notify, social, and core ratelimit/budget/llm.**
    - What we know: CONTEXT locks them for Phase 2. No ROADMAP criterion or test list mentions them; `test_ops.py` (24) is not in the characterization list.
    - Recommendation: implement them with at least the ported behaviour tests from `vendor/grokbot-pumpfun/tests/test_ops.py` and `tests/test_alerts.py`, or explicitly defer with a note. Do not leave stubs.

14. **Doctor SUBSYSTEMS list.**
    - Recommendation: keep `doctor.py:16-28` and update the test (Pitfall 18). Clarify the CONTEXT checkpoint wording in the plan.

15. **Monitor characterization.**
    - Recommendation: adapt the seven trade-dependent tests (Pitfall 7) and add explicit `data_unavailable` and no-trade-subscription tests.

16. **`ws_max_queue` default.**
    - CONTEXT says 16 (the library default). STACK.md:126 recommends an explicit larger value such as 1024 for bursts.
    - Recommendation: keep 16 as CONTEXT decided, and flag the STACK.md recommendation in the plan.

17. **Manifest org value.**
    - Recommendation: `swcstudiospace` (`pyproject.toml` Homepage; DISCOVERY remote). MIGRATION sec 8 lists it as unknown.

18. **`micro-live` guard in `scripts/hermes-verify-isolation.sh:52-53`.**
    - Recommendation: rewrite to reject any engagement value outside `research|paper` without naming the retired level. R42 removes the string; the guard keeps its meaning.

19. **Skill and manifest docs carrying micro-live.**
    - Files: `skills/desk-monitoring/SKILL.md:12`, `skills/desk-operating-model/SKILL.md:36`, `skills/desk-strategy-lab/SKILL.md:17`, `skills/pumpgrok-setup/SKILL.md:45`, `rules/pumpgrok-team.mdc:46`, `SETUP.md:176,229`, `ARCHITECTURE.md:173,234`, `README.md:18`. Criterion 3 does not test micro-live, but R42 and STRUCT-007 require removal. Plan them explicitly.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | project pin `>=3.12,<3.13` | ✓ | 3.12.3 (`/usr/bin/python3`) | — |
| uv | `uv run`, `uv lock`, `uv sync --frozen` | ✓ | 0.11.26 (pin in STACK V-2 is 0.13.4) | Use installed uv; record version |
| `.venv` deps | root tests | ✓ except tenacity | httpx 0.28.1, websockets 17.3, pydantic 2.14.1, pydantic-settings 2.16.1, pytest 9.1.1, pytest-asyncio 1.4.0, requests 2.34.2 | Run `uv lock && uv sync` after adding tenacity |
| tenacity | RPC client | ✗ in `.venv` and `uv.lock` | (9.2.1 on index) | Must add; no fallback (STRUCT-002) |
| System python3 vendor deps | vendor oracle `python3 -m pytest -q` | ✓ | httpx 0.28.1, pydantic 2.13.4, websockets 16.0, pyyaml 6.0.3, pytest 9.1.1, pytest-asyncio 1.4.0 | No /tmp venv needed: vendor imports only these (grep of `vendor/grokbot-pumpfun/{src,tests,scripts}` shows no `solders` or `solana` import) |
| solders / solana | vendor pyproject lists them | ✗ | — | Not needed; not imported |
| PyPI network | `uv lock` | ✓ | `pip index versions tenacity` succeeded this session | — |
| Docker | `docker compose` gates | not checked | — | Not part of Phase 2 success criteria |

**Missing dependencies with no fallback:** tenacity (must be added to pyproject and lock; STRUCT-002 mandates it).
**Missing dependencies with fallback:** none.

## Validation Architecture

Test framework: pytest 9.1.1 with pytest-asyncio 1.4.0 (`asyncio_mode = "auto"`), `addopts = "-q --strict-markers"`, markers `replay` and `characterization` (`pyproject.toml` `[tool.pytest.ini_options]`).

### Success criteria mapped to commands

| Criterion | Requirement | Automated command | Exists now? |
|-----------|-------------|-------------------|-------------|
| SC1 | STRUCT-002 | `uv run pytest -q tests/characterization/test_authority_check.py tests/characterization/test_holder_check.py tests/characterization/test_jupiter_quote.py tests/characterization/test_priority_fee.py` | ✗ Wave 0 |
| SC2a | STRUCT-003 | `cd vendor/grokbot-pumpfun && python3 -m pytest -q` | ✓ (oracle, 264 tests) |
| SC2b | STRUCT-003 | `uv run pytest -q tests/characterization/` | ✗ Wave 0 |
| SC2c | STRUCT-003 | `! LC_ALL=C.UTF-8 grep -rlP '\p{Cyrillic}' src/pumpgrok/engine/` (add positive control) | ✗ engine missing |
| SC3 | STRUCT-007 | `test "$(grep -l '^bots:' skills/*/SKILL.md \| wc -l)" -eq 23 && test "$(grep -l '^gates:' skills/*/SKILL.md \| wc -l)" -eq 23 && ! /usr/bin/grep -rn -e lite-api -e '--max-micro' skills/` | ✗ currently 0 and fails on `--max-micro` (jupiter-routing:18) |
| SC4a | STRUCT-005 | `uv run pumpgrok --help` | ✓ exits 0 today |
| SC4b | STRUCT-005 | `uv run pumpgrok paper buy --help` lists `--ticket --mint --size-sol --slippage-bps --approval-id` | ✗ no `paper` verb today |
| SC5 | SEC-003 | `uv run pytest -q tests/safety/test_no_signing_outside_live_stub.py` | ✗ Wave 0 |
| Checkpoint | STRUCT-003 | `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` prints one `skip` or `buy` | ✗ prints nothing today; exit 0 with JournalNote |
| Regression | Phase 1 | `uv run pytest -q` (including `tests/test_skip_cycle.py`, `tests/safety/test_static_guards.py`, `tests/test_network_block.py`) | ✓ (update line 157 per Pitfall 18) |
| Lint/type | all | `make lint typecheck` (`ruff check`, `ruff format --check`, `mypy src/`) | ✓ |
| Gates | all | `python3 ci/gates/check_ownership.py --validate-manifest`, `python3 ci/gates/check_desk_integrity.py --repo .`, `./scripts/check.sh` | ✓ (check.sh requires skill rules; ownership needs Pitfall 31 rules) |

Sampling rate: run the targeted test file after each port module; run `uv run pytest -q` after each deliverable; run the vendor oracle and the checkpoint once at phase end.

### Test design for SC5 (signing guard)

- Walk `src/pumpgrok/**/*.py` with `ast`. Skip files whose POSIX relpath starts with `execution/live/`.
- Forbidden set (exact equality): `{"sign", "send_transaction", "sendTransaction", "Keypair"}`.
- Node checks: `Name.id`, `Attribute.attr`, `alias.name`/`alias.asname`, `FunctionDef`/`AsyncFunctionDef`/`ClassDef.name`, `arg.arg`, `keyword.arg`, `Constant` with `str` value.
- Positive probes (must flag): `def sign(x): ...`; `sig = Keypair()`; `x.send_transaction(t)`; `getattr(c, "sendTransaction")`; `from solders.keypair import Keypair as K` (alias name matches); `f(sign=1)`.
- Negative probes (must not flag): `signature=raw.get("signature")`, `"never a real signature"` in a docstring, `signature_hash = 1`, the same names under `execution/live/`.
- Also assert `execution/live/live_adapter.py` has no `solders`/`solana` import and no `Transaction`/`VersionedTransaction`/`Message` names (covers "the live stub builds no transaction").

### Wave 0 gaps (create before porting)

- [ ] `tests/characterization/` (flat files for the 13 modules)
- [ ] `tests/fixtures/http/` hand-authored JSON for authority, holder, priority fee, Jupiter v2 order, x.ai chat, pump.fun REST, PumpPortal create event
- [ ] `tests/safety/test_no_signing_outside_live_stub.py` with probes
- [ ] `tenacity` dependency and `uv.lock`
- [ ] `tests/test_skip_cycle.py` updates (line 71 note kind if changed; line 157 doctor list)
- [ ] ownership rules for flat characterization names and `engine/reputation.py`
- [ ] `tests/characterization/` naming check against the rest of `tests/`

## Security Domain

Phase 2 has no live writes. The relevant ASVS categories are input validation (CLI and config), secrets handling, and error/log hygiene.

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (no operator auth in Phase 2) |
| V3 Session Management | no | — |
| V4 Access Control | yes | `forbidden_owners` enforcement (Open Q 12); live gate stays refused |
| V5 Input Validation | yes | argparse with `UsageError` (`cli.py:57-63`); `--ticket` pattern `^SOL-\d{8}-\d{3}$` (`core/approvals.py` `ticket_id`); `--size-sol` positive; `--mint` base58 length check; `--slippage-bps` int range |
| V6 Cryptography | yes (negative) | No signing, no key material; SEC-003 proves absence; never hand-roll |
| V7 Error Handling and Logging | yes | Redact `str(exc)` from httpx (Pitfall 5); `SecretStr` for keys; no key in logs (`settings.py:85` `mask`) |
| V8 Data Protection | yes | Key-bearing values refused (`settings.py:71,218-313`); `.env` never read (`settings.py:20-21`) |

### Known Threat Patterns for this stack

| Pattern | STRUCT | Standard Mitigation |
|---------|--------|---------------------|
| Key leaked in RPC URL or error text | Tampering / Information disclosure | Keyless endpoints; settings refusal; redaction at client boundary |
| Endpoint injection via config | Tampering | Validate `rpc.endpoints` and `jupiter.quote_url` are `https://` absolute URLs in Settings |
| Untrusted metadata or response text into LLM prompts | Injection | Treat pump.fun/Jupiter/RPC strings as data; keep prompts server-side constants (`engine/agents/*` `prompt` ClassVar, `agents/base.py:38`) |
| Live path reached through prose or cron | Elevation | CLI verbs for sniper/exit absent; `forbidden_owners` (Open Q 12); live gate exit 3 |
| Signing code added later | Tampering | SEC-003 AST guard in `uv run pytest` |

## Sources

### Primary (HIGH confidence; read this session)
- `.planning/phases/02-restructure/02-CONTEXT.md` (full read, includes R52-R55)
- `.planning/ROADMAP.md` Phase 2 section; `.planning/REQUIREMENTS.md` STRUCT-002/003/005/007, SEC-003 (lines 29-32, 101)
- `tests/test_tools_cli.py` (lines 32-86, 89-141, 178-200); `tools/{jupiter_quote,authority_check,holder_check,priority_fee}.py` (full)
- `src/pumpgrok/cli.py` (full); `src/pumpgrok/doctor.py` (full); `src/pumpgrok/config/settings.py` (lines 26-127, 141-358); `src/pumpgrok/config/overlays/paper.toml`
- `src/pumpgrok/execution/live/{live_gate,live_adapter,__init__}.py`; `src/pumpgrok/ledger/events.py:46-49,75,282-289`; `src/pumpgrok/core/{skill,tool,datasource,approvals}.py`; `src/pumpgrok/replay/{clock,fixtures}.py`
- `tests/conftest.py`, `tests/safety/test_static_guards.py`, `tests/test_network_block.py`, `tests/test_skip_cycle.py`, `tests/fixtures/replay/smoke/{manifest.json,events.jsonl}`
- `vendor/grokbot-pumpfun/src/{monitor,analyzer,risk,ops,models,agents/base,agents/timing,executor,pipeline,reputation}.py` (line refs as cited); `vendor/grokbot-pumpfun/tests/{test_filter,test_risk}.py`; `vendor/grokbot-pumpfun/pyproject.toml`
- `docs/MIGRATION_MAP.md` sections 1.5-1.8, 3, 4.2-4.3, 6, 7 (rows 63-78, 97-116)
- `docs/upgrade-plan-desk-v2.md` R5, R12, R14, R18, R27, R31, R40, R44-R49 (lines 165-215)
- `docs/design/interfaces.md` sections 3.1, 3.2 (lines 1120-1200)
- `.planning/research/STACK.md` lines 15-52, 120-130, 193-203; `docs/FOUNDATION_STACK.md:83,125`
- `skills/*/SKILL.md` (frontmatter scan, lines 1-25 of jupiter-routing); `hermes/cron/jobs.yaml`; `hermes/cron/prompts/*.md` (grep); `scripts/{check.sh,hermes-bootstrap.sh,hermes-install-cron.sh,hermes-verify-isolation.sh,generate-templates.py}` (grep)
- `ownership.yaml` (grep of patterns 52-394); `pyproject.toml`; `.env.example`; `docker-compose.yml` (env block)
- `.venv` site-packages listing (dist-info names)

### Secondary (MEDIUM; repo docs and registry)
- `python3 -m pip index versions tenacity` (this session) -> 9.2.1
- `.planning/research/SUMMARY.md:34,181` (Jupiter unit trap, R44 supersedes STACK V-8)

### Tertiary (LOW / ASSUMED)
- tenacity `sleep=` and custom `wait` signatures (A1); Jupiter v2 `inAmount`/`outAmount` (A2); x.ai `reasoning_effort` field name (A3); `/v1/models` response shape (A4)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for versions (dist-info and registry); MEDIUM for tenacity call signature (A1).
- Architecture / port map: HIGH for line references (verified this session); MEDIUM for classes not read in full (`ops.py` HealthServer, `pipeline.py` internals, `analyzer.py` compute details).
- Pitfalls: HIGH for items that cite lines and grep results; MEDIUM for ruff rule consequences (not executed).
- Open questions: decisions, not facts; recommendations are the research's position.

**Not read in this research (gaps the planner should close):** `docs/ROSTER.md` (skill bot ownership, Open Q 9); `docs/DISCOVERY.md:8-18` in full (verb list was taken from REQUIREMENTS STRUCT-005 and the head of DISCOVERY); `vendor/grokbot-pumpfun/tests/{test_agents,test_analyzer,test_pipeline,test_tune}.py` (characterization bodies beyond the summaries here); `scripts/check.sh` lines 60-128 and 150-end; `ci/gates/check_ownership.py` self-test logic.

**Research date:** 2026-10-21
**Valid until:** 2026-11-20 (stable repo facts); re-verify the tenacity signature and Jupiter v2 fields before Phase 3 (fast-moving external APIs).

## CLI verb surface (reference for the planner)

| Verb (source) | Phase 2 behaviour | Notes |
|---|---|---|
| `run --mode paper [--once] [--replay DIR]` (exists) | `--once --replay`: engine decision (skip) + one JournalNote, exit 0 | Pitfalls 16, 21, 22 |
| `run --record <dataset> --duration <s>` (R40) | not-yet-implemented, exit 5 | Phase 4 recorder (R52) |
| `doctor` (exists) | unchanged format; engine and tools flip to ok | Pitfall 18 |
| `audit`, `verify --fixture <dataset>` (DISCOVERY) | not-yet-implemented; `verify` parses args | Phase 4/5 |
| `report --daily\|--weekly` (DISCOVERY) | not-yet-implemented | Phase 5 (`reporting`) |
| `scout discover\|pipeline` (DISCOVERY) | not-yet-implemented | Phase 3 (tools) |
| `risk audit` (DISCOVERY) | not-yet-implemented | Phase 4 |
| `chief pickup` (DISCOVERY) | not-yet-implemented | Phase 4 |
| `rug watch` (DISCOVERY) | not-yet-implemented | Phase 3/4 |
| `journal rollup` (DISCOVERY) | not-yet-implemented | Phase 4 |
| `ticket next\|create\|list` (DISCOVERY) | not-yet-implemented | Phase 4 `ledger/tickets.py` |
| `state status\|halt [--clear --by --reason]` (DISCOVERY, R22) | not-yet-implemented | Phase 4; clear is human-only (R22/R5) |
| `state autonomy <manual-ticket\|autonomous-paper>` (R40) | not-yet-implemented | Phase 4 |
| `killswitch set\|clear\|status` (DISCOVERY) | not-yet-implemented | Phase 4 |
| `paper buy\|sell --ticket --mint --size-sol --slippage-bps --approval-id` (R40) | parse all flags; not-yet-implemented, exit 5 | `--ticket` matches `^SOL-\d{8}-\d{3}$` (approvals.py); `--size-sol` converts once to lamports (approvals.py docstring); `forbidden_owners` (Open Q 12) |
| `live confirm` (R12) | not-yet-implemented | Phase 4 (LiveGate) |
| `replay trim\|rebuild-ticks` (R12) | not-yet-implemented | Phase 4 |
| `verify`, `pumpgrok tools exec.quote` (MIGRATION row 75/batch 2 mention) | not in DISCOVERY list; do not add | — |

Hermes cron prompts (six): `scout-discover` -> `scout discover --max-leads 5`; `scout-pipeline` -> `scout pipeline --candidates --limit 5`; `risk-audit-open-leads` -> `risk audit --pending`; `chief-pickup` -> `chief pickup`; `rug-watch-paper` -> `rug watch`; `chief-journal-rollup` -> `journal rollup --daily` (MIGRATION_MAP sec 4.3, lines 474-481). Each prompt must treat exit 5 as "not yet implemented" and must not invent results.
