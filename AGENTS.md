# PumpGrok desk: instructions for coding agents

PumpGrok is a ten-seat, paper-first Solana trading desk (`src/pumpgrok/`), packaged in the
programming-desk shape: path ownership, verification receipts, gates G-1..G-7, contracts and prompt
assembly. Engagement levels are `research | paper` only (R16). No code path can move real funds.

## Where the rules live

The linked file is the rule. Do not treat a summary as a substitute.

| Topic | File |
|---|---|
| Gates G-1..G-7, how to run them | [docs/quality-gates.md](docs/quality-gates.md) |
| Ten seats, levels, flow of a trade | [docs/desk-operating-model.md](docs/desk-operating-model.md) |
| Features that cross seats | [docs/cross-bot-protocol.md](docs/cross-bot-protocol.md) |
| Key custody, secrets, container posture | [SECURITY.md](SECURITY.md) |
| Security constitution (verbatim in every seat file) | [rules/pumpgrok-team.mdc](rules/pumpgrok-team.mdc) |
| Path to owner | [ownership.yaml](ownership.yaml) |
| Vendored engine pin and desk overrides | [docs/VENDOR_PIN.md](docs/VENDOR_PIN.md) |
| Event and tool contracts | [contracts/README.md](contracts/README.md) |
| Release history | [CHANGELOG.md](CHANGELOG.md) |

## The ten seats

| Seat id | Channel | Writes exchange |
|---|---|---|
| bot-00-chief | Trading Floor | no |
| bot-01-scout | Trading Floor | no |
| bot-02-risk | Trading Floor | no |
| bot-03-whale | Trading Floor | no |
| bot-04-sniper | Trading Floor | paper-write |
| bot-05-rug | Trading Floor | no |
| bot-06-exit | DM / off-channel | paper-write |
| bot-07-shill | DM / off-channel | no |
| bot-08-signal | DM / off-channel | no |
| bot-09-journal | DM / off-channel | no |

## Before the first edit

Every path resolves to exactly one seat in [ownership.yaml](ownership.yaml). The last matching
pattern wins, and an unowned path fails G-1. Resolve the paths you will edit before changing them.
Cross-seat work follows [docs/cross-bot-protocol.md](docs/cross-bot-protocol.md).

Work on a `bot-0N-<seat>/<unit>` branch. The gates workflow derives the acting seat from that
prefix. Open a draft pull request. Do not merge, force-push or delete branches without approval.

## Receipts

No completion claim without a receipt under `.receipts/<seat>/<task-id>.json`. Record the commands
you ran and their exit codes, and list what you did not verify. A seat never approves its own
work. Receipts are gitignored; track one with `git add -f`.

## Secrets

Do not print, commit or echo keys, tokens, seed phrases, or `.env` contents. Reference environment
variables by name only. G-3 is `python3 ci/gates/check_secrets.py`.

## Run the checks

```bash
uv sync --frozen --group dev
make lint typecheck test audit   # canonical suite (CI runs the same)
./scripts/check.sh               # instruction-file lint, no network
docker compose run --rm pumpgrok # one skip-only replay cycle, exits 0
```

Use `uv run` for Python commands. The replay is the only executable path in Phase 1.

---

Generated and maintained sections follow. The GSD marker blocks below are kept verbatim.

<!-- GSD:project-start source:PROJECT.md -->

## Project

**PumpGrok Desk v2**

PumpGrok is a Solana memecoin (pump.fun launch) trading desk: ten LLM-backed seats (chief, scout, risk, whale, sniper, rug, exit, shill, signal, journal) plus a catalog of read-only and paper-write tools and a library of skills, packaged in the shape of programming-desk (`ownership.yaml`, receipts, gates G-1..G-7, contracts, prompt assembly, skill manifests) as a Python 3.12 package `src/pumpgrok/`. It is built for the operator who wants the desk to run autonomously in paper mode for the first 2-4 weeks, under an asyncio supervisor, against live Solana data, recording everything in an append-only ledger and replaying deterministically from fixtures. It can never move real funds: the only enabled execution adapter is a `PaperAdapter`, live adapters are disabled stubs behind a nine-precondition gate, and private keys never enter the system.

**Core Value:** The desk runs autonomously in paper mode for 2-4 weeks and produces honest, replayable reports; no code path can move real funds.

### Constraints

- **Security**: Paper-only hard default; `execution.mode` defaults to `paper`, `PaperAdapter` is the only enabled adapter, live adapters raise `LiveGateError`, and `pumpgrok run --mode live` exits 3 unless all nine R21 preconditions hold (precondition 8, a registered live adapter, never holds in this milestone) - the core value depends on no code path being able to move real funds.
- **Security**: No private keys, seed phrases or keypairs ever enter the system; forbidden config names abort startup, secrets arrive only via env, and an AST test fails on signing symbols outside the live stub - the security constitution (`rules/pumpgrok-team.mdc`) is kept verbatim.
- **Compliance**: Detect and trade on observed public signals only; no coordinated buying, wash trades, volume generation, shilling, social posting or wallet UI automation - D7/R39, enforced by `tests/safety/test_no_manipulation_tools.py` and the `notify.alert` allowlist.
- **Compliance**: Constitution clauses are enforced in code, not prose: ticket format `SOL-YYYYMMDD-NNN`, exact human approval phrase, single-send idempotency, RISK `KILL` non-overridable, 5% daily-loss `FLOOR HALTED` with human-only clear - D9, R5, R22, R23.
- **Compatibility**: Mirror programming-desk conventions exactly in shape and names (`ownership.yaml` with one owner per tracked path, gates G-1..G-7 plus self-test, receipts per PR under `.receipts/<seat>/`, prompt assembly from `prompts/*.xml`, skills with L1/L2/L3 bodies and manifests) - D1/D2, so operators and agents move between the two desks without relearning.
- **Compatibility**: Keep the Solana integrations exactly as today (mainnet JSON-RPC, pump.fun REST, PumpPortal WS, Jupiter Swap V2 order, x.ai Grok); nothing added, nothing dropped; Jito dead config and `wallet_private_key` removed - D8, R3.
- **Tech stack**: Python 3.12 only, `uv`, ruff, mypy --strict, pytest; money as integers in base units (lamports, token units) with `Decimal` only for ratios; ULIDs from `core/ids.py`; all time through the `Clock` (no direct `asyncio.sleep`/`time.time`) - D1, R27, R28, R29 keep replay deterministic and the ledger hash chain stable.
- **Process**: ASCII-only new docs (`scripts/check.sh` fails on emoji); constitutional strings keep their exact bytes (U+2013) in code - R7.
- **Process**: GSD workflow with code review and verification per phase; five phases cut per R37 so every checkpoint is buildable from Phase 1 with no waiver; one PR per batch on `bot-0N-<seat>/phase-<n>-<unit>` branches with a receipt and `python3 ci/gates/run_all.py` green.
- **Process**: Checkpoint rule after every phase: all canonical commands exit 0 (`make lint typecheck test audit`) and `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke` completes one cycle on fixture data (skip-only in Phase 1, engine decision from Phase 2, full ten-seat cycle from Phase 4) with no network - R37, SPE-18063.
- **Dependencies**: pump.fun frontend REST and PumpPortal WS are unofficial with heuristic field names; upstream payloads parse with `extra="ignore"` models, a malformed payload yields `DataStale`/`BLIND`, and `BLIND` is treated as `KILL` - upgrade plan section 8.1.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Scope and method

