# Phase 2: Restructure - Pattern Map

**Mapped:** 2026-10-21
**Files analyzed:** 89 (34 source, 22 test/fixture, 23 skills, 6 cron prompts, 4 manifests)
**Analogs found:** 87 / 89 (exact 71, role-match 16, none 2: `notify/stdout.py`, `tools/social/__init__.py`)

Binding inputs: `02-CONTEXT.md` (Locked, Discretion, R52-R55) and `02-RESEARCH.md`. Where they disagree with the ROADMAP, the ROADMAP wins (R52). Jupiter is `api.jup.ag/swap/v2/order`, quote-only (R44/R54). No trade subscription (R45/R46). Root `tools/` and `vendor/` stay byte-identical as oracles (R53).

Line references are to the current tree unless marked "(research)". Verified this session with Read/grep.

---

## 1. File Classification

Key: **E** exact (the vendor or root module being ported, or the same-role Phase 1 file); **R** role-match (same role and flow, different content); **N** no analog.

| # | New/Modified (under `src/pumpgrok/` unless noted) | Role | Data Flow | Closest Analog | M |
|---|---|---|---|---|---|
| 1 | `tools/__init__.py` | package marker (doctor `find_spec` target) | - | `core/__init__.py` | R |
| 2 | `tools/onchain/__init__.py` | package marker | - | `core/__init__.py` | R |
| 3 | `tools/onchain/rpc.py` | client (failover + retry) | request-response | `tools/authority_check.py:27-39` (call shape); `vendor/grokbot-pumpfun/src/agents/base.py:131-190` (retry loop) | R |
| 4 | `tools/onchain/authorities.py` | utility | request-response | `tools/authority_check.py:42-75` | E |
| 5 | `tools/onchain/holders.py` | utility | request-response | `tools/holder_check.py:44-86` | E |
| 6 | `tools/onchain/priority_fee.py` | utility | request-response | `tools/priority_fee.py:44-93` | E |
| 7 | `tools/market/__init__.py` | package marker | - | `core/__init__.py` | R |
| 8 | `tools/market/jupiter.py` | client (quote-only) | request-response | `tools/jupiter_quote.py:29-65` | E |
| 9 | `tools/notify/__init__.py` | package marker | - | `core/__init__.py` | R |
| 10 | `tools/notify/base.py` | abstract Notifier | event-driven | `vendor/grokbot-pumpfun/src/alerts.py:40-62` | R |
| 11 | `tools/notify/stdout.py` | sink | event-driven | none (`logging/json.py` formatter is the nearest) | N |
| 12 | `tools/notify/file.py` | sink | file-I/O | `core/atomic_write.py` | R |
| 13 | `tools/social/__init__.py` | client, GET-only | request-response | none (`vendor/.../analyzer.py:72-79` `_get` is the nearest) | N |
| 14 | `core/ratelimit.py` | utility | timing | `vendor/grokbot-pumpfun/src/ops.py:90-128` | E |
| 15 | `core/budget.py` | state utility | state | `vendor/grokbot-pumpfun/src/ops.py:187-214` | E |
| 16 | `core/llm.py` | client + precheck | request-response | `vendor/grokbot-pumpfun/src/ops.py:235-262` (GrokOps), `agents/base.py:35-60` | E |
| 17 | `engine/__init__.py` | package marker (docstring only) | - | `core/__init__.py` | R |
| 18 | `engine/models.py` | domain model | transform | `vendor/grokbot-pumpfun/src/models.py:26-270`; style `core/risk_budget.py:15` | E |
| 19 | `engine/monitor.py` | websocket consumer | streaming | `vendor/grokbot-pumpfun/src/monitor.py:95-111, 212-252` | E |
| 20 | `engine/analyzer.py` | service (injected httpx) | request-response | `vendor/grokbot-pumpfun/src/analyzer.py:38-86` | E |
| 21 | `engine/scoring.py` | pure transform | transform | `vendor/grokbot-pumpfun/src/scoring.py:21-79` | E |
| 22 | `engine/reputation.py` | store | file-I/O, CRUD | `vendor/grokbot-pumpfun/src/reputation.py:48-171`; `core/atomic_write.py` | E |
| 23 | `engine/pipeline.py` | orchestrator | transform | `vendor/grokbot-pumpfun/src/pipeline.py:65`; replay shape `cli.py:109-160` | E |
| 24 | `engine/tune.py` | batch CLI helper | batch | `vendor/grokbot-pumpfun/scripts/tune.py` (234 lines) | E |
| 25 | `engine/exits.py` | pure function | transform | `vendor/grokbot-pumpfun/src/risk.py:219-280` | E |
| 26 | `engine/watcher.py` | poll loop over Protocol | timer | `vendor/grokbot-pumpfun/src/risk.py:283-382`; Protocol style `core/datasource.py:43-61` | E |
| 27 | `engine/agents/__init__.py` | package marker | - | `vendor/grokbot-pumpfun/src/agents/__init__.py` | R |
| 28 | `engine/agents/base.py` | agent base (x.ai POST) | request-response | `vendor/grokbot-pumpfun/src/agents/base.py:35-190` | E |
| 29 | `engine/agents/checker.py` | agent (strong model) | request-response | `vendor/grokbot-pumpfun/src/agents/checker.py` | E |
| 30 | `engine/agents/narrative.py` | agent (fast) | request-response | `vendor/grokbot-pumpfun/src/agents/narrative.py` | E |
| 31 | `engine/agents/timing.py` | agent (fast) | request-response | `vendor/grokbot-pumpfun/src/agents/timing.py:65-93` | E |
| 32 | `engine/agents/auditor.py` | agent (fast) | request-response | `vendor/grokbot-pumpfun/src/agents/auditor.py` | E |
| 33 | `config/settings.py` (modified) | config | - | `config/settings.py:98-127`; `vendor/.../models.py:271-290` | E |
| 34 | `cli.py` (modified) | CLI | request-response | `cli.py:66-80, 93-106, 109-160` | E |
| 35-38 | `tests/characterization/test_{authority_check,holder_check,jupiter_quote,priority_fee}.py` | characterization | test | `tests/test_tools_cli.py:32-141` | E |
| 39-47 | `tests/characterization/test_{agents,analyzer,monitor,reputation,scoring,tune,pipeline,exits,watcher}.py` | characterization | test | `vendor/grokbot-pumpfun/tests/test_{agents,analyzer,filter,reputation,scoring,tune,pipeline,risk}.py` | E |
| 48 | `tests/safety/test_no_signing_outside_live_stub.py` | static guard | test | `tests/safety/test_static_guards.py:78-221` | E |
| 49 | `tests/fixtures/http/*.json` (7 files) | recorded/hand-authored fixtures | test data | `tests/fixtures/replay/smoke/manifest.json` | R |
| 50 | `tests/test_skip_cycle.py` (modified, lines 71, 156-157) | regression | test | itself | E |
| 51-73 | `skills/*/SKILL.md` (23, modified) | skill docs | static | `skills/*/SKILL.md` frontmatter; `core/skill.py:32-40`; `scripts/check.sh:10-55` | E |
| 74-79 | `hermes/cron/prompts/*.md` (6, modified) | cron prompt | static | `hermes/cron/prompts/risk-audit.md:12-13` etc. | E |
| 80-83 | `pyproject.toml`, `uv.lock`, `.env.example`, `ownership.yaml` | manifests | config | `pyproject.toml:9-15`; `.env.example`; `ownership.yaml:264-312, 375-394` | E |

