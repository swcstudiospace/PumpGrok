# Foundation Stack: choices vs programming-desk precedent

Tracker: SPE-17997 https://linear.app/swcstudio/issue/SPE-17997/n5-foundation-stack-choices-vs-programming-desk-precedent | Notion https://app.notion.com/p/3ffbc1a0c7ae81d58f54d92ba28f167b?pvs=204

Node n5 of ultrathink graph ut-mvgfr96y-be17fc96. Design document only: nothing in this file is
installed, committed, or executed by this wave. Every repository fact cites `file:line`; every
PyPI fact cites the command and the response field; inferences are tagged `[INFERENCE]`.

Scope: the engineering foundation under `src/pumpgrok/` and the repo-level tooling that the
programming-desk skeleton (D2) expects. Trading semantics (sizing, breakers, exit rules) belong
to `docs/RISK_POLICY.md` and `docs/SAFETY_INVARIANTS.md`; the tool rosters belong to
`docs/TOOL_CATALOG.md`; the paper engine belongs to `docs/design/paper-engine.md`. This document
fixes *which libraries, pins, files, commands and gate rules* those designs may assume.

Canonical CLI names used below (orchestrator decision R12/R40, binding across all design docs):
`pumpgrok run --mode paper|live [--once] [--replay <dataset>] [--record <dataset> --duration <s>]`,
`pumpgrok doctor|audit`, `pumpgrok verify [--fixture <dataset>]`, `pumpgrok report --daily|--weekly`,
seat verbs `pumpgrok scout discover|pipeline`, `pumpgrok risk audit`, `pumpgrok chief pickup`,
`pumpgrok rug watch`, `pumpgrok journal rollup`, plus `pumpgrok ticket next|create|list`,
`pumpgrok state status`, `pumpgrok state halt [--reason <text>] | --clear --by <human> --reason <text>`,
`pumpgrok state autonomy <manual-ticket|autonomous-paper>`,
`pumpgrok paper buy|sell --ticket <SOL-YYYYMMDD-NNN> --mint <mint> --size-sol <sol> --slippage-bps <bps> --approval-id <id>`,
`pumpgrok killswitch set|status` and `pumpgrok killswitch clear --by <human> --reason <text>` (clear is
CLI-only, R22), `pumpgrok live confirm` (writes the HMAC-signed human confirmation record, R21),
`pumpgrok replay trim|rebuild-ticks`. CLI subcommands are thin wrappers over the in-process
tool registry (dotted `<ns>.<verb>` names such as `market.price`, `exec.place`; R19).

## 0. Starting point (what exists today)

| Fact | Evidence |
|---|---|
| No root packaging, lint, type, test or CI config; only `.devcontainer.json`, `plugin.json`, `scripts/`, `tools/`, `tests/`, `vendor/` | `ls -a` at repo root (2026-10-20): `.claude-plugin .cursor-plugin .devcontainer.json .git .grok-plugin ARCHITECTURE.md LICENSE README.md SETUP.md agents banner.jpg hermes issues plugin.json rules scripts skills tests tools vendor` |
| No root `.gitignore`; six compiled files are tracked | `git ls-files \| grep -E '\.pyc$'` -> `tests/__pycache__/test_tools_cli.cpython-312.pyc`, `tools/__pycache__/{authority_check,holder_check,jupiter_quote,paper_sim,priority_fee}.cpython-312.pyc` (node n2 marks them `delete`; this node supplies the `.gitignore`) |
| Vendored engine already uses pydantic v2 `BaseModel`/`SecretStr`, `httpx.AsyncClient`, `websockets.connect`, stdlib `logging` | `vendor/grokbot-pumpfun/src/models.py:19`, `:271-278`, `:299`; `src/agents/base.py:20,75,165,171`; `src/monitor.py:23,218`; `src/log.py:27-36` |
| Vendored engine env override scheme `GROKBOT_*` -> config path | `vendor/grokbot-pumpfun/src/models.py:403-407,486-490` |
| Vendored engine ships a hand-rolled Prometheus text exposition and a raw-asyncio `/healthz` + `/metrics` server | `vendor/grokbot-pumpfun/src/ops.py:41,67,299-300,355-357` |
| Vendored engine pyproject: setuptools, `>=` ranges, ruff `line-length = 100`, ruff select `E F W I UP B ASYNC C4 SIM RUF`, mypy non-strict with `exclude tests/ scripts/` | `vendor/grokbot-pumpfun/pyproject.toml:1-3,12-19,46-51,62-69` |
| Vendored Dockerfile: `python:3.12-slim`, non-root `grokbot`, VOLUME logs/state, HEALTHCHECK on `/healthz`, STOPSIGNAL SIGTERM; single stage | `vendor/grokbot-pumpfun/Dockerfile:5,15,26,32-36,39` |
| Vendored compose: one service, `restart: unless-stopped`, `stop_grace_period: 45s`, env-driven, health port bound to 127.0.0.1, json-file log rotation, 512M limit | `vendor/grokbot-pumpfun/docker-compose.yml:7-34` |
| Hermes forbids these env keys from ever reaching a profile: `PRIVATE_KEY SECRET_KEY SEED MNEMONIC PHANTOM WALLET_SECRET` | `hermes/profiles.yaml:18-24` |
| `scripts/check.sh` fails the repo on any emoji in `**/*.md` (vendor excluded) and `rules/*.mdc` | `scripts/check.sh:140-146` (regex `[\U0001F300-\U0001FAFF\u2600-\u27BF]`) |
| Constitution the code must enforce: ticket id `SOL-YYYYMMDD-NNN` + exact approval message; single-send + `UNKNOWN RESULT`; RISK KILL absolute; 5 % daily loss `FLOOR HALTED` | `rules/pumpgrok-team.mdc:28,30,32,34` |

## 1. Decision table

Precedent column reads the real programming-desk files. "Chosen" follows D5 unless the precedent
gives a stronger reason. "Risk" is the known downside we accept.