- Latest version and `requires_python` for every package from `https://pypi.org/pypi/<pkg>/json` (fetched 2026-10-21).
- Breaking-change review from each upstream changelog (URLs in Sources).
- Wheel contents checked for `py.typed` (prometheus-client 0.26.0, respx 0.23.1, httpx 0.28.1) and dependency metadata (pydantic-settings, respx, httpx).
- Installed `websockets==17.3` in a scratch venv under `/tmp` (outside the repo) to read the real `connect()` defaults.
- Live probes on 2026-10-21 (about 01:40 to 01:45 UTC) against Jupiter, PumpPortal, pump.fun, Solana mainnet RPC and x.ai. Results are labelled "observed live".
- Nothing in the repo was modified and no git, test or gate command was run.

## Verdict on docs/FOUNDATION_STACK.md

| # | FOUNDATION item | Finding | Required change |
|---|---|---|---|
| V-1 | pydantic-settings `>=2.16.0` (3.1) | 2.16.1 released 2026-10-20 fixes two CLI regressions from 2.16.0. We use no CLI settings, but there is no reason to floor below the fix | Floor to `>=2.16.1,<3` |
| V-2 | uv `0.13.3` installer and `uv_build >=0.13.3,<0.14.0` (table, Dockerfile, 3.1) | uv 0.13.4 released 2026-10-20 | Bump installer to 0.13.4 (Dockerfile `ghcr.io/astral-sh/uv:0.13.4`, CI SHA pin); `uv_build>=0.13.4,<0.14.0` |
| V-3 | uv default Python not addressed | uv 0.13.0 made Python 3.15 the default stable interpreter. `requires-python = ">=3.12,<3.13"` constrains resolution, but nothing pins the interpreter | Commit `.python-version` containing `3.12` (`uv python pin 3.12`) |
| V-4 | `make audit`: `uv export --frozen --no-dev --format requirements-txt --no-hashes` (3.2) | uv exports the current project by default. The project line cannot be audited as a pinned requirement, and pip-audit needs a resolvable file | Add `--no-emit-project` to the export. Keep `--strict` on pip-audit |
| V-5 | `[[tool.mypy.overrides]] module = ["prometheus_client.*", "respx.*"] ignore_missing_imports` (3.1); open item U-8 | Both wheels ship `py.typed` (verified in the wheels). Ignoring imports is no longer needed | Delete the override and close U-8 |
| V-6 | httpx 0.28 pin (3.1, M-3) | Current release is still 0.28.1 (2024-12-06), but the repo has commits as recent as 2026-02-23 (`httpx` GitHub commits API). No release in about 22 months | Keep the pin. Record the maintenance risk (section Risks). Re-check at each milestone |
| V-7 | websockets M-1: "import from `websockets.asyncio.client`" | Confirmed. Also confirmed from 17.3 source: `proxy=True` is the default, so an OS or env proxy is used automatically since websockets 15.0 | Add: pass `proxy=None` on the PumpPortal connection unless a proxy is intended. Set `max_queue` explicitly (default is 16) |
| V-8 | Jupiter Swap V1 retired (TOOL_CATALOG `market.price` fallback, `exec.simulate`, `jupiter_lite` rate key all move to V2) | V1 "is no longer actively maintained and has been superseded by Swap V2" per Jupiter's own page | Build the quote adapter against `GET https://api.jup.ag/swap/v2/order` with an API key. The V1 path is removed (R44), not kept as a fallback |
| V-9 | pytest-asyncio `>=1.4.0,<2`; `asyncio_mode = "auto"` | Holds. 1.0.0 removed the deprecated `event_loop` fixture. 1.4.0 deprecates overriding `event_loop_policy` in favour of the `pytest_asyncio_loop_factories` hook. 1.4.0 requires pytest >= 8.4 | Keep pins. Set `asyncio_default_fixture_loop_scope` explicitly (1.4 warns when unset) |
| V-10 | x.ai model names in config (FOUNDATION_STACK.md lines 385-387: `grok-4-fast`, `grok-4`) | Neither name is on the current x.ai models table (2026-10-21). The table lists `grok-4.7`, `grok-4.6`, `grok-4.5`, `grok-4.3`, `grok-4.20-*`, `grok-build-0.1`, `grok-4.20-multi-agent-0309` | Do not pin `grok-4` or `grok-4-fast`. Choose model IDs from the live model list at config time (see x.ai section). Also: `PUMPGROK_GROK__BASE_URL` is set to a full `/v1/chat/completions` URL; an OpenAI-SDK client expects `https://api.x.ai/v1` as base. Pick one convention |
| V-11 | PumpPortal data (TOOL_CATALOG market and signal tools) | Per-token trade subscriptions are refused without an API key funded with at least 0.02 SOL (observed live). See the PumpPortal section | Treat the PumpPortal API key as a secret. Budget the 0.01 SOL per 10,000 events metered fee. Raise with the orchestrator (see Risks) |
| V-12 | pump.fun `frontend-api.pump.fun` as the price and trades source (TOOL_CATALOG `market.price`, `market.ohlcv`, `onchain.holders`) | Observed HTTP 530 with body `error code: 1016` on every path tried, repeatedly, on 2026-10-21. Treat it as unreliable, not as an SLA | Make pump.fun REST a degradable source. Derive pre-graduation price from PumpPortal fields (section PumpPortal). See pump.fun section |