Source: 34 (32 new + 2 modified). Tests/fixtures: 22. Skills: 23. Prompts: 6. Manifests: 4. Total 89.

---

## 2. Pattern Assignments

### 2.1 Root tools to `tools/` (STRUCT-002)

**Analog for rows 4-8: `tools/*.py` (oracle).** Port the function bodies; replace `requests` with an injected `httpx.AsyncClient`, replace the three `rpc_call` copies with `tools/onchain/rpc.py`, and keep the output field names.

Copy from `tools/authority_check.py:42-75` (`check_mint`):
```python
result = rpc_call(rpc_url, "getAccountInfo", [mint, {"encoding": "jsonParsed"}])
if result is None or result.get("value") is None:
    return {"ok": False, "error": "Mint account not found or not a token mint"}
...
return {"ok": True, "mint": mint, "mintAuthority": ..., "hasMintAuthority": mint_authority is not None, "rpc": rpc_url}
```
Changes:
- `"rpc": rpc_url` (`:72`) leaks the endpoint into output. Keep only keyless endpoints (research Pitfall 4/5), and redact at the RPC boundary.
- `return {"ok": False, "error": str(e), ...}` (`:75`) echoes exception text. Redact at the client, not in the caller.

**Analog for row 5 `holders.py`: `tools/holder_check.py:44-86`.** Copy verbatim:
- Method `getTokenLargestAccounts` (`:46`); `top1/top5/top10` math (`:65-67`); `value[:limit]` with default `limit=20`.
- The `note` string at `:79-83` is a disclosure. Keep it byte-identical.
- Owner: R35 RUG, not WHALE. See Gap G5.

**Analog for row 6 `priority_fee.py`: `tools/priority_fee.py:44-93`.**
- Method `getRecentPrioritizationFees` with `[[]]` (`:49`); index `min(max(int(n * percentile / 100), 0), n - 1)` (`:65`).
- `recommended_lamports_per_cu` (`:85`) is a mislabelled alias (MIGRATION row 77). Decide keep or drop; do not carry it silently.

**Analog for row 8 `market/jupiter.py`: `tools/jupiter_quote.py:29-65`.**
```python
resp = requests.get(JUPITER_QUOTE_URL, params=params, timeout=12)   # :39
resp.raise_for_status()
data = resp.json()
...
"priceImpactPct": data.get("priceImpactPct"),                       # :56
```
Port rules (R44/R38/R54):
- URL: `https://api.jup.ag/swap/v2/order`. No `taker`. Never `/execute`, `/build`, `/submit`.
- Key: `JUPITER_API_KEY` from env, wrapped in `SecretStr`, sent as `x-api-key`.
- Unit trap: v2 `priceImpact` is percentage points. Map `Ratio = priceImpact / 100` (research Pitfall 2). Do not read `priceImpactPct`.
- Quote is informational only. It is never the fill price (R38).
- Field names `inAmount`/`outAmount` are ASSUMED for v2 (research A2). Record a fixture before relying on them.

**Analog for row 3 `rpc.py`:** no tenacity analog exists. Closest shape: the `_call` loop at `vendor/grokbot-pumpfun/src/agents/base.py:131-180`. Do not copy its `random.random()` jitter (`:189`, banned). Use `tenacity.AsyncRetrying(sleep=clock.sleep, wait=<seeded callable>)` (research Code Examples; signature is ASSUMED A1, confirm before writing).

### 2.2 Vendor engine to `engine/` (STRUCT-003)