| # | Concern | programming-desk precedent (file:line) | Chosen for pumpgrok | Rationale | Risk |
|---|---|---|---|---|---|
| 1 | Config loader (dev/paper/live overlays) | Gateway reads env only via a plain `@dataclass Settings` with `_env()` helpers (`services/desk-gateway/src/desk_gateway/config.py:39-83`); no TOML, no overlays | `pydantic-settings` `BaseSettings` with `env_prefix="PUMPGROK_"`, nested delimiter `__`. ONE overlay location, shipped inside the package: `src/pumpgrok/config/overlays/{dev,paper,live}.toml`, selected by `PUMPGROK_PROFILE` (default `paper`); an optional operator overlay `PUMPGROK_CONFIG=<file>` is applied last; `PUMPGROK_*` env vars override every file; there is NO `config/` directory at the repo root (R30). Effective `execution.mode` precedence: CLI `--mode` > env `PUMPGROK_MODE` > TOML `execution.mode`; the live gate (R21) evaluates the merged effective mode, so `--mode live` with a paper profile still runs the gate. `mode: Literal["paper","live"] = "paper"`; secrets only via env, typed `SecretStr` (vendor pattern `models.py:271-278`) | Precedent is a 20-field gateway; the desk has 8 config sections (vendor `Config` fields, `models.py:455`) and three environments, so a typed, layered loader is needed. Env override semantics match vendor `ENV_OVERRIDES` (`models.py:403-407`), so the port is mechanical | Three sources (profile TOML, operator TOML, env) can confuse operators; mitigated by `pumpgrok doctor` printing the effective, redacted config and its source per field |
| 2 | Structured JSON logging + correlation IDs | `src/desk/telemetry/audit_tracer.py:1-38`: JSONL audit records, canonical JSON, sha256 hash chain, credential redaction; stdlib only. Gateway uses stdlib `logging` with `log_level` from env (`config.py:67`) | stdlib `logging` + a `JsonFormatter` (`src/pumpgrok/logging/json.py`) + `contextvars` for `correlation_id`, `seat`, `ticket_id`; a `RedactionFilter` applied to every handler; stderr handler always on, rotating file handler under `var/log/` when configured | Zero new dependency, matches precedent's stdlib stance; hash-chained audit JSONL is reused verbatim for the ledger's `events` export (section 5) | Hand-rolled formatter must be tested for non-serialisable payloads (fall back to `repr`) |
| 3 | Metrics / spans | Vendor hand-rolls `Metrics.prometheus()` text and a raw asyncio HTTP server (`vendor/.../ops.py:41-67,299-357`). programming-desk has no metrics endpoint in `src/desk` (directory listing: `security session supervision telemetry diagnostics recovery assertions`) | `prometheus_client` (Counter/Gauge/Histogram) with `generate_latest()` served by the same minimal asyncio HTTP server pattern on `/metrics`; `/healthz` JSON 200/503 kept from vendor; spans = `with span("stage.analyze", correlation_id=...)` context manager emitting a `Histogram` observation and one JSON log line (`event="span"`) | Replaces 60 lines of bespoke exposition with the reference client; keeps the no-framework HTTP server so no `uvicorn`/`fastapi` enters the trading process | `prometheus_client` default registry is process-global; tests must use a fresh `CollectorRegistry` |
| 4 | Scheduler / event loop | `src/desk/supervision/process_supervisor.py` (12.4 KB) supervises child processes; vendor `Pipeline.serve`/`_guarded` semaphore `MAX_CONCURRENT_TOKENS=4` (`vendor/.../pipeline.py:137,211`) | `asyncio` single process: `Supervisor` (`src/pumpgrok/supervisor/`) owns named tasks (monitor, analyzer workers, position watcher, kill-switch poller, health server, reporter); restart-with-backoff per task; `--once` runs one cycle and exits; `--replay <dir>` swaps live sources for JSONL fixtures | D5 says asyncio supervisor; vendor already structures the loop this way, so porting is a move not a rewrite | Single process = single failure domain; acceptable for paper mode, revisited at live gate |
| 5 | Persistence (ledger / journal) | `audit_tracer.py` JSONL with `seq`, `prev_hash`, `record_hash` (`:23-38,53-63`); gateway optional `psycopg`/`redis` extras (`services/desk-gateway/pyproject.toml:21-23`); vendor atomic JSON `StateStore` (`vendor/.../state.py:48-93`) | `sqlite3` in WAL mode at `var/ledger.sqlite` (replay runs use `var/replay/<dataset>/ledger.sqlite`, R21): append-only `events(seq, ts_utc, source, correlation_id, idempotency_key, type, payload_json, prev_hash, hash)` + `snapshots(seq, ts_utc, state_json)` exactly as `docs/design/paper-engine.md` section 3.2 (R32); `source` in `{paper, replay, manual}`; event `type` values are the CamelCase names defined once in `src/pumpgrok/ledger/events.py` (R32); every append goes through `ledger/store.py` under `BEGIN IMMEDIATE` with the hash chain computed inside the transaction (R26); JSONL journal export `pumpgrok journal rollup` writes `var/journal/YYYY-MM-DD.jsonl` carrying the same `seq`/`prev_hash`/`hash` chain the precedent `audit_tracer.py` uses (names differ: `record_hash` -> `hash`, `id` -> `seq`) | stdlib, transactional, queryable for the 5 % daily-loss floor and drawdown; hash chain reuses the precedent idea with the ledger's column names | WAL on network filesystems is unsafe; `pumpgrok doctor` checks `journal_mode=wal` and refuses non-local paths |
| 6 | HTTP / RPC client (timeouts, jittered retries, failover) | Gateway: `httpx>=0.28.1` (`services/desk-gateway/pyproject.toml:10`), `TOOL_DEADLINE_SEC = 20.0` (`config.py:28`); vendor: `httpx.AsyncClient(timeout=...)` with hand-rolled exp+jitter backoff and 5xx/429-only retry (`vendor/.../agents/base.py:75,165-174`) | One shared client in `src/pumpgrok/tools/onchain/rpc.py` (R31) plus one `httpx.AsyncClient` per upstream (pump.fun REST, Jupiter lite-api, Solana JSON-RPC, x.ai) with explicit `httpx.Timeout(connect=3, read=10, write=5, pool=5)`; `tenacity` `AsyncRetrying(stop_after_attempt(3), wait_random_exponential(0.5, 8), retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)) | retry_if_result(status in {429,502,503,504}), sleep=clock.sleep)` so retry waits run on the injected `Clock` (R27; direct `asyncio.sleep`/`time.time` in `src/pumpgrok` is forbidden by a static test); `RpcPool` rotates through `solana.rpc_urls` on repeated failure | Standardises the four retry loops the code base would otherwise copy (today `rpc_call()` is pasted three times, `tools/{authority_check,holder_check,priority_fee}.py`); `tenacity` is D5 | Retrying a *send* breaks the single-send rule (`rules/pumpgrok-team.mdc:30`); the exec adapter MUST use `stop_after_attempt(1)` and is unit-tested for it |
| 7 | Schema validation of untrusted payloads | pydantic v2 in gateway (`pyproject.toml:12`) and vendor models with `extra="allow"` (`models.py:29,66,78`) | pydantic v2 models with `extra="forbid"` for *our* contracts (`contracts/events/*.json` <-> the ledger event models in `src/pumpgrok/ledger/events.py`, R32) and `extra="ignore"` for *upstream* payloads (pump.fun, PumpPortal, Jupiter, RPC); every upstream parser returns `Result[Model, ParseError]` and never raises into the loop; LLM JSON output validated by `model_validate_json` with pessimistic fallback (vendor `GrokAgent.run` never raises, `agents/base.py:89`) | Upstream field names are heuristic today (scout-vendor-engine gap 7); `ignore` plus explicit `Field(validation_alias=...)` keeps the port tolerant while our own contracts stay strict | Silent drops on `ignore`; mitigated by a `parse_unknown_fields_total` counter per source |
| 8 | Recorded-fixture HTTP/WS testing | Vendor: `httpx.MockTransport` + `FakeWebSocket` + `FakeClock` across 264 tests (`vendor/grokbot-pumpfun/tests/`, e.g. `test_filter.py` monkeypatches `websockets.connect`) | `respx` for HTTP (route mocks + recorded JSON bodies under `tests/fixtures/http/<upstream>/*.json`); WS = in-process `FakeWebSocket` async iterator fed from `tests/fixtures/replay/<dataset>/ws_events.jsonl`; the same JSONL feeds `pumpgrok run --replay` | `respx` is D5 and removes the per-test `MockTransport` plumbing; one fixture format for tests and replay avoids two decoders | Recorded fixtures go stale; `pumpgrok doctor --refresh-fixtures` is NOT provided (would hit mainnet); refresh is a manual, reviewed PR |
| 9 | Lint / format | programming-desk: no formatter hooks on purpose (`.pre-commit-config.yaml:45-46`); Python skill mandates `ruff check` (`skills/platforms/python/SKILL.md:33`); vendor `ruff` `line-length = 100` (`vendor/.../pyproject.toml:47`) | `ruff` for both lint and format, `line-length = 100`, rule set in section 3.1; `ruff format --check` in CI; **no auto-format hook in pre-commit** (precedent rationale: reviewed artefact must equal committed artefact) | One tool, same line length as the vendor code being ported (fewer diff lines in characterization) | `ruff format` on the ported vendor code produces a large one-time diff; done in its own commit before any logic change |
| 10 | Typecheck | Skill: "`mypy --strict` on new modules" (`skills/platforms/python/SKILL.md:58`); vendor mypy non-strict (`pyproject.toml:62-69`) | `mypy --strict` on `src/pumpgrok` with `pydantic.mypy` plugin; `tests/`, `ci/`, `scripts/`, `vendor/` excluded; `warn_unreachable = true` (not implied by `--strict`, see section 2) | D5; the port is the one chance to type the vendor code properly | mypy 2.x defaults (`local_partial_types`, `strict_bytes`) will surface errors in ported code; budgeted in MIGRATION_NOTES |
| 11 | Test runner | `pytest` + `pytest-asyncio` `asyncio_mode = "auto"`, `testpaths = ["tests"]` (`services/desk-gateway/pyproject.toml:33-41`); root tests run with `python3 -m pytest tests/desk` and a `conftest.py` sys.path shim (`tests/conftest.py:1-9`); gate self-tests `python3 -m pytest ci/tests/ -v` (`.github/workflows/gates.yml:228`) | `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`), `testpaths = ["tests", "ci/tests"]`; no sys.path shim needed because the package is installed editable by `uv sync`; markers `replay`, `characterization` | Mirrors precedent; one invocation (`uv run pytest -q`) covers product and gate tests | `ci/tests` import `ci/gates/*.py` by path (precedent does the same); `--import-mode=importlib` not required but noted |
| 12 | Dependency vulnerability scan | `security-pr.yml:289-315` runs `pip-audit -r requirements*.txt` (no-op when none exist, comment at `:293-302` explains pip-audit cannot read a uv pyproject); Trivy fs scan HIGH+ (`:317-335`) | `uv export --frozen --no-dev --format requirements-txt > /tmp/req.txt && uv run pip-audit -r /tmp/req.txt --strict` as the `audit` Makefile target; Trivy fs kept in `security-pr.yml` | Gives pip-audit a requirements file derived from the lockfile, closing the gap the precedent documents | pip-audit fails on *any* advisory (precedent `:296-299`); use `--ignore-vuln <id>` only with a dated justification in `SECURITY.md` |
| 13 | Lockfile | Gateway commits `uv.lock`; build backend `uv_build>=0.11.26,<0.12.0` (`services/desk-gateway/pyproject.toml:28-30`); skill: "uv for dependency resolution and locking; commit uv.lock" (`SKILL.md:87`) | `uv` + committed `uv.lock`; build backend `uv_build` pinned to the current series (section 2); CI uses `uv sync --frozen` | Precedent; D5 | `uv` moves fast (0.13.3 released 2026-10-20); pin the installer action to a SHA and the `uv_build` series |
| 14 | Container + single-command start | programming-desk root has no Dockerfile; gateway deploys via systemd (`infra/desk-gateway/desk-gateway.service`, scout line 31); vendor Dockerfile/compose cited in section 0 | Multi-stage `Dockerfile` (builder: `uv sync --frozen --no-dev`; runtime: `python:3.12-slim`, non-root `pumpgrok`, `ENTRYPOINT ["pumpgrok"]`, `CMD ["run","--mode","paper"]`); `docker-compose.yml` single service `pumpgrok`, `./var:/app/var` volume, `env_file: .env`, health on `127.0.0.1:8080/healthz`; `make run-paper` and `docker compose up pumpgrok` are the two blessed starts | Vendor precedent is sound; multi-stage drops build tools from the runtime image; non-root and no baked secrets kept | Image carries no RPC key, so any key must come from `.env`/secret manager at run time (section 7) |
| 15 | Pre-commit hooks | `.pre-commit-config.yaml:70-172`: all `repo: local`; hooks `g3-committed-secrets` (every commit), `g1-ownership-manifest` (on `ownership.yaml`), `gate-self-test` (on `ci/(gates\|tests)/`), `preflight-self-test`, `g4-contract-preflight` (manual); explicit "no third-party hook repos, no auto-formatters" (`:40-46`); native alternative `ci/hooks/pre-commit` runs only `check_secrets.py --staged` | Same five local hooks verbatim, plus two more local hooks: `ruff-check` (`uv run ruff check --no-fix`, files `\.py$`) and `mypy-src` (`uv run mypy src/`, files `^src/`); still no third-party repos, still no formatter | Precedent plus the two checks the precedent repo lacked because it had no `src` package of its own at the time | `mypy` on every commit is slow (~10 s); acceptable because it is scoped to `src/` changes only |
| 16 | CI workflows | `gates.yml:25-29` on `pull_request`+`push` to main, self-hosted runner, trusted `ci/gates/` overlay from base ref (`:46-61`), bot from branch prefix anchored `^bot-0[0-6]-[a-z0-9-]+$` (`:79-85`), receipt selection by `branch` field (`:101-161`), G-1..G-7 steps, `gate-self-test` job (`:203-228`); `security-pr.yml` jobs gitleaks/semgrep/bandit/pip-audit+trivy with SARIF artifacts | Three workflows: `ci.yml` (ruff, ruff format --check, mypy, pytest, pip-audit; `push` + `pull_request`; `ubuntu-latest` **and** `[self-hosted, Linux, X64]` are both listed in section 3.7 with the self-hosted one commented, see Unverified U-3), `gates.yml` (mirror of precedent with seat regex `^bot-0[0-9]-[a-z0-9-]+$` and the **deviation** that a branch with no `bot-0N-` prefix is attributed to `bot-00-chief` instead of failing), `security-pr.yml` (gitleaks/semgrep/bandit/pip-audit/trivy, same structure) | Precedent is reviewed and battle-tested (Greptile P1 comments at `gates.yml:19-21`); the one deviation exists because today's branch is `feat/grokbot-desk-merge` and Hermes-driven commits land without seat prefixes | Default attribution weakens G-1 for prefix-less branches: chief owns only orchestration paths, so such a branch touching `src/` still fails G-1 (correct outcome); the risk is that chief-owned docs can be edited without a seat prefix |
| 17 | Prompt assembly | `scripts/assemble-prompts.sh [--roster] [--check]` substitutes `{{DEFAULT_BRANCH}} {{BOT_ID}} {{DESK_CHANNEL_ID}} {{SEAT_UUID:<SEAT>}} {{DESK_GATEWAY_URL}} {{DESK_ROSTER_VERSION}}` from `grokbot/rosters/<team>.json`; leftover `{{...}}` fatal; `generate-templates.py --check` (scout-programming-desk line 192) | Same two scripts, same placeholder set, roster at `grokbot/rosters/pumpgrok.json`; seats `CHIEF SCOUT RISK WHALE SNIPER RUG EXIT SHILL SIGNAL JOURNAL`; audiences `trading-seats\|chief\|risk`; `agents/<seat>.md` regenerated by `generate-templates.py` keeping today's frontmatter keys (`agents/chief.md` frontmatter `name,title,description,seat,skills,writes_to_exchange`, scout-pumpgrok-pack line 12) | D2 says copy names; the Hermes `agent_file:` pointers (`hermes/profiles.yaml:28`) keep working | Ten seats vs seven changes every seat regex in the gates (`SEAT_RE` in `check_desk_integrity.py:47`, `SEAT_ID_RE` in `check_receipt.py:57-61`, `gates.yml:81`) -- all three must be edited together |
| 18 | Receipts / gates | `.receipts/<bot>/<task>.json`, `REQUIRED_FIELDS = ["task_id","bot","commands","claims","unverified"]` (`ci/gates/check_receipt.py:48`), `BYPASS_PATTERNS` (`:26-46`), `run_all.py --bot --base --receipt [--change] [--strict]` (scout line 147), `.receipts/**/*.json` gitignored, `.gitkeep` tracked (scout line 42) | Identical schema and scripts, retargeted constants in section 4; `.receipts/bot-00-chief ... bot-09-journal/.gitkeep`; receipts for paper fills cite a ledger query command (`pumpgrok state status --json`) as evidence | Precedent is the whole point of D2 | None beyond the regex fan-out noted in row 17 |