## Recommended Stack

### Core Technologies

| Technology | Version (verified) | Purpose | Why Recommended | Confidence |
|---|---|---|---|---|
| CPython | 3.12.x (`requires-python = ">=3.12,<3.13"`) | Runtime | Every pinned package supports 3.12. The 3.12 `sqlite3` transaction-control changes are handled in the ledger pattern below. Matches vendor and gateway precedent | HIGH |
| pydantic | 2.14.1 (2026-10-11; `requires_python >=3.10`) | Contracts, upstream payload parsing, config models | v2 is the only supported major line in this milestone. 2.14 dropped 3.9 and added 3.15 support. Keep the `pydantic.mypy` plugin | HIGH |
| pydantic-settings | 2.16.1 (2026-10-20; `requires_python >=3.11`) | Layered config (env + TOML + overlays) | `BaseSettings` with `env_prefix="PUMPGROK_"` and `env_nested_delimiter="__"` replaces the vendor's hand-rolled `GROKBOT_*` loader. Pins `python-dotenv>=1.2.2` (CVE-2026-28684 fix) transitively | HIGH (version); MEDIUM (multi-file TOML layering, see note) |
| httpx | 0.28.1 (2024-12-06; `requires_python >=3.8`) | Async HTTP for pump.fun, Jupiter, Solana JSON-RPC, x.ai | Typed (`py.typed`), `AsyncClient` with explicit `httpx.Timeout`. The 0.28 breaking changes are limited (see What NOT to Use) | HIGH (API); MEDIUM (maintenance cadence) |
| websockets | 17.3 (2026-10-19; `requires_python >=3.11`) | PumpPortal WebSocket client | Use `websockets.asyncio.client.connect`. The legacy implementation is deprecated since 14.0 and is not used. Ping/keepalive, bounded queue and reconnection backoff are built in | HIGH |
| sqlite3 (stdlib) | Python 3.12 bundled SQLite | Append-only, hash-chained ledger and snapshots | No dependency. WAL mode, single writer under `BEGIN IMMEDIATE`, explicit transaction control (pattern below). Matches FOUNDATION row 5 | HIGH |
| tenacity | 9.2.1 (2026-10-07; `requires_python >=3.10`) | Jittered retry on timeout, 5xx and 429 only | `AsyncRetrying` plus `wait_random_exponential` (verified present in 9.2.1 source) | HIGH |
| prometheus-client | 0.26.0 (2026-07-24; `requires_python >=3.9`) | `pumpgrok_*` metrics and `/metrics` exposition | `generate_latest()` served from the asyncio health server. Ships `py.typed` (verified in wheel) | HIGH |
| PyYAML | 6.0.3 (2025-09-25) | Rosters, gate inputs | Unchanged from FOUNDATION. Stubs via `types-PyYAML` | HIGH |

### Supporting Libraries

| Library | Version (verified) | Purpose | When to Use |
|---|---|---|---|
| uv_build | 0.13.4 (`>=0.13.4,<0.14.0`) | Build backend | Always. 0.13 made no breaking change to `[tool.uv.build-backend]` (changelog) |
| respx | 0.23.1 (2026-04-08; `requires_python >=3.8`; requires `httpx>=0.25.0`; `py.typed`) | Mock httpx in tests | All HTTP upstream tests. Does NOT mock WebSockets; PumpPortal tests need an in-process fake server or a fake connection object |
| pip-audit | 2.10.1 (2026-06-10; `requires_python >=3.10`) | Dependency vulnerability audit | `make audit` over the `uv export` file, `--strict` |
| hypothesis | 6.170.5 | Property tests for parsers and the hash chain | Deferred (FOUNDATION row 11 and section 1 are unchanged) |

### Development Tools

| Tool | Version (verified) | Purpose | Notes |
|---|---|---|---|
| ruff | 0.17.1 (2026-10-15; `requires_python >=3.7`) | Lint and format | Set `target-version = "py312"` explicitly: since 0.17.0 an unset target defaults to 3.11. 0.17.0 also changed its default rule set (several flake8-datetimez rules off by default, F406 on). Our `select` is explicit, so this does not change results, but the pin must stay |
| mypy | 2.4.0 (2026-10-01; `requires_python >=3.10`) | `mypy --strict` on `src/pumpgrok` | 2.0 turned on `--local-partial-types` and `--strict-bytes` by default and dropped 3.9 targets. Expect new errors in the ported vendor code. Keep `warn_unreachable = true` (not implied by `--strict`) and the pydantic plugin. Parallel checking exists (`-n N`), experimental |
| pytest | 9.1.1 (2026-06-19; `requires_python >=3.10`) | Test runner | 9.0 added native TOML config, subtests and a `strict` option. `[tool.pytest.ini_options]` from FOUNDATION 3.1 should keep working; confirm on first run |
| pytest-asyncio | 1.4.0 (2026-05-26; `requires_python >=3.10`; needs pytest >= 8.4) | Async tests | `asyncio_mode = "auto"`; use `loop_scope` / `asyncio_default_fixture_loop_scope`. Never use the removed `event_loop` fixture |
| uv | 0.13.4 (2026-10-20) | Installer, lockfile, export | Pin the installer in CI by commit SHA (open item U-4). Commit `uv.lock` and `.python-version` (see V-3) |
| types-PyYAML | 6.0.12.20260906 | YAML stubs | Keep |

## Installation