**Analog for rows 18-19 monitor and models: `vendor/grokbot-pumpfun/src/monitor.py:95-111` (filter) and `models.py:26-53` (Token).**
```python
def passes_filter(token: Token, cfg: FilterConfig) -> tuple[bool, str]:
    if cfg.require_metadata and not token.has_metadata:
        return False, "no_metadata"
    if token.curve_progress >= cfg.max_curve_progress:
        return False, "curve_too_full"
    if token.age_seconds < cfg.min_age_seconds:
        return False, "too_young"
    if token.unique_buyers < cfg.min_unique_buyers:      # :109
        return False, "few_buyers"                        # :110
    return True, "ok"
```
Port rules:
- Keep the reason codes byte-identical except `few_buyers` on missing evidence becomes `data_unavailable` (fail closed; research Pitfall 8).
- `Token.age_seconds` reads `time.time()` at `models.py:53`. Change it to take `now: float` (research Pitfall 10).
- Delete `LaunchMonitor._buyers` (`monitor.py:126, 142, 152-153, 198`) and `_subscribe_trades` (`:236, 241, 254-258`).
- The stream loop (`:212-252`) uses `websockets.connect(...)` (`:218`, legacy path), `asyncio.wait_for` (`:225`), `time.time` (`:222, 242, 243`), `asyncio.sleep` (`:251`). Port as:
```python
from websockets.asyncio.client import connect   # the only allowed path (test_network_block.py:50-75)
async with connect(url, proxy=None, max_queue=max_queue) as ws:
    await ws.send(json.dumps({"method": "subscribeNewToken"}))   # only subscription (R45)
...
async with clock.timeout(sweeper_delay):
    raw = await ws.recv()
except TimeoutError:
    raw = None
```

**Analog for row 20 analyzer: `vendor/grokbot-pumpfun/src/analyzer.py:38-80`.** Keep the injection shape:
```python
class Analyzer:
    def __init__(self, config: Config, client: httpx.AsyncClient | None = None) -> None:   # :41
        self._client = client
        self._owns_client = client is None
...
async def _get(self, path: str, **params: Any) -> Any:                                     # :72
    try:
        resp = await self.client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        log.warning(...)
        return None
```
Port rules:
- Keep `_get` returning `None` on failure (R47). Add a per-source health flag beside it. No entry decision may rest only on pump.fun REST.
- Remove the `Bearer` header (`:51`) unless a settings field carries it (Gap G6).
- Log strings are Russian (`:78`). Translate.
- `_veto_reason` (`:285-293`) returns Russian free text. Replace with ASCII codes (Gap G3).

**Analog for row 25 exits: `vendor/grokbot-pumpfun/src/risk.py:238-280`.** Keep the rule order (research Code Examples; `risk.py:255,258,264,272`):
```python
if risk.stop_loss_pct and -change >= risk.stop_loss_pct:      -> "stop_loss"
if risk.take_profit_pct and change >= risk.take_profit_pct:   -> "take_profit"
if risk.trailing_stop_pct and peak > position.entry_price:    -> "trailing_stop"
if risk.max_hold_seconds and position.opened_at:              -> "max_hold"   # held = (now or time.time()) - opened_at  (:273)
```
Port rules:
- Signature becomes `exit_signal(position, price, cfg, now: float)`. `now` is required. Remove `now or time.time()` (Pitfall 13).
- `risk: RiskConfig` becomes an `exits` section (Pitfall 15). Do not extend `core/risk_budget.py:15` (R20 schema).
- Day-rollover (`risk.py:106-117`) is NOT ported (R5).

**Analog for row 26 watcher: `vendor/grokbot-pumpfun/src/risk.py:283-382`.** Constants to keep: `PEAK_PERSIST_STEP = 1.01` (`:293`), `BLIND_AFTER = 3` (`:297`). Replace the `RiskManager` dependency (`:299-307`) with a `PositionBook` Protocol. The Protocol style is `core/datasource.py:43-61` (`@runtime_checkable`, `Protocol`). Replace `asyncio.sleep` (`:371`) with `clock.sleep`.

**Analog for row 22 reputation: `vendor/grokbot-pumpfun/src/reputation.py:48-171`.** Replace `time.time()` at `:72, 94, 147` with an injected clock. Read the path from settings (`ops.reputation_path`, `models.py:382`). Persist via `core/atomic_write.py`. Keep the JSON shape or migrate it (research, Runtime State).

**Analog for row 21 scoring: `vendor/grokbot-pumpfun/src/scoring.py:21-79`.** Logic is 1:1 (`normalized_weights :21`, `compute_scores :35`, `passes_threshold :58`, `weakest_component :66`). Translate the docstring at `:6` (it says no LLM call; keep that claim true).

**Analog for row 28 agents base: `vendor/grokbot-pumpfun/src/agents/base.py:35-190`.** Keep the structure: `_call` loop (`:131`, `:140`) with `ops.precheck` on each attempt (`:144`), `_backoff` (`:182-190`), `_failed`/`record_success`. Changes:
- `asyncio.sleep` at `:149` becomes `clock.sleep`.
- `random.random()` at `:189` becomes an injected `random.Random` from `make_rng`.
- `self.grok.base_url` is used as the POST target (`:153`). Config value becomes `https://api.x.ai/v1` and the code appends `/chat/completions` (R48). Vendor default is the full path (`models.py:279`).
- Model selection: `checker` uses `grok-4.3` at effort low; `narrative` and `timing` use `grok-4.20-0309-non-reasoning`; `auditor` keeps fast (`agents/base.py:57-59`).