## 2. Pinned versions

Evidence: `curl -s https://pypi.org/pypi/<pkg>/json` run 2026-10-20 from this host; `version` =
`info.version`, date = max `upload_time` of that release's files, `requires_python` =
`info.requires_python`. All fourteen queries returned (online), plus four supporting packages.

| Package | Pin (pyproject) | Latest on PyPI | Released | requires_python | Justification |
|---|---|---|---|---|---|
| pydantic | `>=2.14.1,<3` | 2.14.1 | 2026-10-11 | >=3.10 | v2 API used by vendor (`models.py:19`); `<3` guards the next major |
| pydantic-settings | `>=2.16.0,<3` | 2.16.0 | 2026-10-14 | >=3.11 | TOML + env sources; same major as pydantic |
| httpx | `>=0.28.1,<0.29` | 0.28.1 | 2024-12-06 | >=3.8 | Same floor as gateway (`services/desk-gateway/pyproject.toml:10`); 0.28 removed deprecated `proxies=`/`app=` kwargs, so `<0.29` holds the API |
| respx | `>=0.23.1,<0.24` | 0.23.1 | 2026-04-08 | >=3.8 | httpx 0.28-compatible mock router; dev only |
| websockets | `>=17.3,<18` | 17.3 | 2026-10-19 | >=3.11 | New asyncio implementation is default since 14.0; 17.x keeps `websockets.asyncio.client.connect`; see MIGRATION_NOTES M-1 |
| tenacity | `>=9.2.1,<10` | 9.2.1 | 2026-10-07 | >=3.10 | `AsyncRetrying` + `wait_random_exponential`; 9.x is the current major |
| prometheus_client | `>=0.26.0,<0.27` | 0.26.0 | 2026-07-24 | >=3.9 | Reference exposition format; pre-1.0 so minor is pinned |
| pyyaml | `>=6.0.3,<7` | 6.0.3 | 2025-09-29 | >=3.8 | Gate scripts and rosters are YAML (`check_desk_integrity.py:87-96`); gateway floor `>=6.0` (`pyproject.toml:17`) |
| ruff | `>=0.17.1,<0.18` | 0.17.1 | 2026-10-15 | >=3.7 | Lint + format; minor pinned because rule sets change per minor |
| mypy | `>=2.4.0,<3` | 2.4.0 | 2026-10-01 | >=3.10 | 2.x line (2.0 released 2026-05-06); see MIGRATION_NOTES M-4 |
| pytest | `>=9.1.1,<10` | 9.1.1 | 2026-06-19 | >=3.10 | Gateway floor `>=8.0` (`pyproject.toml:35`); 9.x current |
| pytest-asyncio | `>=1.4.0,<2` | 1.4.0 | 2026-05-26 | >=3.10 | Gateway floor `>=1.0` (`pyproject.toml:36`); 1.x removed the `event_loop` fixture, see M-5 |
| pip-audit | `>=2.10.1,<3` | 2.10.1 | 2026-06-10 | >=3.10 | Dev group; invoked against `uv export` output |
| uv | `>=0.13.3` (installer, not a Python dep) | 0.13.3 | 2026-10-20 | >=3.8 | Precedent tool (`SKILL.md:87`); CI pins `astral-sh/setup-uv` by SHA, see U-4 |
| uv_build | `>=0.13.3,<0.14.0` | 0.13.3 | 2026-10-20 | -- | Build backend; precedent pins a series (`services/desk-gateway/pyproject.toml:29`) |
| types-PyYAML | `>=6.0.12.20260906` | 6.0.12.20260906 | 2026-09-06 | -- | Stubs for `mypy --strict` on YAML-reading code |
| pytest-cov | not added | 7.1.0 | 2026-03-21 | -- | Vendor uses it (`pyproject.toml:25`) but no coverage threshold exists; added only when a threshold is agreed (U-5) |
| hypothesis | not added | 6.170.5 | 2026-10-20 | -- | Candidate for parser fuzzing (scout-vendor-engine gap 11); deferred |

Python: `requires-python = ">=3.12,<3.13"` (D1; precedent CI uses 3.12, `gates.yml:65`).

## 3. Repository file drafts

Every block below is a draft to be materialised by the implementation wave. Nothing here is
written to the repo by this node except this document.

### 3.1 pyproject.toml

Validated: the exact text below was written to a temporary file
(`/tmp/tmpzr0bqey6/pyproject.toml`, outside the repo) and parsed with
`python3 -c "import tomllib; tomllib.load(open(p,'rb'))"`; result: valid TOML, tables
`build-system`, `dependency-groups`, `project`, `tool`; `project.scripts == {"pumpgrok": "pumpgrok.cli:main"}`.