# Interpreter pin (uv 0.13 default stable is 3.15; pin the project)

# Runtime dependencies (FOUNDATION 3.1, with the corrections above)

# Dev group

# Lock and sync

# Audit (corrected: exclude the project itself)

- `[tool.mypy]` keeps `strict = true`, `warn_unreachable = true`, `plugins = ["pydantic.mypy"]`.
- Delete `[[tool.mypy.overrides]]` for `prometheus_client.*` and `respx.*` (V-5).
- `[tool.ruff] target-version = "py312"` (explicit, see tools table).

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|---|---|---|
| websockets 17 (asyncio) | aiohttp client WebSocket | If the whole process already runs on aiohttp. Not the case here; websockets is already decided and in the vendor code |
| httpx 0.28 | aiohttp | If you need connector-level control of many concurrent sockets. Not needed at this request volume |
| sqlite3 (stdlib, single writer) | aiosqlite | If many coroutines must write concurrently from one process. Here the ledger has one writer by design (PROJECT R26), so a thread or `asyncio.to_thread` wrapper around one connection is enough and adds no dependency |
| sqlite3 | PostgreSQL | Only if multi-process writers are ever needed. Live trading is out of scope, so not now |
| tenacity 9 | backoff | If you want decorator-only retries with no predicate composition. tenacity already covers predicates and `AsyncRetrying` |
| pydantic-settings | dynaconf | Only if the operator needs many runtime-editable config backends. The overlay model here is simple TOML plus env |
| prometheus-client | OpenTelemetry metrics SDK | If traces must be exported to an OTLP collector. FOUNDATION section 5.6 defers OTel explicitly; keep it deferred |
| mypy 2.x `--strict` | pyright | If mypy's plugin story for pydantic-settings proves weaker in practice. Decision stays mypy unless a concrete failure appears in the port |
| pip-audit over `uv export` | `uv`-native audit | Not evaluated further. Keep pip-audit, which FOUNDATION row 12 decided |

## What NOT to Use

| Avoid | Why | Use Instead |
|---|---|---|
| `websockets.legacy.*` or pre-14 `websockets.connect` imports | Legacy implementation is deprecated (since 14.0; warned in 15 and 16 changelogs). 17.0 also removed aliases deprecated in 9.0 | `from websockets.asyncio.client import connect` |
| Relying on the default websockets proxy behaviour | Since 15.0 connections use an OS or environment proxy automatically (`proxy=True` default, verified in 17.3 source). A proxy in the host environment silently changes the PumpPortal path | `connect(..., proxy=None)` unless a proxy is intended; document the choice |
| websockets default `max_queue` for bursty launch streams | Default is 16 frames (verified in 17.3 source). PumpPortal create/trade bursts can exceed that and back-pressure the reader | Set `max_queue` explicitly (e.g. `max_queue=1024`), and keep the consumer non-blocking |
| httpx `proxies=` and `app=` arguments | Removed in 0.28.0 (httpx CHANGELOG). String `verify=` and `cert=` are deprecated in 0.28 | `httpx.AsyncClient(proxy=..., transport=...)`; `verify=<ssl.SSLContext>` if needed |
| `pytest-asyncio` `event_loop` fixture and `asyncio.get_event_loop()` in tests | `event_loop` removed in pytest-asyncio 1.0.0. `event_loop_policy` override deprecated in 1.4.0 | `loop_scope` markers, `asyncio_default_fixture_loop_scope`, and the `pytest_asyncio_loop_factories` hook when a custom loop is needed |
| `respx` for WebSocket tests | respx mocks httpx only (its docs say so) | An in-process fake WebSocket server (`websockets.asyncio.server.serve` on localhost) or a fake connection object |
| sqlite3 default datetime adapters and converters | Deprecated as of Python 3.12 (sqlite3 docs) | Store ISO-8601 TEXT written explicitly with the `Clock`; parse explicitly |
| sqlite3 implicit legacy transactions with no explicit control | Python 3.12 default `autocommit` is `LEGACY_TRANSACTION_CONTROL` and "will change in a future Python release" | Pass `autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL` and `isolation_level=None`; issue `BEGIN IMMEDIATE` / `COMMIT` yourself |
| `synchronous=NORMAL` for the ledger database | SQLite WAL docs: with NORMAL the WAL is not synced on commit, so a power loss can roll back the most recent committed transactions. The ledger is the replay source of truth | `PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL` for `ledger.sqlite`. NORMAL is acceptable for disposable caches only |
| `float` for SOL or token amounts from upstream | PumpPortal sends `solAmount`, `initialBuy` and `vSolInBondingCurve` as JSON numbers (float). Floats break R28 | Parse the JSON number into `Decimal(str(value))`, then convert to integer lamports or base units |
| Jupiter Metis Swap V1 as the long-term quote source | Jupiter states V1 is "no longer actively maintained" and superseded by Swap V2 | Removed (R44). The only quote path is `GET https://api.jup.ag/swap/v2/order` with `x-api-key`; see Jupiter section for field mapping |
| Keyless Jupiter access in production | Keyless is 0.5 requests per second (30 per minute) per the rate-limit page. A scan of a few hundred candidates exhausts it in minutes | Free key: 1 RPS. Developer key: 10 RPS |
| pump.fun `frontend-api.pump.fun` as a hard dependency | HTTP 530 with Cloudflare `error code: 1016` on every path, repeatedly, on 2026-10-21. No public docs or SLA | Adapter with circuit breaker; price from PumpPortal bonding-curve fields; holders from Solana RPC `getTokenLargestAccounts` or the v3 top-holders endpoint, both marked unofficial |
| Public Solana mainnet RPC for production reads | Public endpoint: 100 requests per 10 s per IP, 40 per single RPC; `getTokenLargestAccounts` returned HTTP 429 "Too many requests for a specific RPC call" in the live probe. The docs say public endpoints are "not intended for production" | Configured failover list of paid RPC providers, keyed through the `solana.rpc_api_key` header (FOUNDATION M-7) |
| `grok-4` and `grok-4-fast` model IDs | Not on the current x.ai model table (2026-10-21) | Read the live list (`GET https://api.x.ai/v1/models` with a key) and pin a current ID such as `grok-4.7` (flagship) or `grok-4.3` (lower cost) by config |
| Trusting Grok for live market facts | x.ai models have no realtime knowledge without server-side search tools (models page) | Put market data in the prompt, or enable x.ai Web Search tools explicitly for the seat that needs it |
| `max_tokens` on x.ai chat completions | Deprecated in favour of `max_completion_tokens` (default 128,000 when unset) | `max_completion_tokens` |
| Pydantic `extra="allow"` on upstream models | Lets unknown upstream fields leak into the ledger | `extra="ignore"` for upstream payloads, `extra="forbid"` for our event contracts (FOUNDATION row 7) |
| `pydantic.v1` namespace | Compatibility shim; 2.14 still ships it | pydantic v2 APIs only |
| `uv export` without `--no-emit-project` feeding pip-audit | Project line is not an auditable pinned requirement | Add `--no-emit-project` (V-4) |
| Relying on uv's default interpreter selection | uv 0.13 default stable Python is 3.15 | Commit `.python-version` = `3.12` (V-3) |