**Analog for row 23 pipeline: `vendor/grokbot-pumpfun/src/pipeline.py:65` (class `Pipeline`).** Keep engine stages. Drop the live flag and its refusal (`:490-540`; Phase 4 `LiveGateError`). `time.time` at `:99, 100, 198, 394, 403` becomes the clock.

**Analog for row 24 tune: `vendor/grokbot-pumpfun/scripts/tune.py`.** 234 lines, 53 Cyrillic lines, 21 `print(` calls. Use `sys.stdout.write` (ruff `T20`, research Pitfall 28).

**Analog for rows 14-16 `core/`: `vendor/grokbot-pumpfun/src/ops.py`.**
```python
class RateLimiter:                                            # :90
    def __init__(self, per_minute, burst=None, clock: Callable[[], float] = time.monotonic): ...  # :93-99
    ...
                await asyncio.sleep(delay)                    # :128
class CallBudget:                                             # :187
    def __init__(self, max_per_day, clock: Callable[[], float] = time.time, spent=0): ...          # :190-196
class GrokOps:                                                # :235
    def precheck(self, agent: str) -> str | None:             # :248
```
Port rules:
- Default-argument clocks (`time.monotonic`, `time.time`) are banned references even as defaults (research Anti-patterns). Require an injected `Clock`.
- `CircuitBreaker` (`ops.py:131`) is Phase 4 (`risk/breakers.py`, R52). Do not port it here.
- `HealthServer` (`:299`) and `Heartbeat` (`:372`) are not Phase 2.

**Analog for row 29-32 agents checker, narrative, timing, auditor.** Same pattern as row 28. Prompt text is Russian (checker 27 Cyrillic lines, narrative 19, timing 26, auditor 24, per research). Translate. Prompt edits change `canonical_request_hash` (CONTEXT Discretion). The smoke LLM record is authored last.

**Engine scope gates.**
- Baseline: `grep` over `src/pumpgrok/engine/` returns nothing today. After the port, `! LC_ALL=C.UTF-8 grep -rlP '\p{Cyrillic}' src/pumpgrok/engine/` must print nothing (research Pitfall 29).
- Vendor Cyrillic line counts (`grep -cP`): `monitor` 32, `analyzer` 38, `scoring` 13, `reputation` 27, `pipeline` 104, `models` 114, `risk` 68, `ops` 51, `scripts/tune.py` 53.

### 2.3 Configuration (STRUCT-003, STRUCT-005)

**Analog for row 33 `config/settings.py`: Phase 1 `Settings` (`settings.py:112-127`) plus the vendor secret model (`vendor/.../models.py:271-287`).**
```python
class ReplaySettings(BaseModel):                       # settings.py:98
    model_config = ConfigDict(frozen=True, extra="forbid")
    seed: int = 20260101

class Settings(BaseSettings):                          # :112
    model_config = SettingsConfigDict(env_prefix="PUMPGROK_", env_nested_delimiter="__", extra="forbid")
    risk: RiskBudget = Field(default_factory=RiskBudget)   # :125
    replay: ReplaySettings = Field(default_factory=ReplaySettings)
```
Vendor secret pattern:
```python
class GrokConfig(SecretModel):                         # models.py:277
    api_key: SecretStr = SecretStr("")                 # :278
    base_url: str = "https://api.x.ai/v1/chat/completions"   # :279
    fast_model: str = "grok-4-fast"                    # :280
    checker_model: str = "grok-4"                      # :281
```
Port rules:
- Add sections `data` (`ws_url`, `ws_max_queue=16`), `rpc` (`endpoints[]`), `grok` (`base_url=https://api.x.ai/v1`, `strong_model=grok-4.3`, `strong_effort=low`, `fast_model=grok-4.20-0309-non-reasoning`, `api_key: SecretStr`), `jupiter` (`quote_url`), `filter`, `scoring`, `exits`, `ops` (`reputation_path`). Do not extend `risk` (Pitfall 15).
- `extra="forbid"` (`:118`) rejects unknown TOML keys. Every new section must exist in the model before any overlay sets it (Pitfall 14).
- Startup guards: `FORBIDDEN_SUBSTRINGS` (`settings.py:51-58`: `PRIVATE_KEY`, `SECRET_KEY`, `SEED`, `MNEMONIC`, `PHANTOM`, `WALLET_SECRET`, `KEYPAIR`) apply to env NAMES. `KEY_BEARING_VALUE_RE` (`:71`) applies to VALUES (`api-key=`, `token=`, `key=`). `PUMPGROK_GROK__API_KEY` passes both checks. `JUPITER_API_KEY` is not `PUMPGROK_`-prefixed and is read in the composition root (Open Q6).
- `refuse_cli_secrets` (`:341-358`) runs before parse (`cli.py:162-163`). Keyed URLs in `rpc.endpoints` fail startup.