```toml
[project]
name = "pumpgrok"
version = "0.1.0"
description = "PumpGrok: autonomously supervised, paper-trading-by-default Solana memecoin desk (pump.fun / Jupiter / Solana RPC / x.ai Grok)"
readme = "README.md"
requires-python = ">=3.12,<3.13"
license = { text = "AGPL-3.0-only" }
authors = [{ name = "Spectrum Web Co LLC" }]
dependencies = [
    "pydantic>=2.14.1,<3",
    "pydantic-settings>=2.16.0,<3",
    "httpx>=0.28.1,<0.29",
    "websockets>=17.3,<18",
    "tenacity>=9.2.1,<10",
    "prometheus-client>=0.26.0,<0.27",
    "pyyaml>=6.0.3,<7",
]

[project.scripts]
pumpgrok = "pumpgrok.cli:main"

[project.urls]
Repository = "https://github.com/swcstudio/pumpgrok"

[build-system]
requires = ["uv_build>=0.13.3,<0.14.0"]
build-backend = "uv_build"

[tool.uv.build-backend]
module-name = "pumpgrok"
module-root = "src"

[dependency-groups]
dev = [
    "respx>=0.23.1,<0.24",
    "ruff>=0.17.1,<0.18",
    "mypy>=2.4.0,<3",
    "pytest>=9.1.1,<10",
    "pytest-asyncio>=1.4.0,<2",
    "pip-audit>=2.10.1,<3",
    "types-PyYAML>=6.0.12.20260906",
]

[tool.ruff]
line-length = 100
target-version = "py312"
src = ["src", "tests", "ci"]
extend-exclude = ["vendor", "prompts-assembled", "var"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "ASYNC", "C4", "SIM", "RUF", "S", "T20", "PL"]
ignore = [
    "PLR0913",  # many-argument constructors on pydantic settings models
    "PLR2004",  # magic values are named constants in risk/ already; tests compare literals
    "S101",     # assert is the pytest idiom; bandit still runs in security-pr.yml
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S", "T20", "PLR"]
"ci/**" = ["T20", "S603", "S607"]
"scripts/**" = ["T20"]

[tool.ruff.lint.isort]
known-first-party = ["pumpgrok"]

[tool.ruff.format]
quote-style = "double"
docstring-code-format = true

[tool.mypy]
python_version = "3.12"
strict = true
warn_unreachable = true
packages = ["pumpgrok"]
mypy_path = "src"
plugins = ["pydantic.mypy"]
exclude = ["^vendor/", "^tests/", "^ci/", "^scripts/"]

[[tool.mypy.overrides]]
module = ["prometheus_client.*", "respx.*"]
ignore_missing_imports = true

[tool.pydantic-mypy]
init_forbid_extra = true
init_typed = true
warn_required_dynamic_aliases = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests", "ci/tests"]
addopts = "-q --strict-markers"
markers = [
    "replay: runs against tests/fixtures/replay/<dataset>",
    "characterization: pins vendor behaviour during the port",
]
filterwarnings = ["error::DeprecationWarning:pumpgrok.*"]
```

Notes on the draft:
- `T20` (no `print`) is on for `src/`; the CLI emits through `pumpgrok.cli.emit()` which writes
  JSON to stdout, keeping today's `print(json.dumps(...))` contract (`tools/*.py`) in one place.
- `S` (bandit-equivalent) runs in ruff as well as in `security-pr.yml`; duplicates are cheap.
- `license` is `AGPL-3.0-only` per `LICENSE:1-4` (AGPL v3) -- the four plugin manifests that say
  `MIT` are corrected by node n2 (D2 says "license corrected to AGPL-3.0").

uv.lock generation (run once, commit the result; CI never regenerates):

```
uv lock
uv sync --frozen --group dev
```

### 3.2 Makefile

```make
.PHONY: help sync lint fmt typecheck test audit run-paper replay report gates prompts check doctor clean

UV ?= uv
BOT ?= bot-00-chief
TASK ?= $(error TASK=<task-id> is required for gates)
REPLAY ?= tests/fixtures/replay/smoke

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | column -t -s "$$(printf '\t')"

sync:            ## install locked deps incl. dev group
	$(UV) sync --frozen --group dev

lint: sync       ## ruff lint + format check
	$(UV) run ruff check .
	$(UV) run ruff format --check .

fmt: sync        ## ruff format (writes files; never run by a hook)
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck: sync  ## mypy --strict on src/
	$(UV) run mypy src/

test: sync       ## pytest (product + gate self-tests)
	$(UV) run pytest -q

audit: sync      ## pip-audit against the lockfile
	$(UV) export --frozen --no-dev --format requirements-txt --no-hashes -o /tmp/pumpgrok-req.txt
	$(UV) run pip-audit -r /tmp/pumpgrok-req.txt --strict

run-paper: sync  ## start the paper desk (foreground)
	$(UV) run pumpgrok run --mode paper

replay: sync     ## one cycle against a recorded dataset
	$(UV) run pumpgrok run --mode paper --once --replay $(REPLAY)

report: sync     ## daily report from the ledger
	$(UV) run pumpgrok report --daily

doctor: sync     ## effective config, data sources, ledger, killswitch
	$(UV) run pumpgrok doctor

gates:           ## G-1..G-7 for BOT/TASK (stdlib + pyyaml only, like CI)
	python3 ci/gates/run_all.py --bot $(BOT) --base origin/main --receipt .receipts/$(BOT)/$(TASK).json

prompts:         ## assemble prompts and regenerate agent templates
	bash scripts/assemble-prompts.sh
	python3 scripts/generate-templates.py

check: lint typecheck test audit  ## everything ci.yml runs
	bash scripts/assemble-prompts.sh --check
	python3 scripts/generate-templates.py --check
	./scripts/check.sh

clean:           ## caches only; never var/
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find src tests ci -name __pycache__ -type d -prune -exec rm -rf {} +
```

`clean` deliberately does not match G-6's `rm -rf` pattern on `var/` (ledger); `var/` is never
removed by a Makefile target.

### 3.3 Dockerfile

```dockerfile
# No secrets in the image; everything arrives as PUMPGROK_* env at run time.
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.3 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    PUMPGROK_PROFILE=paper \
    PUMPGROK_VAR_DIR=/app/var
RUN useradd --system --create-home --home-dir /home/pumpgrok pumpgrok \
 && mkdir -p /app/var && chown -R pumpgrok:pumpgrok /app
COPY --from=builder --chown=pumpgrok:pumpgrok /opt/venv /opt/venv
# Profile overlays ship inside the installed package (src/pumpgrok/config/overlays/, R30);
# an operator overlay, if any, is mounted under /app/var and named via PUMPGROK_CONFIG.
COPY --chown=pumpgrok:pumpgrok prompts-assembled/ /app/prompts-assembled/
WORKDIR /app
VOLUME ["/app/var"]
USER pumpgrok
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,sys,urllib.request; p=os.environ.get('PUMPGROK_HEALTH_PORT','8080'); sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{p}/healthz',timeout=3).status==200 else 1)"
STOPSIGNAL SIGTERM
ENTRYPOINT ["pumpgrok"]
CMD ["run", "--mode", "paper"]
```

Deviation from vendor (`vendor/grokbot-pumpfun/Dockerfile:17-22`): multi-stage, lockfile-driven,
no `pip`, no `requirements.txt`. Kept: non-root user, volume for state, healthcheck on `/healthz`,
SIGTERM. `--mode live` inside a container is refused by the live gate (D4) regardless of CMD.

### 3.4 docker-compose.yml

```yaml
services:
  pumpgrok:
    build: .
    image: pumpgrok:local
    container_name: pumpgrok
    restart: unless-stopped
    stop_grace_period: 45s          # > supervisor.shutdown_grace_seconds
    env_file: .env                  # PUMPGROK_* only; never a wallet key (see .env.example)
    environment:
      PUMPGROK_PROFILE: "${PUMPGROK_PROFILE:-paper}"
      PUMPGROK_HEALTH_PORT: "8080"
    command: ["run", "--mode", "paper"]
    ports:
      - "127.0.0.1:8080:8080"       # /healthz and /metrics stay loopback
    volumes:
      - ./var:/app/var              # ledger.sqlite, snapshots, journal, KILLSWITCH, health
    logging:
      driver: json-file
      options:
        max-size: "20m"
        max-file: "5"
    deploy:
      resources:
        limits:
          memory: 512M
```

### 3.5 .env.example

Placeholders only. Secret-shaped values are intentionally absent so G-3 and gitleaks pass on
this file; `.env` itself is in `ALWAYS_FLAG_FILES` (`ci/gates/check_secrets.py:77`) and must
never be committed.