## Stack Patterns by Variant

- Subscribe to `subscribeNewToken` and `subscribeMigration` only (both free per the docs). Per-token `subscribeTokenTrade` is refused without a funded key (observed live).
- Mark trade-derived signals (`signal`, `whale`) as `data_unavailable` instead of falling back to guesses.
- Use one WebSocket connection for all subscriptions. PumpPortal asks for one connection, no more than 200 subscribe messages per second, and no more than 5000 keys per message; violators are banned for about an hour (FAQ).
- Budget the metered fee: 0.01 SOL per 10,000 messages received. The replay recorder should record only subscribed keys to keep fixtures small.
- Use `api.jup.ag/swap/v2/order` with `x-api-key`. Free tier is 1 RPS and 60 per minute; Developer is 10 RPS. Respect `x-ratelimit-reset` (Unix seconds) in backoff, per the rate-limit page.
- Keyless 0.5 RPS. Limit `jupiter_lite` concurrency to 1 and cache quotes for the quote TTL. Do not use this in the 2-4 week autonomous run.
- No live network. Use respx for httpx upstreams and the in-process WebSocket fake for PumpPortal. Clock comes from the fixture (PROJECT R27).
- Keep the circuit breaker open for that source and continue on PumpPortal and RPC data. `market.price` reports `source: curve` from PumpPortal `vSolInBondingCurve / vTokensInBondingCurve` when available.

## Version Compatibility

| Package A | Compatible With | Notes |
|---|---|---|
| pydantic 2.14.1 | pydantic-settings 2.16.1 | settings 2.16 requires pydantic >= 2.7 (PyPI metadata) |
| pydantic-settings 2.16.1 | python-dotenv >= 1.2.2 | Required by settings 2.16.0 for CVE-2026-28684; pinned transitively |
| pydantic-settings 2.16.x | Python >= 3.11 | Python 3.10 support removed in 2.16.0 |
| pydantic 2.14 | mypy 2.4 with `pydantic.mypy` plugin | Plugin synthesises `BaseSettings.__init__` signatures; changed in the 2.x line (pydantic release notes) |
| websockets 17.3 | Python >= 3.11 | 17.0 keyword-only `send(text=...)`, `ping(ack_on_close=...)`, `broadcast(raise_exceptions=...)`. 17.0 also changed `process_request` for non-GET requests (client code unaffected) |
| httpx 0.28.1 | respx 0.23.1 | respx requires `httpx>=0.25.0` (PyPI metadata) |
| httpx 0.28.1 | Python >= 3.8 (lib); desk uses 3.12 | Standard |
| pytest 9.1.1 | pytest-asyncio 1.4.0 | pytest-asyncio 1.4.0 requires pytest >= 8.4 |
| pytest-asyncio 1.x | `event_loop` fixture | Removed in 1.0.0 (changelog "Removed") |
| uv 0.13.4 | `uv_build` 0.13.4 | Same release day; use the matching pair |
| uv 0.13.x | `requires-python` `>=3.12,<3.13` | Interpreter pin via `.python-version` avoids the 3.15 default |
| ruff 0.17.1 | `target-version = "py312"` | Explicit target avoids the 3.11 default introduced in 0.17.0 |
| mypy 2.4 | Python 3.12 target | 3.9 target removed; `--local-partial-types` and `--strict-bytes` default on |
| prometheus-client 0.26.0 | mypy `--strict` | Ships `py.typed`; no import override needed |
| sqlite3 (Python 3.12) | `autocommit=` keyword | New in 3.12; default LEGACY, documented as future-changing; set explicitly |

## Upstream API Surfaces (verified 2026-10-21)

### Jupiter (quotes)

- Metis Swap V1 quote (retired per R44; dated probe record, do not use): `GET .../swap/v1/quote?inputMint&outputMint&amount&slippageBps`. Observed live 2026-10-21: HTTP 200 with `inAmount`, `outAmount`, `otherAmountThreshold` (string integer, minimum out after slippage), `priceImpactPct` (string, decimal ratio, e.g. `"0"`), `routePlan` (array of `{swapInfo, percent, bps}`), `contextSlot`, `swapMode`, `slippageBps`, `platformFee`. Source: `https://developers.jup.ag/docs/swap/v1/get-quote`.
- Deprecation: the same page warns "Metis Swap API is no longer actively maintained and has been superseded by Swap V2". Source: same page.
- Swap V2 order, `GET https://api.jup.ag/swap/v2/order`. Observed live without a key: HTTP 200, with `router` (`jupiterz` won the keyless test quote), `priceImpact` (number in percentage points), `priceImpactPct` marked deprecated (decimal ratio, "Use priceImpact divided by 100"), `otherAmountThreshold` (string), `routePlan`, `swapUsdValue`, `requestId`, `taker` optional. Source: `https://developers.jup.ag/docs/api-reference/swap/order.md`.
- Unit trap: V1 `priceImpactPct` is already a ratio; V2 `priceImpact` is percent points. Map as `Ratio = priceImpact / 100` (decimal string). Quote values are integer strings; keep `Units`/`Lamports` as ints.
- Routing trap: without `taker` and with default params all routers compete (Metis, JupiterZ RFQ, Dflow, OKX). Setting `payer` different from `taker` restricts routing to Metis. Choose deliberately; the desk's fill model uses bonding-curve reserves, so Jupiter is informational (R38). Source: order API reference.
- Rate limits: keyless 0.5 RPS (30/min); Free 1 RPS (60/min); Developer 10 RPS (600/min); Launch 50; Pro 150. Sliding 60-second window. Headers on 200 and 429: `x-ratelimit-remaining`, `x-ratelimit-current`, `x-ratelimit-reset` (Unix seconds). Source: `https://developers.jup.ag/docs/portal/rate-limits.md`.
- V1 rate and latency notes retired with the path above. Quote adapter targets `api.jup.ag/swap/v2/order` with `x-api-key` (Free key minimum). Confidence: HIGH (fields and docs).