**Analog for row 34 `cli.py`: Phase 1 CLI.**
```python
EXIT_OK = 0; EXIT_CONFIG = 1; EXIT_LEDGER = 2; EXIT_LIVE = 3; EXIT_FIXTURE = 4; EXIT_NOT_IMPLEMENTED = 5   # cli.py:43-48

def build_parser() -> argparse.ArgumentParser:                                    # :66
    parser = _Parser(prog="pumpgrok", ...)
    verbs = parser.add_subparsers(dest="verb", required=True, metavar="VERB")
    run = verbs.add_parser("run", parents=[mode_option], help="run the desk")
    run.add_argument("--once", action="store_true", ...)
    verbs.add_parser("doctor", parents=[mode_option], help="report subsystem health")
```
```python
def _run(args, settings) -> int:                                                  # :93
    ...
    if not (args.once and args.replay):
        _say(sys.stderr, "not implemented: this release runs only `run --mode paper --once --replay <dir>`")
        return EXIT_NOT_IMPLEMENTED                                               # :105
```
Port rules:
- Add the DISCOVERY verbs as subparsers. Absent verbs print one JSON object on stdout (`{"ok": false, "status": "not-yet-implemented", "verb": ...}`) and exit 5. Today `_run` writes text to stderr only (`:102-105`). Research Open Q1 and CONTEXT Discretion say exit 2; `cli.py:5-6` reserves 2 for ledger. Use 5 (Pitfall 17).
- `paper buy|sell` must parse `--ticket --mint --size-sol --slippage-bps --approval-id`. `--ticket` pattern: `^SOL-\d{8}-\d{3}$` (`core/approvals.py:39`). `--size-sol` converts to lamports once (`approvals.py:22`).
- Skip cycle: `_skip_cycle` (`:109-160`) keeps the order: manifest verification, then recreate ledger, then `FixtureClock`, then one `JournalNote`. Replay must not call `LaunchMonitor.stream()` (Pitfall 22).
- `doctor` (`src/pumpgrok/doctor.py:16-28` `SUBSYSTEMS`) needs no change. `engine` and `tools` flip to `ok` once the packages exist.

**Analog for JournalNote (engine decision row): `ledger/events.py:282-289` and `NoteKind` at `:75-86`.**
```python
class JournalNote(_ClosedModel):          # :282, extra="forbid"
    source: EventSource
    seat: str = "desk"
    note_kind: NoteKind = NoteKind.note
    text: str
    refs: list[str] = []
```
`NoteKind.verdict` exists (`:80`). Put `engine decision=<skip|buy> reason=<ASCII>` in `text`. Do not add columns (Pitfall 21).

### 2.4 Skills, cron prompts, manifests (STRUCT-007, STRUCT-005)

**Frontmatter analog: `core/skill.py:32-40` (`SkillManifest`) and the parser in `scripts/check.sh:10-55`.**
```python
class SkillManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{1,60}$")
    description: str = Field(min_length=1, max_length=1024)
    bots: list[str] = Field(min_length=1)          # :39
    gates: list[str] = Field(default_factory=list)
```
```python
# scripts/check.sh: name must equal directory; description <= 1024; body <= 350 lines
if name != os.path.basename(d): err(...)
```
Current state: 23 `skills/*/SKILL.md`, zero with `^bots:` or `^gates:` (verified). Frontmatter today has only `name` and `description`.

Analog for the Jupiter skill: `skills/jupiter-routing/SKILL.md:18` contains `--max-micro` (`priority_fee.py --multiplier 1.25 --max-micro 50000`). The root `priority_fee.py` has no such flag. Remove it (Pitfall 24). Also remove `lite-api` text (Pitfall 23). Current hits: `ARCHITECTURE.md:26`, `AGENTS.md:90,123,209,256,264,342`, `tools/jupiter_quote.py:26` (oracle, keep), `tests/test_tools_cli.py:37,70` (oracle, keep).

Skills mentioning `micro-live` (R42, to remove): `skills/desk-monitoring/SKILL.md`, `skills/desk-operating-model/SKILL.md`, `skills/desk-strategy-lab/SKILL.md`, `skills/pumpgrok-setup/SKILL.md`, plus `scripts/hermes-verify-isolation.sh`, `SETUP.md`, `ARCHITECTURE.md`, `README.md`.

**Cron prompt analog: `hermes/cron/prompts/risk-audit.md:12-13`.**
```
1. python "$PUMPGROK_ROOT/tools/desk_state.py" status
2. python "$PUMPGROK_ROOT/tools/desk_state.py" pending-leads
```
Six prompts reference `$PUMPGROK_ROOT/tools/*.py` (`chief-journal`, `chief-pickup:13-17`, `risk-audit:12-13`, `rug-watch:10-11`, `scout-discover:12-16`, `scout-pipeline`). Rewrite to `pumpgrok ...` (MIGRATION sec 4.3). Each must handle exit 5 as not-yet-implemented and not invent results (Pitfall 25).

Retire `PUMPGROK_ROOT`, `PUMPGROK_DESK`, `PUMPGROK_ROLE` exports: `scripts/hermes-install-cron.sh:43-50`, `scripts/hermes-bootstrap.sh:129-131`. Settings refuses them (`find_unknown_env`, `settings.py:227`).

**Manifests.**
- `pyproject.toml:9-15`: add `"tenacity>=9.2.1,<10"` beside `httpx>=0.28.1,<0.29`. Lock `uv.lock` in the same change (Pitfall 36).
- `pyproject.toml` dev group: the comment `# removed with tools/ in Phase 2` is wrong. R53 moves removal to Phase 5 (Pitfall 34).
- `.env.example`: header says every key is `PUMPGROK_`-prefixed. Add `PUMPGROK_GROK__API_KEY=` placeholder and document `JUPITER_API_KEY` separately (Open Q6).
- `ownership.yaml`: see section 4, Gap G5.

---

## 3. Characterization-Test Pattern

### 3.1 Root unittest oracle to pytest port (STRUCT-002, R55)

The six cases required by ROADMAP SC1 are in `tests/test_tools_cli.py`:

| Root case (oracle) | Lines | Port file | Port rule |
|---|---|---|---|
| `JupiterQuoteContract.test_quote_url_is_current_lite_swap_api` | `:33-39` | `test_jupiter_quote.py` | Assert `https://api.jup.ag/swap/v2/order`. Document the deviation in the module docstring (R44). |
| `JupiterQuoteContract.test_get_quote_calls_configured_url` | `:41-71` | `test_jupiter_quote.py` | Replace `mod.requests.get` patch (`:67`) with `httpx.AsyncClient(transport=httpx.MockTransport(handler))`; assert `request.url`. Fixture returns `priceImpact`, not `priceImpactPct` (Pitfall 2). |
| `JupiterQuoteContract.test_main_exits_nonzero_when_quote_fails` | `:73-87` | `test_jupiter_quote.py` | Keep the non-zero exit assertion on error. |
| `FailClosedExitCodes.test_authority_main_exits_nonzero_on_error` | `:107-117` | `test_authority_check.py` | Keep `returncode != 0` on `{"ok": False}`. Patch the injected client, not `check_mint`. |
| `FailClosedExitCodes.test_holder_main_exits_nonzero_on_error` | `:119-129` | `test_holder_check.py` | As above for `holder_snapshot`. |
| `FailClosedExitCodes.test_priority_fee_main_exits_nonzero_on_error` | `:131-141` | `test_priority_fee.py` | As above for `estimate_priority_fee`. |

Root pattern to copy (`tests/test_tools_cli.py:22-30`):
```python
def load_tool(name: str):
    spec = importlib.util.spec_from_file_location(f"pumpgrok_{name}", path)
```
Do not copy it. The port imports `pumpgrok.tools.*` normally.

Keep the root oracle files untouched (R53). Their assertions (`lite-api`, `ticket_helper.py next`) stay true for the oracle.

### 3.2 Pytest style to copy (Phase 1 and vendor)

- Offline by default: `tests/conftest.py` (35 lines) patches `httpx.AsyncHTTPTransport.handle_async_request` and `websockets.asyncio.client.connect` to raise `NetworkBlocked`. Use `httpx.MockTransport` in tests (`tests/test_network_block.py:33-37`).
- Vendor analyzer helper (`vendor/grokbot-pumpfun/tests/test_analyzer.py:36-60`):
```python
def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))

async def test_fetch_hits_three_endpoints(config):
    seen: list[str] = []
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        ...
```
- Vendor filter fixtures (`vendor/grokbot-pumpfun/tests/test_filter.py:14-24`): a `cfg()` fixture returning `FilterConfig(...)` and `make_token(**overrides)`. Copy both for `test_monitor.py`.
- Vendor websocket double (`test_filter.py:239-265`, `FakeWebSocket`): scripted `recv()`, `send()` recorded. Replace `asyncio.sleep(3600)` (`:258`) with `FixtureClock` (`replay/clock.py:121-130`). Replace `monkeypatch.setattr(asyncio, "sleep", ...)` (`:316-318`) with clock injection; the static guard bans it.
- Exactly one `pytest-asyncio` mode: `asyncio_mode = "auto"` (`pyproject.toml`, `[tool.pytest.ini_options]`).

### 3.3 Vendor test to characterization file mapping

Counts from CONTEXT (vendor counts 21/16/21/18/13/15/37). Port every case unless it depends on trade events (R45/R46).

| Characterization file | Vendor source | Notes |
|---|---|---|
| `test_monitor.py` | `test_filter.py` (21) | Seven cases depend on trades: `:69-73`, `:137-156`, `:158-168`, `:199-207`, `:285-304`, `:307-327`, `:329-343` (research Pitfall 7). Rewrite them as `data_unavailable` / no-trade-subscription cases. Keep the docstring listing what was adapted. |
| `test_analyzer.py` | `test_analyzer.py` (16) | `_get` returns `None` on failure (R47). |
| `test_scoring.py` | `test_scoring.py` (13) | 1:1. |
| `test_reputation.py` | `test_reputation.py` | Clock-injected. |
| `test_agents.py` | `test_agents.py` (18) | Seeded RNG for jitter; clock for sleep. |
| `test_tune.py` | `test_tune.py` (15) | Output via `sys.stdout.write`. |
| `test_pipeline.py` | `test_pipeline.py` (37) | Engine stages only; live cases removed. |
| `test_exits.py` | `test_risk.py` subset | Exit rule cases only (`exit_signal`, `pnl_pct`, `stop_loss_triggered`). |
| `test_watcher.py` | `test_risk.py` subset | Uses the `PositionBook` test double, not `RiskManager`. |

Mapping note: `test_risk.py` has 36 cases; exit and watcher are the subset (CONTEXT).

### 3.4 Flat-name constraint

ROADMAP SC1/SC2 require flat names: `tests/characterization/test_<module>.py`. Pytest default `prepend` import mode fails on basename collisions. Current basenames under `tests/` and `ci/tests/` contain no collision with the 13 names (verified by listing). Keep it that way (Pitfall 32).

---

## 4. Signing-Guard Test Pattern (SEC-003)

### 4.1 Analog: `tests/safety/test_static_guards.py`

Structure to copy (verified):
- `SRC = Path(__file__).resolve().parents[2] / "src" / "pumpgrok"` (`:18`).
- Allowlist constants: `CLOCK_ALLOWLIST = frozenset({"replay/clock.py"})` (`:21`), `RNG_ALLOWLIST` (`:23`).
- `_scan_file(path, rel)` (`:78`): parses the file with `ast`, resolves aliases, flags nodes. Returns `[f"{rel}:{line}: {reason}"]`.
- `find_violations(package_root)` (`:130`): `rglob("*.py")`, sorted.
- `test_src_pumpgrok_has_no_forbidden_primitives` (`:138`): `assert find_violations(SRC) == []`.
- `PROBES: list[tuple[str, str, bool]]` (`:147-205`) and `test_probe_is_classified` (`:206`) parametrize over `(relpath, source, must_flag)`, writing each probe into `tmp_path / "pumpgrok"`.
- Scratch-copy test (`test_smuggled_wall_clock_in_scratch_copy_is_caught`) proves the walker fires on a copied tree.