```
# Copy to .env (gitignored). Every key is read by pydantic-settings with prefix PUMPGROK_.
# Nested keys use double underscore: PUMPGROK_SOLANA__RPC_URLS maps to solana.rpc_urls.

PUMPGROK_PROFILE=paper                      # dev | paper | live ; selects src/pumpgrok/config/overlays/<profile>.toml (R30)
PUMPGROK_CONFIG=                            # optional operator overlay TOML applied last; empty = none
PUMPGROK_MODE=paper                         # paper | live ; precedence CLI --mode > PUMPGROK_MODE > TOML execution.mode (R30)
PUMPGROK_VAR_DIR=./var
PUMPGROK_LOG_LEVEL=INFO
PUMPGROK_LOG_JSON=true
PUMPGROK_HEALTH_PORT=8080

# Data sources (D8: nothing added, nothing dropped)
PUMPGROK_DATA__REST_URL=https://frontend-api.pump.fun
PUMPGROK_DATA__WS_URL=wss://pumpportal.fun/api/data
PUMPGROK_DATA__API_KEY=<pumpportal-key-or-empty>
PUMPGROK_JUPITER__QUOTE_URL=https://lite-api.jup.ag/swap/v1/quote
PUMPGROK_SOLANA__RPC_URLS=https://api.mainnet-beta.solana.com,<second-rpc-url-without-key>
PUMPGROK_SOLANA__RPC_API_KEY=<provider-key-or-empty>   # sent as a header, never embedded in the URL

# LLM (x.ai Grok via httpx; failure degrades to rule-based)
PUMPGROK_GROK__API_KEY=<xai-key>
PUMPGROK_GROK__BASE_URL=https://api.x.ai/v1/chat/completions
PUMPGROK_GROK__FAST_MODEL=grok-4-fast
PUMPGROK_GROK__CHECKER_MODEL=grok-4

# Alerts (stdout + file sinks are always on)
PUMPGROK_ALERTS__TELEGRAM_BOT_TOKEN=<telegram-token-or-empty>
PUMPGROK_ALERTS__TELEGRAM_CHAT_ID=<chat-id-or-empty>   # the ONLY Telegram destination notify.alert may send to (allowlist, R39)
PUMPGROK_ALERTS__WEBHOOK_URL=<https-url-or-empty>      # the ONLY webhook destination (allowlist, R39)

# Kill switch. PUMPGROK_KILLSWITCH is read ONCE at start (R22); the live sources polled every
# cycle are the file var/KILLSWITCH and the alert-channel command. Clear is CLI-only:
# `pumpgrok killswitch clear --by <human> --reason <text>`.
PUMPGROK_KILLSWITCH=false

# Live gate (R21: nine preconditions, ALL required for effective mode live; startup prints every
# unmet one and exits 3). (1) effective mode live, (2) PUMPGROK_LIVE_ENABLE=1, (3) min paper days on
# source=paper ledger events, (4) performance thresholds on the same events, (5) non-empty public
# address allowlist, (6) 0 < notional cap <= 1.0 SOL, (7) HMAC-signed confirmation record from
# `pumpgrok live confirm`, (8) adapter named AND registered (none ships -> always unmet),
# (9) no active kill switch, halt or open breaker.
PUMPGROK_LIVE_ENABLE=0
PUMPGROK_LIVE__MIN_PAPER_DAYS=14
PUMPGROK_LIVE__WALLET_ALLOWLIST=            # comma-separated PUBLIC addresses; empty = live refused
PUMPGROK_LIVE__NOTIONAL_CAP_SOL=0
PUMPGROK_LIVE__CONFIRMATION_RECORD=         # path to the HMAC-signed human confirmation JSON (pumpgrok live confirm)
PUMPGROK_LIVE__ADAPTER=                     # must name a registered adapter; none ships in this build

# FORBIDDEN: the loader refuses to start if any of these names is present in the environment,
# with or without the PUMPGROK_ prefix (mirrors hermes/profiles.yaml forbidden_env_keys).
#   PRIVATE_KEY  SECRET_KEY  SEED  MNEMONIC  PHANTOM  WALLET_SECRET
#   WALLET_PRIVATE_KEY  KEYPAIR  SOLANA_PRIVATE_KEY
```

The last three names extend the Hermes list (`hermes/profiles.yaml:18-24`) with the vendor's
own `GROKBOT_WALLET_PRIVATE_KEY` shape (`vendor/.../models.py:406`) and the common
`KEYPAIR`/`SOLANA_PRIVATE_KEY` names; the loader check is substring, case-insensitive.

### 3.6 .pre-commit-config.yaml and .gitignore

`.pre-commit-config.yaml` (local hooks only, mirroring `programming-desk/.pre-commit-config.yaml:70-172`):

```yaml
minimum_pre_commit_version: "3.2.0"
default_install_hook_types: [pre-commit]
default_stages: [pre-commit]
fail_fast: false

repos:
  - repo: local
    hooks:
      - id: g3-committed-secrets
        name: "G-3 - committed secrets"
        entry: python3 ci/gates/check_secrets.py --files
        language: system
        types: [file]
        pass_filenames: true
      - id: g1-ownership-manifest
        name: "G-1 - ownership manifest self-check"
        entry: python3 ci/gates/check_ownership.py --validate-manifest
        language: python
        additional_dependencies: ["pyyaml"]
        files: ^ownership\.yaml$
        pass_filenames: false
      - id: gate-self-test
        name: "Gate self-test (ci/tests)"
        entry: python3 -m pytest ci/tests -q
        language: python
        additional_dependencies: ["pytest", "pyyaml"]
        files: ^ci/(gates|tests)/
        pass_filenames: false
      - id: ruff-check
        name: "ruff check (no fix)"
        entry: uv run ruff check --no-fix
        language: system
        types: [python]
        pass_filenames: true
      - id: mypy-src
        name: "mypy --strict src/"
        entry: uv run mypy src/
        language: system
        files: ^src/
        pass_filenames: false
      - id: g4-contract-preflight
        name: "G-4 - contract-first pre-flight (advisory)"
        entry: ci/hooks/g4-preflight.sh
        language: python
        additional_dependencies: ["pyyaml"]
        files: ^(contracts/|openapi\.yaml$)
        pass_filenames: true
        stages: [manual]
```

No auto-formatter hook (precedent `:45-46`); no third-party `repo:` (precedent `:40-42`).

`.gitignore` (precedent verbatim, scout-programming-desk line 42, plus desk runtime state):

```
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
__pycache__/
*.pyc
*.egg-info/
dist/
build/
.env
.receipts/**/*.json
!.receipts/**/.gitkeep
var/
!var/.gitkeep
prompts-assembled/*.xml.tmp
```

The six tracked `.pyc` files (section 0) must be `git rm --cached` in the same change that adds
this file, or `*.pyc` has no effect on them.

### 3.7 GitHub workflows

`ci.yml` (new; precedent repo has no equivalent because its product code is the gateway package):

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
permissions:
  contents: read
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
jobs:
  check:
    runs-on: ubuntu-latest           # see Unverified U-3; precedent uses [self-hosted, Linux, X64]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@<pin-by-sha>   # U-4
        with:
          version: "0.13.3"
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: uv sync --frozen --group dev
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src/
      - run: uv run pytest -q
      - run: uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
      - run: uv run pumpgrok doctor
      - name: pip-audit against the lockfile
        run: |
          uv export --frozen --no-dev --format requirements-txt --no-hashes -o req.txt
          uv run pip-audit -r req.txt --strict
      - run: bash scripts/assemble-prompts.sh --check
      - run: python3 scripts/generate-templates.py --check
      - run: ./scripts/check.sh