### PumpPortal (WebSocket)

- Endpoint: `wss://pumpportal.fun/api/data?api-key=...`. Source: `https://pumpportal.fun/data-api/real-time/`.
- Free methods: `subscribeNewToken`, `subscribeMigration`. Metered: `subscribeTokenTrade` (keys = token mints) and `subscribeAccountTrade` (keys = wallets), 0.01 SOL per 10,000 events, linked wallet funded with at least 0.02 SOL. Unsubscribe: `unsubscribeNewToken`, `unsubscribeTokenTrade`, `unsubscribeAccountTrade`. Source: same page.
- Observed live without a key (2026-10-21): `{"method":"subscribeNewToken"}` returned ack `{"message":"Successfully subscribed to token creation events."}` then data frames. `{"method":"subscribeTokenTrade","keys":[mint]}` returned `{"message":"'subscribeTokenTrade' and 'subscribeAccountTrade' methods are only available when connecting with an API key funded with at least 0.02 SOL."}`. No trade frames were received without a key. <!-- pragma: allowlist secret: JSON-RPC method names, not credentials -->
- Observed create payload (3 frames, 2026-10-21), keys: `signature`, `mint`, `traderPublicKey`, `txType` (`"create"`), `initialBuy` (number), `solAmount` (number, float), `bondingCurveKey`, `vTokensInBondingCurve` (number), `vSolInBondingCurve` (number), `marketCapSol` (number), `name`, `symbol`, `uri`, `is_mayhem_mode` (bool), `pool` (`"pump"`). Ack frames have only `message`; the consumer must discard them. Shape verified only for `create`; trade-frame field names are NOT verified live, and the vendor parser reads `txType`, `traderPublicKey`, `solAmount` (`vendor/grokbot-pumpfun/src/monitor.py:133`, `src/analyzer.py:134`).
- Limits (FAQ, `https://pumpportal.fun/FAQ`): one WebSocket connection (subscribe over it); no more than 200 subscribe messages per second; no more than 5,000 keys in a single message; temporary bans of about one hour on violations.
- Single client connection with `proxy=None`, explicit `max_queue`, library keepalive defaults, and reconnect with backoff (`connect()` accepts `reconnect_delays` per the changelog; the `WEBSOCKETS_BACKOFF_*` environment variables are the other knob). Re-send subscriptions after every reconnect.
- Decimal parse of all money fields (V-11 and What NOT to Use).
- Derive pre-graduation price as `vSolInBondingCurve / vTokensInBondingCurve` (SOL per token, base units to be normalised). Create-frame sample: 30 SOL / 1,073,000,000 tokens. Confidence for trade frames: MEDIUM (field presence inferred from create frames; verify once a funded key exists).
- Confidence on the payload shape for `create`: HIGH (live). For trades: LOW until verified.

### pump.fun frontend REST (unofficial, no docs)

- `GET https://frontend-api.pump.fun/coins/{mint}`: HTTP 530, body `error code: 1016`. Same for `/trades/all/{mint}?limit=5`, `/coins/{mint}/holders`, and `/coins/top-holders/{mint}`. Repeated twice. Cloudflare error 1016 is an origin-side DNS error in Cloudflare's error reference (`https://developers.cloudflare.com/support/troubleshooting/cloudflare-errors/troubleshooting-cloudflare-1xxx-errors/`). Cause on pump.fun's side is [INFERENCE].
- `GET https://frontend-api-v3.pump.fun/coins/top-holders/{mint}`: HTTP 200 JSON `{"topHolders":[{"address","amount","isDev","isSniper","isBundler","enteredAt","fundingSource"}, ...]}`.
- `GET https://frontend-api-v3.pump.fun/coins/{mint}`: HTTP 404. `GET https://frontend-api-v3.pump.fun/trades/all/{mint}`: HTTP 400 requiring a `chainId` in form `solana:<base58>`; the path form and query form both failed the regex in the probe. The v3 trades contract is not yet determined.
- `swap-api.pump.fun/v1/coins/{mint}`: HTTP 404.
- Treat pump.fun REST as optional and degradable. Do not write the v1 vendor paths into new code without a fresh probe. Holder data: prefer Solana RPC `getTokenLargestAccounts` (20 accounts) through a paid provider, with v3 top-holders as an unofficial fallback. Confidence: HIGH that v1 failed today; LOW on how long.

### Solana JSON-RPC