Analog for the allowlist-by-path check: `tests/test_network_block.py:50-75` (`test_no_src_module_imports_legacy_websockets_path`) walks `SRC.rglob("*.py")` and checks `ImportFrom`, `Import`, and `Attribute`. The new guard follows the same shape but checks different names.

### 4.2 Differences for the signing guard

- Exact-equality match (`sign`, `send_transaction`, `sendTransaction`, `Keypair`). Do not use substrings or regex (research Don't Hand-Roll: `signature` at `analyzer.py:136` must not match).
- Node types to check: `ast.Name.id`, `ast.Attribute.attr`, `ast.alias.name` and `.asname`, `FunctionDef`/`AsyncFunctionDef`/`ClassDef.name`, `ast.arg.arg`, `ast.keyword.arg`, `ast.Constant` (str) (research Pattern 5; Pitfall 27).
- Exempt path: POSIX relpath starting with `execution/live/` (the live stub, `src/pumpgrok/execution/live/live_adapter.py`, docstring at `:1-8`).
- Baseline verified this session: `grep -rwE "sign|send_transaction|sendTransaction|Keypair" src/pumpgrok` returns nothing. Vendor hits are comments only (`vendor/grokbot-pumpfun/src/executor.py:150, 158`), and vendor is not scanned.

Positive probes (must flag, `True`):
- `def sign(x): ...`
- `sig = Keypair()`
- `x.send_transaction(t)`
- `getattr(c, "sendTransaction")` (string constant)
- `from solders.keypair import Keypair as K` (alias `.name` matches)
- `f(sign=1)` (keyword arg)

Negative probes (must not flag, `False`):
- `signature=raw.get("signature")` (matches `analyzer.py:136`)
- `"never a real signature"` in a docstring
- `signature_hash = 1`
- the same forbidden names under `execution/live/`

Also assert `execution/live/live_adapter.py` imports no `solders`/`solana` and names no `Transaction`/`VersionedTransaction`/`Message` (research Validation Architecture).

---

## 5. Shared Patterns

### 5.1 Injected clock and seeded RNG (applies to every ported file)
**Source:** `src/pumpgrok/replay/clock.py:22-33` (`Clock` protocol: `now`, `monotonic`, `utc_iso`, `sleep`, `timeout`); `WallClock` `:50`; `FixtureClock` `:79` (`sleep` `:121`, `timeout` `:133`); `src/pumpgrok/replay/rng.py:13-15` (`make_rng`).
**Apply to:** every file in rows 3-32 and 14-16.
```python
def __init__(self, ..., clock: Clock, rng: random.Random) -> None: ...
```
The static guard (`test_static_guards.py:21-40`) rejects `import time`, `asyncio.sleep`, `asyncio.wait_for`, `time.time`, `time.monotonic`, `datetime.now`, `uuid`, `secrets`, and any `random.*` except `random.Random`, plus unseeded `Random()`.

### 5.2 httpx injection and MockTransport
**Source:** `vendor/grokbot-pumpfun/src/analyzer.py:41-51` (`client` argument, `_owns_client`); `tests/test_network_block.py:33-37`.
**Apply to:** rows 3-8, 13, 16, 20, 28-32.

### 5.3 Secrets
**Source:** vendor `SecretModel`/`SecretStr` (`models.py:271-287`); Phase 1 `mask` (`logging/redaction.py:56`); `redact_text` (`logging/redaction.py:63`); `RedactionFilter` (`:83`).
**Apply to:** `tools/onchain/rpc.py` (endpoint and key never in URL, log or error), `tools/market/jupiter.py` (`x-api-key`), `core/llm.py` (x.ai key).
Root `authority_check.py:72` and `holder_check.py` (return dict) echo `rpc_url` in output; `rpc.py` must not.

### 5.4 Retry (new)
**Source:** `vendor/grokbot-pumpfun/src/agents/base.py:131-180` (loop) and `:182-190` (backoff). Replace with tenacity.
**Apply to:** `tools/onchain/rpc.py` (STRUCT-002), `engine/agents/base.py`.
`core/tool.py:16-22` `RetryPolicy` is not wired: "ToolSpec refuses attempts > 1 until it is wired". RPC retries therefore live inside `rpc.py`, not in `ToolSpec`.

### 5.5 Reason codes (ASCII)
**Source:** `vendor/grokbot-pumpfun/src/monitor.py:108-110` and `:172`, `:193` (`stale_no_traction`), `:208` (`buffer_overflow`); `analyzer.py:285-293` is the exception (Gap G3).
**Apply to:** `engine/monitor.py`, `engine/analyzer.py`, `engine/pipeline.py`, `engine/exits.py`.
Closed set: `no_metadata`, `curve_too_full`, `too_young`, `few_buyers` (to become `data_unavailable`), `stale_no_traction`, `buffer_overflow`, `stop_loss`, `take_profit`, `trailing_stop`, `max_hold`.

### 5.6 Exit codes and absent verbs
**Source:** `cli.py:43-48`, `_run :93-106`, `_dispatch :162-171`, `main :173-190`.
**Apply to:** `cli.py`, `tests/test_skip_cycle.py:89-95`.

### 5.7 Pydantic style
**Source:** `core/skill.py:32-40`, `core/risk_budget.py:15-20` (frozen, `extra="forbid"`, `Field(ge=..)`, `field_validator`). Vendor models use `extra="allow"` for `Token` (`models.py:29`); the port uses `extra="forbid"`.

---

## 6. No Analog Found

| File | Role | Data Flow | Reason | Use instead |
|---|---|---|---|---|
| `tools/notify/stdout.py` | sink | event-driven | No stdout notifier exists; vendor `alerts.py` is webhook-only (Phase 3) | Research D6; `logging/json.py` for output style |
| `tools/social/__init__.py` | client, GET-only | request-response | No social source ported in Phase 2 (R31) | Research R31; `analyzer.py:72-79` for the GET shape |
| `engine/watcher.py` PositionBook Protocol | Protocol | timer | Vendor depends on `RiskManager` (Pitfall 12) | `core/datasource.py:43-61` for Protocol style |
| `tools/market/jupiter.py` v2 response mapping | mapper | transform | No v2 fixture recorded yet; `inAmount`/`outAmount` are ASSUMED (A2) | Record `tests/fixtures/http/jupiter_order.json` hand-authored, labelled |
| `tenacity` `sleep=`/`wait=` signatures | library | - | ASSUMED (A1) | Verify against installed tenacity 9.2.1 before writing `rpc.py` |

---

## 7. Gaps and Decisions the Planner Must Resolve

1. **G1 - Missing trade evidence has no representation.** `Token.unique_buyers` is `int = 0` (`models.py` `Token`, `:26`). `passes_filter` cannot tell "zero buyers" from "no trade data". Add a tri-state (for example `unique_buyers: int | None = None`, with `None` meaning no evidence) and return `data_unavailable` on `None`. [INFERENCE: the tri-state is the minimum representation that makes fail-closed testable.]
2. **G2 - `data_unavailable` in `_promote`.** `monitor.py:172` keeps `too_young`/`few_buyers` buffered. Without a trade stream (R45), a buffered `data_unavailable` token can never gain evidence. [INFERENCE: treat `data_unavailable` as terminal in `_promote`; state it in the characterization docstring.]
3. **G3 - Russian free-text veto reasons.** `analyzer.py:285-293` returns Russian sentences ("создатель держит ...", "топ-5 кошельков держат ..."). Replace with ASCII codes (for example `creator_share_veto`, `top5_share_veto`). Otherwise the Cyrillic gate fails and reason codes are not ASCII.
4. **G4 - Naming collisions.** `engine/models.py` `Position` (vendor `models.py:243`) collides in meaning with `core/adapter.py:112` `Position`. Choose a distinct engine name.
5. **G5 - Ownership.** `ownership.yaml` assigns `src/pumpgrok/tools/onchain/holders.py` to `bot-03-whale` (rule at `:292-293`). CONTEXT says RUG (R35). Last match wins, so change that rule. `engine/reputation.py` falls to `bot-08-signal` (`:316` default, `engine/**` rule). Flat `tests/characterization/test_<module>.py` falls to `tests/characterization/**` = `bot-02-risk` (rule `:379-380`). The existing subtree rules (`tests/characterization/engine/**` and siblings, `:381-393`) do not match flat names. Add flat-file rules after the directory rules (last match wins).
6. **G6 - Keys.** `analyzer.py:51` sends a pump.fun `Bearer` header from `data.key`. No Settings field exists. Decide: drop it, or add a `SecretStr` field. `JUPITER_API_KEY` conflicts with the `.env.example` header ("every key is `PUMPGROK_`-prefixed"). Resolve in the `.env.example` edit.
7. **G7 - Stale `DataSource` example.** `core/datasource.py:50` comment lists `'jupiter_lite'`. Rate key is `jupiter` (CONTEXT). Update the comment.
8. **G8 - Doc conflicts with R44.** `AGENTS.md:264` says "Keep lite-api v1 only behind a config flag"; R44 says removed, not kept behind a flag. `AGENTS.md:90, 123, 209, 256, 262, 342` also name lite-api. Update in close-out.
9. **G9 - Doctor test.** `tests/test_skip_cycle.py:156` loop `("engine", "tools", "gateway", "supervisor", "reports")` must drop `engine` and `tools` once they resolve. Line 157 asserts `warn  {absent} ...`. Update the loop tuple.
10. **G10 - Replay JournalNote assertion.** `tests/test_skip_cycle.py:71` asserts `note_kind == "note"`. If the engine row uses `verdict`, update the assertion.
11. **G11 - Forbidden owners.** `hermes/cron/jobs.yaml:79` `forbidden_owners: [sniper, exit]` needs caller identity. `logging/json.py:36` `bind_seat` and `current_seat` (`:53`) are the nearest mechanism; the composition root must bind the seat (Open Q12).
12. **G12 - Engine decision under R45.** Without trades, every token reaches `data_unavailable`. Replay smoke ticks carry no evidence (research Pitfall 16). Expected smoke result is `skip`, and that is consistent with the checkpoint ("one skip or buy").

---

## 8. Metadata

**Analog search scope:** `src/pumpgrok/**`, `tests/**`, `tools/*.py`, `vendor/grokbot-pumpfun/{src,tests,scripts}`, `skills/*/SKILL.md`, `hermes/cron/prompts/*.md`, `ownership.yaml`, `pyproject.toml`, `.env.example`, `scripts/check.sh`.
**Files read or grepped:** about 45 (targeted ranges only; no file re-read in full).
**Pattern extraction date:** 2026-10-21