```

`gates.yml`: copy `programming-desk/.github/workflows/gates.yml` lines 23-228 with exactly these
edits:

| Line (precedent) | Precedent text | pumpgrok text | Why |
|---|---|---|---|
| 81 | `if [[ ! "$BOT" =~ ^bot-0[0-6]-[a-z0-9-]+$ ]]; then ... exit 1` | `if [[ ! "$BOT" =~ ^bot-0[0-9]-[a-z0-9-]+$ ]]; then BOT=bot-00-chief; echo "::warning::no seat prefix on '$BRANCH'; attributing to bot-00-chief"; fi` | **Deviation**: ten seats; prefix-less branches default to the chief seat instead of failing. Rationale and risk in table row 16 |
| 68, 226 | `pip install pyyaml` / `pip install pyyaml pytest` | unchanged | gates stay stdlib + pyyaml so they run without `uv` |
| 201 | `python3 ci/gates/check_desk_integrity.py --repo .` | unchanged | G-7 retargeted inside the script, not the workflow |
| 46-61, 208-221 | trusted `ci/gates/` overlay from base ref | unchanged | keeps the self-hosted-runner trust model |

`security-pr.yml`: copy `programming-desk/.github/workflows/security-pr.yml` with these edits:
the `pip-audit` step (`:303-315`) scans `uv export` output instead of globbing
`requirements*.txt`; the gitleaks config `ci/security/gitleaks.toml` gains the Solana/Telegram/xai
rules from section 4 (G-3); bandit and semgrep steps unchanged; Trivy fs unchanged
(`severity: HIGH,CRITICAL`, `exit-code: "1"`, `:334-335`).

## 4. Gate retargeting for a trading desk

Scripts keep their names and CLI (`ci/gates/{check_ownership,check_receipt,check_secrets,check_contracts,check_rollback,check_desk_integrity,run_all}.py`). Only the constants below change; `ci/tests/test_gates.py` gains one test per new constant.

| Gate | Precedent constant (file:line) | pumpgrok value |
|---|---|---|
| G-1 | `check_ownership.py:36-58 _match`, last-match-wins, unowned = fail | unchanged logic plus one new self-test: every path in `git ls-files` resolves to exactly one owner (R36). `ownership.yaml` seats `bot-00-chief..bot-09-journal`; `bot-02-risk` owns `ci/**`, `contracts/**`, `ownership.yaml`, `SECURITY.md`, `rules/pumpgrok-team.mdc`, `.gitignore`, `docs/RISK_POLICY.md`, `docs/SAFETY_INVARIANTS.md`, `src/pumpgrok/{core,replay,ledger,config,logging,risk}/**` and, by a rule placed AFTER `src/pumpgrok/execution/**`, `src/pumpgrok/execution/live/**` (R31); `bot-04-sniper` owns `src/pumpgrok/execution/**`; `bot-06-exit` owns `src/pumpgrok/engine/exits.py`; `bot-05-rug` owns `src/pumpgrok/engine/watcher.py`, `tools/safety/**` and the `tools/onchain/**` directory (incl. `rpc.py`, `authorities.py`); `bot-03-whale` owns `tools/onchain/{holders,transfers}.py` by a later rule; `bot-09-journal` owns `src/pumpgrok/reporting/**` and `skills/desk-post-trade-review/**`; `bot-08-signal` owns `src/pumpgrok/engine/**` (scoring, checker, agents); `bot-01-scout` owns `src/pumpgrok/engine/{monitor,analyzer}.py` and `tools/market/**`; `bot-07-shill` owns `tools/social/**`; `bot-00-chief` owns the generated `agents/*.md` and `prompts-assembled/*`; characterization tests follow the owner of the module they pin. The full rule list is `docs/ROSTER.md` section 7 |
| G-2 | `REQUIRED_FIELDS = ["task_id","bot","commands","claims","unverified"]` (`check_receipt.py:48`); `BYPASS_PATTERNS` (`:26-46`); `SEAT_ID_RE` (`:57-61`) | `REQUIRED_FIELDS` verbatim; `BYPASS_PATTERNS` kept and extended with `(r"PUMPGROK_LIVE_ENABLE=(?:1\|true)", "sets the live flag inline")` and `(r"--i-understand-the-risk", "vendor live bypass flag")`; `SEAT_ID_RE` alternation becomes `bot-0[0-9](?:-[a-z0-9-]+)?\|CHIEF\|SCOUT\|RISK\|WHALE\|SNIPER\|RUG\|EXIT\|SHILL\|SIGNAL\|JOURNAL\|the desk\|desk-[a-z][a-z0-9-]*` |
| G-3 | `PATTERNS` 17 families (`check_secrets.py:29-51`); `SECRET_NAME_RE` (`:56-60`); `ALWAYS_FLAG_FILES` (`:77`) | Append: `("solana_base58_key", r"\b[1-9A-HJ-NP-Za-km-z]{86,88}\b", "Solana 64-byte secret key, base58")`; `("solana_json_keypair", r"\[\s*(?:\d{1,3}\s*,\s*){63}\d{1,3}\s*\]", "Solana keypair as JSON byte array")`; `("helius_url_key", r"(?i)helius(?:-rpc)?\.com/[^\s\"']*api-key=[A-Za-z0-9-]{20,}", "Helius RPC URL with key")`; `("quicknode_url", r"(?i)[a-z0-9-]+\.solana-mainnet\.quiknode\.pro/[A-Za-z0-9]{20,}", "QuickNode endpoint with token")`; `("telegram_bot_token", r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b", "Telegram bot token")`; `("xai_key", r"\bxai-[A-Za-z0-9]{32,}\b", "x.ai API key")`. `SECRET_NAME_RE` gains `\|keypair\|mnemonic\|seed[_-]?phrase\|wallet[_-]?secret`. `ALWAYS_FLAG_FILES` gains `id.json`, `keypair.json`, `wallet.json`. `SKIP_DIRS` keeps `vendor` (`:70-71`) but `vendor/grokbot-pumpfun/.env.example` is scanned explicitly by `--files` in the gate self-test |
| G-4 | `contract_surface: true` + `contract_consumers` in ownership.yaml; change doc fields incl. mandatory `semantic_changes` (scout line 254) | unchanged logic; surfaces = `contracts/events/**` (one `<snake_case>.schema.json` per ledger event type of R32, e.g. `order_placed`, `fill_recorded`, `position_closed`, `halt_set`, `escalation`, `journal_note`; seat messages such as signals, safety reports and verdicts are `journal_note` payloads discriminated by `note_kind`, per `docs/TOOL_CATALOG.md`), `contracts/tool-rosters/**`, `openapi.yaml`; consumers per D3 flow (signal notes: scout->risk,signal,sniper; verdict notes: rug->sniper,exit; order/fill: sniper,exit->journal,chief,risk) |
| G-5 | `DEPLOY_PATTERNS` (`check_rollback.py:47-56`): vercel/terraform/kubectl/helm/fastlane/gcloud/aws | Replace with: `r"\bpumpgrok\s+run\b.*--mode\s+live\b"`, `r"\bpumpgrok\s+(?:go-live\|promote)\b"`, `r"\bPUMPGROK_LIVE_ENABLE=(?:1\|true)\b"`, `r"\bPUMPGROK_MODE=live\b"`, `r"\bdocker\s+compose\s+up\b.*live"`, `r"\bsystemctl\s+(?:start\|restart\|enable)\s+pumpgrok"`. `PLAN_MIN_WORDS = 12` and `PLAN_SIGNALS` (`:61-70`) unchanged; `PLAN_SIGNALS[0]` gains `\|\bpumpgrok\b\|\bkillswitch\b` so "run `pumpgrok killswitch set`" counts as naming the command |
| G-6 | `DESTRUCTIVE_PATTERNS` (`check_rollback.py:25-45`) infra/data/git/fs; `REQUIRED_APPROVAL_FIELDS = ["operation","approved_by","at","blast_radius"]` (`:58`) | Keep the git/fs/data rows (`:32-38`, `:43-44`); drop the terraform/kubectl/helm/aws rows (no such infra); add `("trade", ...)` category: `r"\bexec\.place\b.*live"`, `r"\bpumpgrok\s+live[-_ ]trade\b"`, `r"\bpumpgrok\s+live\s+confirm\b"`, `r"\bwallet[-_ ]transfer\b"`, `r"\bsend[-_ ]transaction\b"`, `r"\bpumpgrok\s+risk\s+raise-limit\b"`, `r"\bpumpgrok\s+killswitch\s+clear\b"`, `r"\bpumpgrok\s+state\s+halt\b.*--clear\b"` (R22 verb; there is no `unhalt`/`clear-halt`), `r"\brm\s+(?:-f\s+)?var/KILLSWITCH\b"`, `r"\bDELETE\s+FROM\s+events\b"`, `r"\bsqlite3\b.*var/ledger\.sqlite"`. `REQUIRED_APPROVAL_FIELDS` verbatim; `blast_radius` for trade category must parse as `max_notional_sol=<float>` (new check) |
| G-7 | `ROSTER_MIN_TOOLS = 10`, `ROSTER_MAX_TOOLS = 15` (`check_desk_integrity.py:41-42`); `TOOL_NAME_RE = ^[a-z][a-z0-9_]{2,60}$` (`:46`); `SEAT_RE = ^bot-0[0-6]-[a-z-]+$` (`:47`); `GATE_REQUIRED_FIELDS g5: [rollback_plan, approval_id], g6: [approval_id]` (`:55-58`); `UUID_RE`, `PLACEHOLDER_RE` (`:49-50`); `TEMPLATE_FORBIDDEN` (`:66-77`); `ASSEMBLED_ALIASES` (`:62`) | `ROSTER_MIN_TOOLS = 8`, `ROSTER_MAX_TOOLS = 15`, inclusive (R19; core eight alone is a valid minimum for DM seats); `TOOL_NAME_RE = ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$` (R19: dotted `<ns>.<verb>` is the only identifier in catalog, roster YAML `name`, registry, tests and ownership; the gateway transport name `ns_verb` is derived at exposure time and never stored); `SEAT_RE = ^bot-0[0-9]-[a-z-]+$`; `GATE_REQUIRED_FIELDS` verbatim; new rule: any tool with `kind: write` MUST carry `gates: [g6]` and an input schema requiring `approval_id` and `rollback_plan` (so paper-write tools on sniper/exit are G-6 tools); new rule: no roster may reference a tool whose name starts with `exec.live` (D3 "NO seat can resolve a live-write tool"); `ASSEMBLED_ALIASES = [CHIEF, SCOUT, RISK, WHALE, SNIPER, RUG, EXIT, SHILL, SIGNAL, JOURNAL]`; `TEMPLATE_FORBIDDEN` keeps `:67-71,75` and replaces the tailnet/railway rows with the six G-3 trading shapes above plus `(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b(?=.*(?:mint\|wallet))", "literal Solana address in a template")` [INFERENCE: lookahead form needs a test; a plain address regex would also hit base58 example mints in docs] |

Receipt schema: fields reused verbatim from `prompts/_shared/core-directives.xml:119-150` and
`check_receipt.py:48` (`task_id, bot, branch, started_at, completed_at, commands[], claims[],
unverified[], files_changed[], contract_changes[], rollback_plan, approvals[], loop_acks[],
approved_by, approval_requested_from, approval_note, quality_gates{}`). Trading-specific claim
examples:

```json
{
  "task_id": "SOL-20261020-003-paper-fill",
  "bot": "bot-04-sniper",
  "branch": "bot-04-sniper/paper-fill-SOL-20261020-003",
  "commands": [
    {"cmd": "uv run pumpgrok paper buy --ticket SOL-20261020-003 --mint <mint> --size-sol 0.2 --slippage-bps 100 --approval-id apr_01J...", "exit_code": 0, "duration_s": 1.2, "output_tail": "{\"ok\": true, \"mode\": \"paper\", \"fill_id\": \"fill_01J...\"}"},
    {"cmd": "uv run pumpgrok state status --json", "exit_code": 0, "duration_s": 0.3, "output_tail": "\"open_positions\": 1, \"daily_pnl_sol\": -0.004"},
    {"cmd": "uv run pytest -q tests/execution/test_paper_adapter.py", "exit_code": 0, "duration_s": 2.1, "output_tail": "14 passed"}
  ],
  "claims": [
    {"claim": "Paper fill for SOL-20261020-003 recorded in the ledger with mode=paper", "evidence_command_index": 1},
    {"claim": "Single-send: adapter uses stop_after_attempt(1); retry test passes", "evidence_command_index": 2}
  ],
  "unverified": ["Slippage model vs real pump.fun curve impact: paper-only estimate"],
  "approvals": [
    {"operation": "exec.place (paper, g6)", "approved_by": "human:operator", "at": "2026-10-20T09:41:00Z", "blast_radius": "max_notional_sol=0.2"}
  ],
  "rollback_plan": "Run `pumpgrok paper sell --ticket SOL-20261020-003 --mint <mint> --size-sol 0.2 --slippage-bps 100 --approval-id apr_01J...` (a sell is a new decision with its own approval, R23); recovery immediate (seconds); ledger keeps both events, no data loss.",
  "approved_by": "bot-02-risk",
  "quality_gates": {"G-1": "passed", "G-2": "passed", "G-3": "passed", "G-6": "passed", "G-7": "passed"}
}
```

## 5. Logging, correlation, metrics, spans

### 5.1 JSON log record

Formatter: `src/pumpgrok/logging/json.py` `JsonFormatter(logging.Formatter)`; one object per line,
`separators=(",", ":")`, `sort_keys=True` (same canonical form as `audit_tracer.py:27-30`).

| Field | Type | Source |
|---|---|---|
| `ts` | RFC 3339 UTC, ms | `record.created` |
| `level` | `DEBUG..CRITICAL` | `record.levelname` |
| `logger` | dotted module | `record.name` |
| `msg` | str | `record.getMessage()` |
| `event` | str, snake_case | `extra={"event": ...}`; required for anything the ledger will mirror (`signal_emitted`, `verdict`, `order_placed`, `fill`, `breaker_tripped`, `killswitch`, `halt`, `span`) |
| `correlation_id` | `cid_<ulid>` | `contextvars` `CID` |
| `seat` | `bot-0N-<seat>` | `contextvars` `SEAT` |
| `ticket_id` | `SOL-YYYYMMDD-NNN` or null | `contextvars` `TICKET` |
| `mint` | base58 or null | `extra` |
| `mode` | `paper\|live` | settings, stamped once per process (vendor stamps `mode` on every JSONL record, `log.py:93-101`) |
| `profile` | `dev\|paper\|live` | settings |
| `duration_ms` | float or absent | spans only |
| `exc` | `{type, msg, stack}` or absent | `record.exc_info` |
| `data` | object | remaining `extra` keys after redaction |

### 5.2 Correlation ID lifecycle

```
signal  -> decision -> order -> fill -> exit -> journal
  |          |          |        |       |        |
  cid created by scout/engine at first sight of a mint (one per mint per UTC day)
             |          |        |       |        |
             risk verdict, signal score, chief ticket all log with the same cid
                        |        |       |        |
                        order_id = ord_<ulid>, carries cid + ticket_id
                                 |       |        |
                                 fill_id = fill_<ulid>, carries order_id + cid
                                         |        |
                                         exit order/fill reuse the cid; new order_id/fill_id
                                                  |
                                                  journal row keyed by cid; report groups by cid
```

Rules: a cid is set with `with correlation(cid):` at the top of each supervisor task iteration
and never reassigned inside; cross-task hand-off passes the cid inside the event payload
(`contracts/events/*.json` all carry `correlation_id`); the ledger `events` table indexes
`correlation_id`.

### 5.3 Redaction filter

`RedactionFilter(logging.Filter)` applied to every handler before formatting:

- Key-based: any key in `data`/`extra` matching `check_secrets.py:56-60 SECRET_NAME_RE` plus
  `keypair|mnemonic|seed|wallet_secret|chat_id` -> value replaced by `"[redacted]"`.
- Value-based: the six G-3 trading regexes from section 4 and the precedent `private_key`, `jwt`,
  `conn_string` families (`check_secrets.py:41-46`) applied to the rendered `msg` and to every
  string leaf in `data`; matched spans replaced by first 4 chars + `*` (same `_redact` as
  `check_secrets.py:123-126`).
- `SecretStr` never reaches the formatter (pydantic prints `**********`), but the filter is still
  the last line because `str(exc)` can embed a URL with a key.
- Tested by `tests/logging/test_redaction.py` with the G-3 fixtures.

### 5.4 Destinations

| Sink | Always on | Format | Path / target |
|---|---|---|---|
| stderr | yes | JSON (or text when `PUMPGROK_LOG_JSON=false` in `dev`) | process stderr; compose json-file driver rotates |
| file | when `var/` writable | JSON | `var/log/pumpgrok.jsonl`, `RotatingFileHandler` 20 MB x 5 |
| ledger mirror | yes | sqlite row | every record with `event` in the mirrored set is also an `events` row (same cid) |
| alerts | by config | text | `Notifier` sinks: stdout + file always, Telegram + webhook when configured (D6) |

### 5.5 Metrics (prometheus_client, prefix `pumpgrok_`)

| Metric | Type | Labels | Note |
|---|---|---|---|
| `pumpgrok_cycle_duration_seconds` | Histogram | `task` (monitor, analyze, score, risk, exec, watch, report) | one observation per supervisor task iteration |
| `pumpgrok_data_age_seconds` | Gauge | `source` (pumpfun_rest, pumpportal_ws, jupiter, solana_rpc, grok) | now - last successful payload; breaker `data-stale` reads this |
| `pumpgrok_upstream_requests_total` | Counter | `source`, `outcome` (ok, 4xx, 5xx, timeout, transport) | |
| `pumpgrok_tool_errors_total` | Counter | `tool` (`<ns>.<verb>`), `seat` | registry wraps every tool call |
| `pumpgrok_signals_total` | Counter | `outcome` (generated, accepted, vetoed, expired) | |
| `pumpgrok_orders_total` | Counter | `side`, `mode`, `outcome` (placed, filled, rejected, unknown_result) | `unknown_result` must stay 0 in paper |
| `pumpgrok_fills_total` | Counter | `side`, `mode` | |
| `pumpgrok_open_positions` | Gauge | -- | |
| `pumpgrok_equity_sol` | Gauge | `kind` (realized, unrealized, total) | |
| `pumpgrok_daily_pnl_sol` | Gauge | -- | 5 % floor computed from this and `equity_sol{kind="total"}` at day start |
| `pumpgrok_drawdown_pct` | Gauge | -- | from peak equity snapshot |
| `pumpgrok_breaker_state` | Gauge | `breaker` (data_stale, loss_velocity, exec_errors, daily_loss, drawdown, killswitch) | 0 closed, 1 open, 2 cooldown |
| `pumpgrok_killswitch_active` | Gauge | `source` (env, file, channel) | |
| `pumpgrok_grok_calls_total` | Counter | `model`, `outcome` | vendor `CallBudget` (`ops.py:187`) ported |
| `pumpgrok_build_info` | Gauge | `version`, `mode`, `profile` | constant 1 |

Exposition: `GET /metrics` via the vendor-style asyncio HTTP server (`ops.py:299-357` ported),
loopback only; `/healthz` returns `{"status": "ok|degraded|halted", "mode", "killswitch",
"breakers", "data_age"}` with 200 only for `ok`.

### 5.6 Spans

No OpenTelemetry dependency in this wave. `span(name, **fields)` is an async-aware context
manager in `src/pumpgrok/logging/spans.py` that (a) records
`pumpgrok_cycle_duration_seconds{task=name}` and (b) emits one JSON log line
`event="span"` with `duration_ms`, `ok`, and the current cid. Nested spans carry `parent` =
enclosing span name. [INFERENCE] If tracing is needed later, this surface maps 1:1 onto an OTel
tracer without touching call sites.

## 6. Canonical commands

Every later verification (receipts, CI, docs) runs these exact strings. Pre-conditions: `uv`
0.13.x on PATH, Python 3.12, repo root as cwd.

```
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run pytest -q
uv run pip-audit
uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke
uv run pumpgrok doctor
python3 ci/gates/run_all.py --bot bot-00-chief --base origin/main --receipt .receipts/bot-00-chief/<task>.json
bash scripts/assemble-prompts.sh --check
./scripts/check.sh
docker compose up pumpgrok
```

Notes: `uv run pip-audit` with no arguments audits the active environment (the synced venv);
the Makefile `audit` target is the stricter lockfile form. `python3 ci/gates/run_all.py` is run
with system `python3` + `pyyaml` on purpose (same as `gates.yml:68`): the gates must not depend
on the product's virtualenv.

## 7. MIGRATION_NOTES

| Id | Change | Breaking for | Required action |
|---|---|---|---|
| M-1 | websockets `>=12.0` (vendor `pyproject.toml:13`) -> `17.3` | `websockets.connect` at `vendor/.../monitor.py:218` and the `FakeWebSocket` monkeypatch in `tests/test_filter.py` | Since 14.0 the top-level `websockets.connect` is the new asyncio implementation; port imports to `from websockets.asyncio.client import connect`; the legacy implementation remains until Nov 2029 (upgrade guide) but is deprecated, so do not import `websockets.legacy`. Characterization test must patch `pumpgrok.engine.monitor.connect`, not `websockets.connect`. New implementation defaults: `max_queue=16`, `ping_interval=20`; set `max_queue=None` explicitly if the PumpPortal burst exceeds 16 frames per read (vendor had no bound) |
| M-2 | pydantic `>=2.6` -> `2.14.1`; `pydantic-settings` added | vendor `Config.load` manual YAML + `ENV_OVERRIDES` (`models.py:403-407,486-490`) | Replace with `BaseSettings` TOML sources; `GROKBOT_*` names become `PUMPGROK_*` with `__` nesting; `SecretStr` fields unchanged; `extra="allow"` on upstream models becomes `extra="ignore"` (section 1 row 7); run `mypy` with the `pydantic.mypy` plugin |
| M-3 | httpx `>=0.27` -> `0.28.1` | `httpx.AsyncClient(timeout=...)` (`agents/base.py:75`) | 0.28 removed `proxies=` and `app=` kwargs and changed default `trust_env` handling in some transports; the vendor passes only `timeout`, so no call-site change; the per-upstream `httpx.Timeout` object replaces the float |
| M-4 | mypy non-strict (`vendor pyproject.toml:62-69`) -> `mypy 2.4 --strict` | every ported module | mypy 2.0 enables `local_partial_types` and `strict_bytes` by default and drops Python 3.9 targets; expect new errors in `analyzer.py` heuristics (`dict[str, Any]` payloads) and `log.py` byte handling; fix by typing, never by `# type: ignore` without a code |
| M-5 | pytest-asyncio `>=0.23` -> `1.4.0` | any test using the `event_loop` fixture | 1.0 removed `event_loop`; vendor tests use `asyncio_mode = "auto"` (`pyproject.toml:42`) and `FakeClock`, scout-vendor-engine line 66, so only tests that override the loop need rewriting to `loop_scope` |
| M-6 | setuptools `packages = ["src","src.agents"]` (`vendor pyproject.toml:37-38`) -> `uv_build` src layout | imports `from src.pipeline import ...`, console script `grokbot = src.pipeline:main` (`:32`) | Package becomes `pumpgrok.*`; `tools/pipeline_evidence.py` default log path `vendor/grokbot-pumpfun/logs/trades.jsonl` (scout-pumpgrok-code line 12) becomes `var/journal/` via the ledger export; `grokbot` script is not re-exposed |
| M-7 | Secrets policy and live gate | operators who passed `--rpc https://...?api-key=...` on the CLI (`tools/authority_check.py` `--rpc` flag, scout-pumpgrok-code line 23) or set `GROKBOT_WALLET_PRIVATE_KEY` | Secrets come only from env or a secret manager injecting env (`.env` is gitignored and G-3 `ALWAYS_FLAG_FILES`); RPC keys travel in a header field `solana.rpc_api_key`, never inside `rpc_urls`; the loader refuses to start when any forbidden key name (section 3.5) is present; an effective mode of `live` (R30 precedence) refuses to start unless all nine R21 preconditions hold (effective mode live; `PUMPGROK_LIVE_ENABLE=1`; `live.min_paper_days >= 14` measured only on `source=paper` ledger events; closed_trades >= 50, profit_factor >= 1.2, max_drawdown <= `drawdown_halt_fraction` on the same events; non-empty public-address allowlist; `0 < live.notional_cap_sol <= 1.0`; HMAC-signed confirmation record from `pumpgrok live confirm`; `live.adapter` named AND registered, which no build satisfies; no active kill switch, halt or open breaker), printing every unmet item and exiting 3 (R21; there is no exit-2 variant anywhere); there is no private-key field anywhere in settings (Security Constitution unchanged) |
| M-8 | Logging | vendor human-readable stderr (`log.py:30-36`) | JSON by default; `PUMPGROK_LOG_JSON=false` restores text in `dev`; operator runbooks that grep `%(levelname)-7s` patterns must switch to `jq` |
| M-9 | Health server | `GROKBOT_HEALTH_PORT` (`models.py:403-414` region) | `PUMPGROK_HEALTH_PORT` default 8080 in container, 0 (disabled) when running `--once` or `--replay` |
| M-10 | `JitoConfig` and `SolanaConfig.wallet_private_key` removed (R3) | vendor `JitoConfig` (`models.py:291-294`), `SolanaConfig.wallet_private_key` (`:299`), `SolanaConfig.jito` (`:300`), `wallet_key` property (`:303-304`), env `GROKBOT_WALLET_PRIVATE_KEY` (`:407`), `config.example.yaml:28-31` | No replacement field. Jito is dead config (only the `LiveExecutor` TODO comment at `executor.py:156-158` names it) and D8 covers venues and data sources only; private keys never enter the system (D4), so the setting cannot exist. `test_config.py` cases that set a wallet key are rewritten to assert the loader REJECTS any `*PRIVATE_KEY*` env name (section 3.5). Key-custody wording everywhere: "no key material exists in paper mode; nothing to custody" (R40) |

## Contradictions with D1-D9 found while writing

- None that block. One tension to note for the orchestrator: D5 names `pip-audit`, but the
  precedent documents that `pip-audit` cannot read a uv `pyproject.toml`
  (`security-pr.yml:290-294`); the `uv export` bridge in section 1 row 12 resolves it without
  dropping either tool.
- G-7 precedent `ROSTER_MIN_TOOLS = 10` (`check_desk_integrity.py:41`) conflicts with the
  assignment text "rosters per seat 8-15 tools"; resolved by R19 (8..15 inclusive, dotted
  `TOOL_NAME_RE`), applied in section 4.
- `requires-python = ">=3.12,<3.13"` adds an upper bound beyond the original R13 text; R40
  amends R13 to exactly this string, so the pin stands.
- Live-gate refusal exit code: earlier drafts said 2; R21 fixes it at 3 and every mention in
  this document (section 3.5, M-7) now says 3.
- Overlay location: earlier drafts placed TOML under a root `config/`; R30 puts the three
  overlays in-package at `src/pumpgrok/config/overlays/` with `PUMPGROK_CONFIG` as the only
  operator file; section 1 row 1, section 3.3 and section 3.5 were rewritten to that.

## Unverified Items

| Id | Unknown | Default assumed here |
|---|---|---|
| U-1 | Whether `uv_build` 0.13.x honours `[tool.uv.build-backend] module-root = "src"` exactly as written (gateway precedent uses a flat `src/desk_gateway` with no explicit table, `services/desk-gateway/pyproject.toml:28-30`) | Assumed yes; if not, `module-root` is dropped and the default `src/` discovery applies |
| U-2 | `pydantic-settings` 2.16 TOML multi-file layering syntax (`toml_file` accepting a list, with later files overriding) | Assumed supported; fallback is a 15-line custom `PydanticBaseSettingsSource` merging two TOML dicts |
| U-3 | Whether this organisation's GitHub-hosted minutes are blocked for pumpgrok as they are for programming-desk (`gates.yml:13-17`) | `ci.yml` drafted on `ubuntu-latest`; `gates.yml` and `security-pr.yml` keep `[self-hosted, Linux, X64]` verbatim. If minutes are blocked, switch `ci.yml` to the self-hosted label |
| U-4 | Commit SHA for `astral-sh/setup-uv` matching uv 0.13.3 | Left as `<pin-by-sha>`; implementation wave resolves it per `SECURITY.md` "pin what executes by commit SHA" (`security-pr.yml:322-323`) |
| U-5 | Coverage threshold | None set; `pytest-cov` not added until RISK agrees a number |
| U-6 | Hermes runtime's behaviour when `PUMPGROK_*` nested keys use `__` (profiles.yaml `.env` is written by `scripts/hermes-bootstrap.sh`) | Assumed opaque passthrough; verified by `scripts/hermes-verify-isolation.sh` in the implementation wave |
| U-7 | Exact Helius/QuickNode URL shapes for the G-3 regexes | Regexes drafted from public URL formats; G-3 self-test fixtures must be synthetic and `# pragma: allowlist secret` annotated |
| U-8 | Whether `prometheus_client` ships `py.typed` (affects the mypy override) | Override `ignore_missing_imports = true` kept for `prometheus_client.*`; removed if stubs resolve |
| U-9 | GitHub repository URL for `[project.urls]` | `https://github.com/swcstudio/pumpgrok` assumed from the Linear workspace slug; manifests today say `your-org` (node n2 fixes) |