- `getRecentPrioritizationFees`: optional `addresses` array (max 128, base58). Result: array of `{slot, prioritizationFee}` with fee in micro-lamports per compute unit; the node caches up to 150 blocks. Omit params for an unfiltered list. The repo calls it with `[[]]` at `tools/priority_fee.py:45`; verify that an empty array means unfiltered on the chosen provider. Observed live on `api.mainnet.solana.com`: HTTP 200 with a list of `{prioritizationFee, slot}`. Source: `https://solana.com/docs/rpc/http/getrecentprioritizationfees`. Confidence: HIGH.
- `getTokenLargestAccounts(mint, {commitment})`: returns up to 20 token accounts; `value[]` items `{address, amount (raw string), decimals, uiAmount (deprecated), uiAmountString}`. Observed live on public mainnet: HTTP 429 `Too many requests for a specific RPC call`. Source: `https://solana.com/docs/rpc/http/gettokenlargestaccounts`. Confidence: HIGH for shape; the public endpoint cannot be used for it. Requires a paid provider.
- `getAccountInfo` with `{"encoding":"jsonParsed"}`: observed live on mainnet for the wSOL mint address: HTTP 200 with `value.data.parsed` (`type: "mint"`, `decimals`, `supply`, `mintAuthority`, `freezeAuthority`), `program: "spl-token"`, `space: 82`. Parsed data exists only for programs the node knows; handle base64 `data` as the fallback. Source: `https://solana.com/docs/rpc/http/getaccountinfo`. Confidence: HIGH.
- Public endpoint limits (`https://solana.com/docs/references/clusters`): 100 requests per 10 s per IP; 40 per single RPC; 40 concurrent connections; 100 MB per 30 s; HTTP 403 means blocked, 429 means slow down and honour `Retry-After`. "Not intended for production applications."
- Commitment defaults to `finalized` in these docs; choose explicitly per tool (`processed` or `confirmed` for market context, `finalized` for ledger-anchored reads).

### x.ai Grok

- `grok-4.7`: 500k context; input $2.00 / cached $0.50 / output $6.00 per 1M tokens for prompts under 200k (double above 200k). Structured outputs: yes; function calling: yes; reasoning efforts `low|medium|high|xhigh`, default `high`. Rate limit 150 RPS and 50M tokens per minute (`https://docs.x.ai/developers/models/grok-4.7`). Batch API is 20% off.
- `grok-4.3`: 1M context; $1.25 / $0.20 / $2.50.
- `grok-4.20-0309-non-reasoning` and `-reasoning`: 1M context; $1.25 / $0.20 / $2.50.
- `grok-build-0.1`: 256k; $1.00 / $0.20 / $2.00.
- Not on the table: `grok-4`, `grok-4-fast`, `grok-3`. Aliases: `<model>` and `<model>-latest` point to the latest stable; `<model>-<date>` is pinned.
- Models have no realtime knowledge without server-side search tools (models page).
- Confidence: HIGH for prices and context as published; the price table is the authority and must be re-read at deploy time.
- Chat Completions: `POST https://api.x.ai/v1/chat/completions`, OpenAI-compatible. The docs call it "the stateless, OpenAI-compatible predecessor" of Responses and recommend Responses for new integrations. Source: `https://docs.x.ai/developers/rest-api-reference/inference/chat-completions`; migration: `https://docs.x.ai/developers/model-capabilities/text/comparison`.
- Recommendation: Responses API for new seat code (`POST https://api.x.ai/v1/responses`), with structured output via its `format` object (the Responses reference shows a `format` block; confirm the exact key on the page before coding). Chat Completions stays acceptable for one-off probes. Confidence: MEDIUM-HIGH.
- Parameters: `max_completion_tokens` (default 128,000 when unset) replaces `max_tokens`; `reasoning_effort` values depend on model; `logprobs` silently ignored on `grok-4.20` and newer; `presence_penalty`/`frequency_penalty` not for reasoning models.
- `response_format` with `type: "json_schema"` and `json_schema` (strict is implicit for tools). Output is guaranteed to match the subset of JSON Schema supported.
- Supported: `string`, `number`, `integer`, `boolean`, `null`, `enum`, `const`, `array`, `object`, `anyOf`/`oneOf`, single-entry `allOf`, non-circular `$ref`/`$defs`.
- Enforced `format` only for `date, time, date-time, email, uuid, ipv4, ipv6, uri`.
- Limits: `minLength`/`maxLength` 2048; `minItems`/`maxItems` 256; `minProperties`/`maxProperties` 64; numeric bounds unlimited.
- Best-effort (not guaranteed): `not`, `if/then/else`, multi-entry `allOf`, other formats, limits above.
- `additionalProperties` defaults to `false` and must be set to `true` explicitly to allow extras.
- Schemas that return 400: enum or anyOf with zero variants, among other rules listed on the page (read the "Rejected schemas" section before adding schemas).
- Recommendation: generate the schema from the seat's pydantic model (`model_json_schema()`), keep it within the limits, and re-validate every reply with pydantic regardless of the guarantee. Confidence: HIGH for the subset; MEDIUM for schema-generation details (verify with a live call under a key).

## Risks and open items (for the roadmap)

## Sources

- https://pypi.org/pypi/pydantic/json, https://pypi.org/pypi/pydantic-settings/json, https://pypi.org/pypi/httpx/json, https://pypi.org/pypi/websockets/json, https://pypi.org/pypi/respx/json, https://pypi.org/pypi/tenacity/json, https://pypi.org/pypi/prometheus-client/json, https://pypi.org/pypi/ruff/json, https://pypi.org/pypi/mypy/json, https://pypi.org/pypi/pytest/json, https://pypi.org/pypi/pytest-asyncio/json, https://pypi.org/pypi/pip-audit/json, https://pypi.org/pypi/uv/json, https://pypi.org/pypi/uv-build/json, https://pypi.org/pypi/pyyaml/json, https://pypi.org/pypi/types-PyYAML/json, https://pypi.org/pypi/hypothesis/json. Wheel checks: prometheus_client-0.26.0 and respx-0.23.1 `py.typed`; httpx-0.28.1 `py.typed`; pydantic-settings and respx metadata.
- pydantic 2.14.0 release: https://github.com/pydantic/pydantic/releases/tag/v2.14.0 (and HISTORY: https://raw.githubusercontent.com/pydantic/pydantic/main/HISTORY.md) - HIGH
- pydantic-settings 2.16.0 and 2.16.1 release metadata: https://api.github.com/repos/pydantic/pydantic-settings/releases/tags/v2.16.0 and .../v2.16.1 - HIGH
- pydantic-settings docs (Sources, `TomlConfigSettingsSource`): https://docs.pydantic.dev/latest/concepts/pydantic_settings/ - MEDIUM
- httpx CHANGELOG (0.28.0 removals): https://github.com/encode/httpx/blob/master/CHANGELOG.md - HIGH; last commit date: https://api.github.com/repos/encode/httpx/commits - HIGH
- websockets changelog (15.0 proxy default, 16.0 legacy deprecation, 17.0 keyword-only args and Python floor, 17.0.1 uvloop fix): https://raw.githubusercontent.com/python-websockets/websockets/main/docs/project/changelog.rst and https://websockets.readthedocs.io/en/stable/project/changelog.html - HIGH
- websockets 17.3 source defaults (`max_queue=16`, `proxy=True`): installed package, `websockets/asyncio/client.py` lines 72, 276 (scratch venv) - HIGH
- respx CHANGELOG: https://github.com/lundberg/respx/blob/master/CHANGELOG.md - HIGH
- tenacity source (`wait_random_exponential`): https://raw.githubusercontent.com/jd/tenacity/main/tenacity/wait.py - HIGH
- prometheus_client: https://github.com/prometheus/client_python (release 0.26.0) - MEDIUM (changelog file on GitHub was empty; version and `py.typed` verified in wheel)
- ruff CHANGELOG 0.17.0 and 0.17.1: https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md - HIGH
- mypy CHANGELOG (2.0 section): https://github.com/python/mypy/blob/master/CHANGELOG.md - HIGH
- pytest changelog (9.0.0 native TOML, subtests, strict; 9.1.x): https://docs.pytest.org/en/stable/changelog.html (source: https://raw.githubusercontent.com/pytest-dev/pytest/main/doc/en/changelog.rst) - HIGH
- pytest-asyncio changelog (1.0.0 removed `event_loop`; 1.3.0 pytest 9 support; 1.4.0 loop factories, pytest >= 8.4): https://pytest-asyncio.readthedocs.io/en/stable/reference/changelog.html - HIGH
- pip-audit README (`-r`, `--strict`, `--skip-editable`, `--no-deps`): https://github.com/pypa/pip-audit - HIGH; changelog: https://github.com/pypa/pip-audit/blob/main/CHANGELOG.md - HIGH
- uv CHANGELOG (0.13.0 default Python 3.15; 0.13.x notes): https://github.com/astral-sh/uv/blob/main/CHANGELOG.md - HIGH
- uv CLI reference (`uv export --no-emit-project`, `--no-dev` alias): https://docs.astral.sh/uv/reference/cli/ - HIGH
- Python 3.12 sqlite3 (autocommit, LEGACY default, deprecated default adapters and converters): https://docs.python.org/3.12/library/sqlite3.html - HIGH
- SQLite WAL (synchronous FULL vs NORMAL durability): https://sqlite.org/wal.html - HIGH
- Metis quote (deprecation notice, V1 fields): https://developers.jup.ag/docs/swap/v1/get-quote (markdown: https://developers.jup.ag/docs/swap/v1/get-quote.md) - HIGH
- Swap V2 order reference: https://developers.jup.ag/docs/api-reference/swap/order.md; Order and execute: https://developers.jup.ag/docs/swap/order-and-execute.md - HIGH
- Rate limits: https://developers.jup.ag/docs/portal/rate-limits.md - HIGH
- Index: https://developers.jup.ag/docs/llms.txt - MEDIUM
- Live: `api.jup.ag/swap/v2/order` (HTTP 200, keyless) on 2026-10-21 - HIGH for presence
- Real-time data: https://pumpportal.fun/data-api/real-time/ - HIGH
- FAQ (rate limits, one connection, 200 subscribe/s, 5,000 keys): https://pumpportal.fun/FAQ - HIGH
- Live: subscribeNewToken payload samples (3 frames) and the funded-key refusal for `subscribeTokenTrade`, 2026-10-21 - HIGH for create shape, LOW for trade shape
- Live probes on `frontend-api.pump.fun` and `frontend-api-v3.pump.fun`, 2026-10-21 - HIGH for observed status
- Cloudflare 1xxx error reference: https://developers.cloudflare.com/support/troubleshooting/cloudflare-errors/troubleshooting-cloudflare-1xxx-errors/ - MEDIUM for meaning of 1016
- getRecentPrioritizationFees: https://solana.com/docs/rpc/http/getrecentprioritizationfees - HIGH
- getTokenLargestAccounts: https://solana.com/docs/rpc/http/gettokenlargestaccounts - HIGH
- getAccountInfo: https://solana.com/docs/rpc/http/getaccountinfo - HIGH
- Public RPC endpoints and limits: https://solana.com/docs/references/clusters - HIGH
- Live: `api.mainnet.solana.com` for getRecentPrioritizationFees (200), getTokenLargestAccounts (429), getAccountInfo jsonParsed (200), 2026-10-21 - HIGH
- Models and pricing: https://docs.x.ai/developers/models (markdown: https://docs.x.ai/developers/models.md) - HIGH
- grok-4.7 model page: https://docs.x.ai/developers/models/grok-4.7 - HIGH
- Structured outputs: https://docs.x.ai/developers/model-capabilities/text/structured-outputs - HIGH
- Chat Completions reference: https://docs.x.ai/developers/rest-api-reference/inference/chat-completions - HIGH
- Responses reference: https://docs.x.ai/developers/rest-api-reference/inference/responses (markdown: `.../responses.md`) - MEDIUM (exact structured-output key to confirm)
- Migration Chat -> Responses: https://docs.x.ai/developers/model-capabilities/text/comparison - HIGH
- `docs/FOUNDATION_STACK.md` sections 1, 3.1, 3.2, 3.3, 7 (M-1 through M-10, U-1 through U-9)
- `docs/TOOL_CATALOG.md` (market.price, market.ohlcv, onchain tools, exec.simulate, jupiter_quote)
- `vendor/grokbot-pumpfun/src/monitor.py:63,133,219,238,256`, `vendor/grokbot-pumpfun/src/analyzer.py:84,86,134`, `tools/priority_fee.py:45`

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-fast` for a trivial task inline, with no subagents and no PLAN.md
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
