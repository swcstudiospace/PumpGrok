<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Toolchain (FOUND-001, 002):** pyproject `requires-python >=3.12,<3.13`, uv_build `module-root = "src"`, script `pumpgrok = "pumpgrok.cli:main"`; commit `.python-version` (3.12) and `uv.lock`; `mypy --strict src/` without prometheus or respx overrides (V-5); pytest `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"` (V-9); audit uses `uv export --no-emit-project` (V-4).
- **Container (FOUND-003):** non-root multi-stage image, uv 0.13.4 (V-2), `PUMPGROK_PROFILE=paper`; HEALTHCHECK runs `pumpgrok doctor`; compose `env_file` with `required: false`.
- **Config (FOUND-004, STRUCT-008, SEC-002):** pydantic-settings, prefix `PUMPGROK_`, `__` nesting. Precedence: CLI > env > `PUMPGROK_CONFIG` file > overlay `src/pumpgrok/config/overlays/{dev,paper,live}.toml` (`PUMPGROK_PROFILE`, default paper) > defaults. Mode: `--mode` > `PUMPGROK_MODE` > TOML `execution.mode` (R30). Every overlay has `[live] enabled = false`. Exit 1, values never printed: unknown key, bad type, unknown profile, forbidden names (PRIVATE_KEY, SECRET_KEY, SEED, MNEMONIC, PHANTOM, WALLET_SECRET, KEYPAIR; `replay.seed` exempt), URLs with `api-key=`, `key=` or `token=`. No Jito or wallet-key field (M-10); no root `config/`.
- **Risk and money (R20, R28):** `RiskBudget` has the nine keys of interfaces.md:728; `daily_loss_halt_fraction` capped at 0.05 (INV-C-06); money is `int`.
- **Live gate (R21):** `LiveGate.check()` returns the nine ids in order. `run` prints each unmet id as `[ ] n id reason` and exits 3 before other work. Ids 3, 4, 7, 9 need ledger or confirmation data not yet present: unmet, fail closed. Id 8 is always unmet. `LiveAdapter` stub raises `LiveGateError` after appending `LiveWriteAttempted` (interfaces.md:611).
- **Ids and logging (R29, OBS-001, OBS-002):** `IdFactory(clock, rng)` emits a hand-rolled Crockford ULID (interfaces.md:157-172). CorrelationId is the plain ULID root; children `<ulid>.<n>`. `uuid` banned. JSON log per FOUNDATION_STACK 5.1 with a RedactionFilter; `PUMPGROK_LOG_JSON=false` only in dev.
- **Core (FOUND-005):** `core/{interfaces,registry,ids,approvals,__init__}.py` per interfaces.md 2.1-2.5 and 923-. `ToolRegistry.find` raises `LiveGateError` for any LIVE_WRITE spec (I3) and audits refusals (I4). `canonical_json` rejects floats; do not copy interfaces.md:253 `default=str`.
- **Ledger (FOUND-013, R26, R28, R32):** `ledger/{store,events}.py` per paper-engine.md 3.2-3.3 (schema and hash rule); `BEGIN IMMEDIATE` appends; genesis prev_hash 64 zeros; 18 CamelCase models; `atomic_write` tmp+fsync+os.replace. Replay ledgers are recreated each run.
- **Replay (FOUND-012, R27):** `replay/clock.py` (WallClock, FixtureClock), `rng.py` (`make_rng`, the only RNG constructor), `fixtures.py` (sha256 manifest check; mismatch exits 4, no ledger; INV-R-30).
- **Skip cycle and doctor (FOUND-013, R37):** `run --mode paper --once --replay tests/fixtures/replay/smoke` runs the gate, reads fixture events, appends one JournalNote (`source=replay`, cycle ULID) and exits 0. `run` without `--once --replay` exits 5. `doctor` marks absent subsystems `not-yet-implemented` (warning, exit 0).
- **Ownership and gates (FOUND-006, 007, 010):** `ownership.yaml` names `bot-00-chief` .. `bot-09-journal`; rules from ROSTER.md:427-840 amended by R36; last match wins; G-1 self-test walks `git ls-files`. Ported `ci/gates/*.py` with FOUNDATION_STACK sec 4 constants: `TOOL_NAME_RE = ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`, `SEAT_RE = ^bot-0[0-9]-[a-z-]+$`, roster 8..15, six G-3 trading patterns. `.receipts/<seat>/.gitkeep` x10; gates.yml, security-pr.yml, ci.yml.
- **Contracts and prompts (FOUND-008, 009):** `contracts/` per ROSTER.md sec 8 (R35 sizes); 18 `events/<snake>.schema.json` generated from `ledger/events.py`; `prompts/` sources with ported scripts; `agents/*.md` keep agents/chief.md:1-17 frontmatter.
- **Desk docs (FOUND-011):** AGENTS.md desk rules index above line 1, GSD marker blocks verbatim; SECURITY.md key-custody line (R40); CHANGELOG.md; docs/quality-gates.md; docs/desk-operating-model.md; docs/cross-bot-protocol.md; levels `research | paper` only.
- **Hygiene, secrets, harness (STRUCT-001, SEC-001, FOUND-012):** `git rm --cached` the six tracked `*.pyc`; delete `issues/tissue.json`; `docs/VENDOR_PIN.md` (409e74c); `.gitignore` per FOUND-007 plus `.planning/research/.cache/`; `scripts/check.sh` rewritten. `.env.example` placeholders only; no PumpPortal key (R45), lite-api URL (R44) or wallet key. `tests/conftest.py` blocks httpx and `websockets.connect`; `tests/harness/faults.py` FaultInjector.

### Claude's Discretion
- **Container command (conflict):** SC4 needs a healthy running container; no supervisor before Phase 4. Default CMD `doctor --hold` (holds until SIGTERM). Orchestrator approves or relaxes SC4.
- **Dependencies:** declare only imports (pydantic, pydantic-settings, httpx, websockets, pyyaml); defer tenacity (Phase 2) and prometheus-client (Phase 5).
- Exit codes: 0 ok, 1 config, 2 ledger inconsistent (reserved), 3 live refused, 4 corrupt fixture, 5 not implemented. `PUMPGROK_EXECUTION__MODE` is a startup error.
- Skip JournalNote: `seat="desk"`, `note_kind="note"`; MIGRATION_MAP's `note_kind: cycle` is not in the enum.
- Open: design hash omits `idempotency_key`; recommend adding before the first ledger write.
- `your-org` remains in plugin.json:8,11 and SETUP.md:16-17; check.sh warns via allowlist until STRUCT-007.
- REQUIREMENTS test paths win over SAFETY_INVARIANTS. `[live] enabled` is a marker, not a precondition. Live stub moves to Phase 1 (INV-C-03).

### Deferred Ideas (OUT OF SCOPE)
- Phase 2: engine port, read-only tools, RPC client, SEC-003, STRUCT-002..007. Phase 3: tool layer, gateway, skills.
- Phase 4: PaperAdapter, RiskEngine, supervisor, reducer and export, reports, SEC-004, GOLIVE-001/002. Phase 5: /metrics, runbooks, soak, SEC-005, GOLIVE-003.

### Orchestrator resolutions (binding)
- R50 (container, Phase 1): the compose service runs `pumpgrok run --mode paper --once --replay /app/tests/fixtures/replay/smoke` and exits 0. The compose healthcheck runs `pumpgrok doctor` (FOUND-003). No `--hold` mode is built. The healthy long-running container is verified in ROADMAP Phase 5 criterion 3 once the supervisor health endpoint exists. ROADMAP Phase 1 criterion 4 was reworded accordingly.
- R51 (Docker): the docker CLI is installed (29.6.2). Criterion 4 needs a reachable daemon. If the daemon is unreachable, record the exact error as a blocker; do not substitute another check.
</user_constraints>

# Phase 1: Foundation - Research

**Researched:** 2026-10-21
**Domain:** Python 3.12 packaging (uv_build), typed config (pydantic-settings), hash-chained SQLite ledger, deterministic replay, CI gates, Docker
**Confidence:** HIGH for toolchain, config and ledger mechanics (probed locally); MEDIUM for the gate port and prompt pipeline (read, not executed); see Open Questions for the items that need an orchestrator decision.

## Summary

Phase 1 turns an empty `src/`-less repo into a gated package whose only runtime behaviour is one skip-only replay cycle. The design documents are complete and internally consistent on almost every point. The research below verified the risky mechanics by running them in a scratch project under `/tmp` (outside the repo) and checked every pin against the PyPI JSON API on 2026-10-21. Nothing in the repo was modified.

The toolchain works as specified: `uv_build` with `module-root = "src"` builds and installs, `uv export --no-emit-project` emits no project line, and `pip-audit --strict` reports no advisories on the runtime pins. pydantic-settings layers TOML files as a list (later files override) with `__` nesting, and it is the right base for the R30 precedence.

Four behaviours are not provided by the libraries and must be built explicitly, because the success criteria depend on them: (1) pydantic-settings silently ignores unknown `PUMPGROK_*` names, (2) `PUMPGROK_EXECUTION__MODE=live` is accepted unless refused, (3) `ValidationError` text echoes the rejected input value, and (4) the forbidden-name refusal has no library support. The ledger's append-only guarantee and the ULID encoding were verified directly.

Three conflicts in the inputs need an orchestrator decision before planning locks: the compose restart policy versus the one-shot container (FOUND-003 text versus R50), the `requests` import that the legacy `tests/test_tools_cli.py` needs (it fails without it), and the `journal_note` `note_kind` enum (ROSTER lists `halt`, paper-engine does not).

**Primary recommendation:** Build Phase 1 in this order: toolchain and `uv.lock` (generated with uv 0.13.4) -> settings with explicit guards -> core ids/errors/registry -> ledger store and events -> replay clock/rng/fixtures -> CLI `run`/`doctor` -> ported gates, ownership, contracts, prompts, docs -> network-blocking harness and static guards -> Dockerfile, compose and workflows. Run the success-criteria commands only at the phase gate.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Layered settings and forbidden-key refusal | Process (CLI/config) | - | Read once at start; refusal must happen before any I/O |
| Effective mode resolution (R30) | Process (CLI) | Config | CLI flag is the top source; live gate reads the merged result |
| Live gate (nine ids) and LiveAdapter stub | Execution (live package) | Ledger (ids 3,4,7,9 read ledger) | Owned by bot-02-risk; fail-closed; no venue code |
| Hash-chained ledger append | Database (SQLite WAL) | Ledger library (`store.py`) | Single writer via `BEGIN IMMEDIATE`; chain computed in transaction |
| ULID and correlation ids | Core library | Replay clock/rng | Only source of ids (R29); deterministic under replay |
| Replay clock, RNG, fixture verification | Replay library | Process | Virtual time; sha256 manifest gate before any ledger write |
| Skip-only cycle orchestration | CLI | Replay runner (Phase 4 owns full runner) | Phase 1 cycle is a fixed skeleton, no engine |
| Ownership, receipts, secrets, contracts, desk integrity gates | CI / repo tooling (stdlib + pyyaml) | Pre-commit, workflows | Run without the product venv (FOUNDATION_STACK sec 6) |
| Prompt assembly and agent templates | Repo tooling (bash + python) | Contracts (roster YAML) | Generated artefacts; `--check` mode in CI |
| Container runtime | Docker image | Compose | Non-root; no secrets baked in; replay command per R50 |

## Standard Stack

### Core (runtime, Phase 1)

| Library | Pin to declare | Latest verified | Released | requires-python | Purpose |
|---|---|---|---|---|---|
| pydantic | `>=2.14.1,<3` | 2.14.1 | 2026-10-11 | >=3.10 | Models, `extra="forbid"` for our contracts |
| pydantic-settings | `>=2.16.1,<3` | 2.16.1 | 2026-10-20 | >=3.11 | Layered config (V-1 floor raised to 2.16.1) |
| pyyaml | `>=6.0.3,<7` | 6.0.3 | 2025-09-29 | >=3.8 | Rosters, ownership manifest, gates |
| httpx | `>=0.28.1,<0.29` | 0.28.1 | 2024-12-06 | >=3.8 | Imported by the network-blocking conftest; no product client in Phase 1 |
| websockets | `>=17.3,<18` | 17.3 | 2026-10-19 | >=3.11 | Imported by the conftest guard; target import path `websockets.asyncio.client` |

Verified with `https://pypi.org/pypi/<pkg>/json` on 2026-10-21 (`info.version`, max upload date of that release, `info.requires_python`) [VERIFIED: PyPI JSON API].

### Dev group (tooling; declared because the canonical commands invoke them)

| Library | Pin | Latest verified | Released | Notes |
|---|---|---|---|---|
| uv | installer `0.13.4` (not a Python dep) | 0.13.4 | 2026-10-20 | V-2; local binary is 0.11.26, see Environment |
| uv-build (`uv_build`) | `>=0.13.4,<0.14.0` | 0.13.4 | 2026-10-20 | V-2 |
| ruff | `>=0.17.1,<0.18` | 0.17.1 | 2026-10-15 | Lint and format |
| mypy | `>=2.4.0,<3` | 2.4.0 | 2026-10-01 | `--strict src/` |
| pytest | `>=9.1.1,<10` | 9.1.1 | 2026-06-19 | |
| pytest-asyncio | `>=1.4.0,<2` | 1.4.0 | 2026-05-26 | V-9 loop scope set explicitly |
| pip-audit | `>=2.10.1,<3` | 2.10.1 | 2026-06-10 | Run over `uv export` |
| types-PyYAML | `>=6.0.12.20260906` | 6.0.12.20260906 | 2026-09-06 | mypy stubs |

Deferred (not declared in Phase 1; CONTEXT says declare only imports): tenacity 9.2.1 (Phase 2), prometheus-client 0.26.0 (Phase 5), respx 0.23.1 (first imported when recorded HTTP fixtures land, Phase 2/3). `respx` is not needed for the Phase 1 network guard, which uses `httpx.AsyncHTTPTransport` patching (see Pattern 4).

### Corrections to FOUNDATION_STACK section 2 / 3.1

| Item | FOUNDATION_STACK says | Phase 1 uses | Source |
|---|---|---|---|
| pydantic-settings floor | `>=2.16.0` | `>=2.16.1` | V-1 (STACK.md) and PyPI |
| uv installer / uv_build | 0.13.3 | 0.13.4 | V-2 and PyPI |
| `.python-version` | not addressed | `3.12` committed | V-3 |
| audit export | no `--no-emit-project` | add `--no-emit-project` | V-4; verified: output has no project line |
| mypy overrides | prometheus_client, respx ignore_missing_imports | removed (neither is imported in Phase 1) | V-5 |
| pytest-asyncio | no loop scope | `asyncio_default_fixture_loop_scope = "function"` | V-9 |
| `[project.urls]` | `https://github.com/swcstudio/pumpgrok` | git origin is `https://github.com/swcstudiospace/PumpGrok.git` (verified `git remote -v`); orchestrator must pick one | Open Question Q5 |
| `.env.example` | contains `PUMPGROK_DATA__API_KEY` (PumpPortal) and `lite-api.jup.ag/swap/v1/quote` | remove both (R45, R44) | FOUNDATION_STACK 3.5 lines 378-379 vs CONTEXT "Hygiene" |

### Package Legitimacy Audit

Ran `gsd_run query package-legitimacy check --ecosystem pypi ...` on 2026-10-21 (verified output). **No package returned OK or SLOP. All 15 returned SUS** with reasons `too-new` (release within about two weeks) and/or `unknown-downloads` (the seam has no PyPI download counts). Each package name matches its canonical project and source repository, which is consistent with the reasons being signal gaps rather than identity problems. Per the protocol every package is kept and tagged.

| Package | Registry | Released | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|----------|-----------|-------------|---------|-------------|
| uv-build | PyPI | 2026-10-20 | unknown | `repoUrl` reports `pypi.org/project/uv/` (odd; verify) | [WARNING: flagged as suspicious - verify before using.] SUS | Flagged; checkpoint |
| pydantic | PyPI | 2026-10-11 | unknown | github.com/pydantic/pydantic | [WARNING: flagged as suspicious - verify before using.] SUS | Flagged; checkpoint |
| pydantic-settings | PyPI | 2026-10-20 | unknown | github.com/pydantic/pydantic-settings | [WARNING: flagged as suspicious - verify before using.] SUS | Flagged; checkpoint |
| httpx | PyPI | 2024-12-06 | unknown | github.com/encode/httpx | [WARNING: flagged as suspicious - verify before using.] SUS | Flagged; checkpoint |
| websockets | PyPI | 2026-10-19 | unknown | github.com/python-websockets/websockets | [WARNING: flagged as suspicious - verify before using.] SUS | Flagged; checkpoint |
| pyyaml | PyPI | 2025-09-29 | unknown | pyyaml.org | [WARNING: flagged as suspicious - verify before using.] SUS | Flagged; checkpoint |
| ruff | PyPI | 2026-10-15 | unknown | docs.astral.sh/ruff | [WARNING: flagged as suspicious - verify before using.] SUS | Flagged; checkpoint |
| mypy | PyPI | 2026-10-01 | unknown | mypy-lang.org | [WARNING: flagged as suspicious - verify before using.] SUS | Flagged; checkpoint |
| pytest | PyPI | 2026-06-19 | unknown | github.com/pytest-dev/pytest | [WARNING: flagged as suspicious - verify before using.] SUS | Flagged; checkpoint |
| pytest-asyncio | PyPI | 2026-05-26 | unknown | github.com/pytest-dev/pytest-asyncio | [WARNING: flagged as suspicious - verify before using.] SUS | Flagged; checkpoint |
| pip-audit | PyPI | 2026-06-10 | unknown | github.com/pypa/pip-audit | [WARNING: flagged as suspicious - verify before using.] SUS | Flagged; checkpoint |
| types-PyYAML | PyPI | 2026-09-06 | unknown | github.com/python/typeshed | [WARNING: flagged as suspicious - verify before using.] SUS | Flagged; checkpoint |
| tenacity, respx, prometheus-client | PyPI | - | - | - | Not declared in Phase 1 | Deferred; no install |

**Packages removed due to SLOP verdict:** none.
**Packages flagged as suspicious SUS:** all 12 declared packages above. Protocol says the planner adds `checkpoint:human-verify` before each install. Because `uv lock` installs the whole set in one step, recommend ONE checkpoint gating `uv lock` that lists all 12 with the versions above. This batching is a deviation the orchestrator should approve (Open Question Q10). Also verify the `uv-build` repository URL before the checkpoint.

No `postinstall` scripts apply (Python packages). Packages are not discovered through WebSearch; all pins come from PyPI JSON, so none is `[ASSUMED]`.

## Architecture Patterns

### Module placement for Phase 1 (batch 1 of MIGRATION_MAP section 7.1, plus CONTEXT overrides)

```
src/pumpgrok/
  __init__.py
  cli.py                  run (paper --once --replay), doctor, live stub exit path
  config/settings.py      BaseSettings, source chain, forbidden-key scan, mode resolver
  config/overlays/{dev,paper,live}.toml   [live] enabled = false in all three
  core/__init__.py        re-exports (interfaces.md section 1)
  core/interfaces.py      one-line facade over core/__init__ (MIGRATION 7.1 note)
  core/side_effect.py core/errors.py core/correlation.py core/idempotency.py
  core/tool.py core/datasource.py core/adapter.py core/skill.py core/bot.py
  core/registry.py core/ids.py core/approvals.py core/atomic_write.py
  ledger/store.py         BEGIN IMMEDIATE append, hash chain, snapshots, canonical_json use
  ledger/events.py        18 pydantic models + EventType StrEnum + snake mapping
  replay/clock.py         Clock protocol, WallClock (ONLY module allowed time/asyncio sleep), FixtureClock
  replay/rng.py           make_rng(seed) - the only random.Random constructor
  replay/fixtures.py      manifest sha256 verification, JSONL readers
  logging/json.py         JsonFormatter, RedactionFilter, contextvars CID/SEAT/TICKET
  execution/live/live_gate.py     LiveGate.check() -> nine ids in order
  execution/live/live_adapter.py  LiveAdapter stub: LiveWriteAttempted then LiveGateError
```

Notes on placement:
- `execution/live/` is listed in MIGRATION batch 4, but CONTEXT (Live stub moves to Phase 1, INV-C-03; Locked "Live gate") puts it in Phase 1. Follow CONTEXT and record the move in the batch table. [CITED: docs/MIGRATION_MAP.md:571-577; .planning/phases/01-foundation/01-CONTEXT.md]
- `RiskBudget`, `BotManifest`, `ApprovalRecord` live in `core/bot.py` and `core/approvals.py` per interfaces.md sections 2.8-2.9 and MIGRATION 7.1 row batch 1. [CITED: docs/design/interfaces.md:728-863]
- `risk/` as a package is NOT Phase 1 (batch 4), except that `RiskBudget` values are validated in `config/settings.py`.

### Pattern 1: Settings with an explicit source chain and guards

pydantic-settings layers sources; it does not refuse unknown or forbidden names. Verified behaviour in a scratch project with pydantic-settings 2.16.1:

```python
# Source: verified in /tmp/probe/settings_probe.py (uv run, pydantic-settings 2.16.1)
@classmethod
def settings_customise_sources(
    cls,
    settings_cls: type[BaseSettings],
    init_settings: PydanticBaseSettingsSource,
    env_settings: PydanticBaseSettingsSource,
    dotenv_settings: PydanticBaseSettingsSource,
    file_secret_settings: PydanticBaseSettingsSource,
) -> tuple[PydanticBaseSettingsSource, ...]:
    files = [overlay_path(profile)]
    if config_file := os.environ.get("PUMPGROK_CONFIG"):
        files.append(Path(config_file))  # applied last among files
    return (init_settings, env_settings, TomlConfigSettingsSource(settings_cls, toml_file=files))
```

Verified results: defaults give `paper`; `PUMPGROK_RISK__MAX_TRADE_FRACTION=0.01` overrides nested; a `PUMPGROK_CONFIG` file with `mode = "live"` overrides the overlay. `toml_file` accepts a list and later files win [VERIFIED: local probe].

The `mypy --strict` run on this probe failed with `no-untyped-def` on an unannotated `settings_customise_sources`; the signature above is annotated and is required. [VERIFIED: local probe]

Behaviour the library does NOT provide (verified), so the loader must add it:

| Input | Library result (verified) | Required behaviour |
|---|---|---|
| `PUMPGROK_BOGUS=1` | accepted, ignored | exit 1, unknown key (name only, no value) |
| `PUMPGROK_RISK__BOGUS=1` | accepted, ignored | exit 1, unknown key |
| `PUMPGROK_EXECUTION__MODE=live` | accepted, effective live | startup error (CONTEXT, Discretion) |
| `PUMPGROK_RISK__MAX_TRADE_FRACTION=abc` | `ValidationError` | exit 1; do not print the value |
| `PRIVATE_KEY=x` in env | accepted | exit 1 (forbidden substring, case-insensitive) |
| `PUMPGROK_REPLAY__SEED=1` | accepted | must be allowed (replay.seed exempt) |

**ValidationError leaks values (verified):** `str(e)` contained the rejected string, and `e.errors()[0]` has an `input` key. Map errors to `(loc, type)` only and drop `input` and `ctx`. [VERIFIED: local probe, `ERRSTR_HAS_VALUE: True`]

### Pattern 2: Ledger append inside BEGIN IMMEDIATE (verified)

```python
# Source: verified /tmp/probe/test_probe.py - sqlite3 stdlib, WAL, trigger refusal
conn = sqlite3.connect(path, isolation_level=None)  # explicit transactions
conn.execute("PRAGMA journal_mode=WAL")  # returned 'wal'
conn.execute("BEGIN IMMEDIATE")
# read head (seq, hash) -> compute prev_hash, hash -> INSERT
conn.execute("COMMIT")
# UPDATE on events raises sqlite3.IntegrityError("ledger is append-only") via RAISE(ABORT)
```

Schema and hash rule are in paper-engine.md 3.2 [CITED: docs/design/paper-engine.md:289-313]. Known gap to resolve before the first write: the hash input (`prev_hash, seq, ts_utc, source, correlation_id, type, payload_json`) omits `idempotency_key`, which is `NOT NULL UNIQUE`. Recommendation: include `idempotency_key` in the hash input and state it in paper-engine.md 3.2 in the same change (CONTEXT Open item; Open Question Q3).

### Pattern 3: ULID (hand-rolled, verified against the spec vector)

```python
# Source: interfaces.md:157-183 (IdFactory, _crockford); vector checked locally
ms = int(clock.now() * 1000)
rand = rng.getrandbits(80)
ulid = _crockford((ms << 80) | rand, 26)
# spec vector: ms=1469918176385 -> prefix '01ARYZ6S41' (VERIFIED locally)
```

`ULID_RE = ^[0-9A-HJKMNP-TV-Z]{26}$` (interfaces.md:138). The Crockford alphabet in `_CROCKFORD` is `0123456789ABCDEFGHJKMNPQRSTVWXYZ` (interfaces.md:175) [VERIFIED: local probe output matched spec prefix and regex].

### Pattern 4: Network-blocking conftest (verified)

Patching `httpx.AsyncHTTPTransport.handle_async_request` (and `httpx.HTTPTransport.handle_request`) to raise makes any un-mocked `AsyncClient` request fail. `httpx.MockTransport` continues to work because it is a different transport class. Both verified with pytest-asyncio auto mode [VERIFIED: /tmp/probe/test_net.py, 2 passed].

For websockets: ported code must import `from websockets.asyncio.client import connect` (M-1; [VERIFIED: websockets 17.3 exposes `websockets.asyncio.client.connect`]). The conftest patches `websockets.asyncio.client.connect` and `websockets.connect`; a static test asserts no `src/pumpgrok` module imports the legacy path. (Phase 1 has no websocket code, so the patch is a guard only.)

### Pattern 5: Static virtual-time and uuid guard

Implement as an AST walk over `src/pumpgrok/**/*.py` that rejects `asyncio.sleep`, `asyncio.timeout`, `asyncio.wait_for`, `time.time`, `time.monotonic`, `datetime.now`, `uuid` imports and `random.random` / unseeded `random.Random()`. Allowlist exactly `src/pumpgrok/replay/clock.py` for the wall-clock primitives, as paper-engine.md 4.1 says it is "the only module allowed to import time / asyncio.sleep / asyncio.timeout" [CITED: docs/design/paper-engine.md:441]. Without the allowlist the ROADMAP SC5 test fails on the very clock that implements R27.

### Pattern 6: Gate ports (ci/gates, read from the precedent)

Precedent at `~/src/repos/programming-desk/ci/gates/` (verified present: check_contracts.py, check_desk_integrity.py, check_ownership.py, check_receipt.py, check_rollback.py, check_secrets.py, run_all.py; precedent ci/tests/test_gates.py 109 KB; `.github/workflows/{gates,security-pr}.yml`; `scripts/{assemble-prompts.sh,generate-templates.py}`).

Constants that change, with the precedent value verbatim:

- `check_desk_integrity.py:41` `ROSTER_MIN_TOOLS = 10` -> 8 (R19); `:46` `TOOL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,60}$")` -> `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`; `:47` `SEAT_RE = re.compile(r"^bot-0[0-6]-[a-z-]+$")` -> `^bot-0[0-9]-[a-z-]+$`; `:33-35` `PACKS_DIR`, `TEMPLATES_DIR = "grokbot/templates"` (-> `agents`); remove `contracts/tool-packs` and pack checks (no tool packs in the design). [VERIFIED: grep of precedent check_desk_integrity.py:29-62]
- `check_ownership.py:36-58` `_match` is kept verbatim. A bare pattern (no `/`) matches its basename at ANY depth (`fnmatch(Path(path).name, pattern)`), so `README.md`, `Makefile`, `pyproject.toml` rules also catch vendor and tools copies. Order decides; the vendor rule must come later. [VERIFIED: code read at precedent check_ownership.py:36-58]
- `check_secrets.py` `PATTERNS` (17 families at lines 29-51) and `ALWAYS_FLAG_FILES` (line 77) get the six G-3 trading families from FOUNDATION_STACK sec 4 row G-3. `SKIP_DIRS` already contains `vendor` [VERIFIED: precedent check_secrets.py SKIP_DIRS].
- `run_all.py` runs G-1..G-7 and G-7 takes no `--bot` (precedent comment). Keep.
- G-1 self-test (new): walk `git ls-files`, resolve each path with the same matcher, fail on zero or multiple owners. Resolve against the ROSTER draft (below).

### Pattern 7: Ownership draft check (verified by simulation)

Ran the ROSTER.md section 7 YAML (167 rules) through the precedent `_match` against the 155 tracked files: **1 unowned path, `banner.jpg`**; no duplicate patterns; `vendor/**`, `tools/**`, `src/pumpgrok/execution/live/**` resolve as intended (last match). Add a rule for `banner.jpg` (owner bot-00-chief, alongside README) before the G-1 self-test is required to pass. [VERIFIED: /tmp/g1probe.py run over `git ls-files`]

### Anti-Patterns to Avoid

- **`canonical_json` with `default=str`** (interfaces.md:256): it silently stringifies unknown objects and admits floats. Use a validator that rejects `float` and any non-`str|int|bool|None|list|dict` leaf; Decimal values are converted to `str` explicitly before hashing (R28).
- **Printing `ValidationError`** (see Pattern 1).
- **Deleting `var/`** to reset a replay: remove only `var/replay/<dataset>/ledger.sqlite` (+ `-wal`, `-shm`) before the cycle.
- **Letting `.env` reach the image**: compose `env_file` injects it into the environment, so the forbidden-name scan must read `os.environ`, not a file.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Layered config from TOML + env | Custom merge of dicts | pydantic-settings `BaseSettings` + `TomlConfigSettingsSource` (verified) | Tested nested-env and list-of-file behaviour |
| Schema validation of our events | Hand-written validators | pydantic v2 models with `extra="forbid"` | Generates the JSON Schema files FOUND-008 needs |
| Hash chain / append-only | Separate hash file | SQLite triggers + `BEGIN IMMEDIATE` (verified) | Refusal is enforced by the DB |
| JSON canonical form | Ad-hoc dumps | Custom `canonical_json` (sorted, no float) on stdlib `json` | Stdlib suffices; float rejection is the only extra rule |
| HTTP mocking for the offline guard | Monkeypatch per test | `httpx` transport patch in autouse fixture (verified) | One place blocks everything |
| ULID | `uuid` (banned, R29) | Hand-rolled Crockford (verified vector) | 12 lines; deterministic under the injected clock/rng |
| Secret redaction | New scanner | Port the precedent `_redact`/PATTERNS (check_secrets.py) | Same families already tested by the gate |
| Test runner | unittest harness | pytest + pytest-asyncio auto mode (verified) | Matches FOUNDATION and ROADMAP commands |
| Prompt assembly | New templating | Port `scripts/assemble-prompts.sh` and `generate-templates.py` | `--check` modes already designed |

**Key insight:** the design already names every module and rule. The risk is in glue (guards, placeholders, file lists), not in libraries.

## Runtime State Inventory

Not a rename or migration of runtime state; the phase creates a greenfield package. Explicit answers, per Step 2.5 (applies to the `*.pyc` and `issues/` removals):

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None: no ledger, DB or ChromaDB/Mem0 store exists in the repo (`var/` absent) | none |
| Live service config | None found in repo; n8n/Datadog not referenced by Phase 1 files | none |
| OS-registered state | None: no systemd/launchd/Task Scheduler entry for pumpgrok (`hermes-install-cron.sh` is Phase 2) | none |
| Secrets/env vars | `.env` absent; `hermes/profiles.yaml` forbidden list (lines 18-23) must be enforced by the loader | code (guard), not data |
| Build artifacts | Six tracked `*.pyc` (`tests/__pycache__/`, `tools/__pycache__/`) and `issues/tissue.json` must be removed from the index | `git rm --cached` / delete in one change with `.gitignore` |

## Common Pitfalls

### Pitfall 1: Silent acceptance of unknown and forbidden env names
**What goes wrong:** the desk starts with a typo'd key or with `PRIVATE_KEY` set, and nothing refuses.
**Why:** pydantic-settings maps env only onto declared fields (verified: `PUMPGROK_BOGUS` ignored).
**How to avoid:** scan `os.environ` for `PUMPGROK_*` names and map them to field paths; refuse unknown ones. Scan all env names for forbidden substrings (`PRIVATE_KEY`, `SECRET_KEY`, `SEED`, `MNEMONIC`, `PHANTOM`, `WALLET_SECRET`, `KEYPAIR`), case-insensitive, except the exact name `PUMPGROK_REPLAY__SEED`.
**Warning signs:** a test that sets `PUMPGROK_BOGUS` passes `Settings()`.

### Pitfall 2: `PUMPGROK_EXECUTION__MODE=live` takes effect
**What goes wrong:** env overrides the TOML and bypasses the R30 mode order.
**How to avoid:** refuse that exact name at startup (CONTEXT Discretion). Mode resolution: `--mode` > `PUMPGROK_MODE` > TOML `execution.mode`. `PUMPGROK_MODE` is a top-level field `mode` (not nested), so it does not collide with `execution.mode`.

### Pitfall 3: Secret echo through validation errors
**What goes wrong:** a bad `PUMPGROK_SOLANA__RPC_API_KEY`-style value appears in the exit-1 message.
**How to avoid:** print `loc` and `type` only (verified that `str(e)` contains the input).

### Pitfall 4: `tests/test_tools_cli.py` cannot import without `requests` (blocker)
**What goes wrong:** the legacy test loads `tools/jupiter_quote.py` in-process. The module does `import requests` inside `try` and on `ImportError` prints JSON and calls `sys.exit(1)` at import time (`tools/jupiter_quote.py:14-19`). The test then patches `mod.requests.get` (`tests/test_tools_cli.py:68`). `requests` is not in the proposed dependency set, so `uv run pytest -q` fails and SC5 cannot pass. [VERIFIED: code read; `tests/test_tools_cli.py:25-29`, `:68`]
**How to avoid:** add `requests` to the dev group only, pinned, with a comment that it is removed with `tools/` in Phase 2 (MIGRATION row 64 rewrites this file). Do not skip or delete the test (that narrows scope). Open Question Q2.

### Pitfall 5: Dockerfile draft cannot run the R50 command
**What goes wrong:** the R50 command reads `/app/tests/fixtures/replay/smoke`, but the FOUNDATION_STACK Dockerfile copies only `pyproject.toml`, `uv.lock`, `README.md`, `src`, `prompts-assembled` (FOUNDATION_STACK 3.3 lines 298-312). The replay fails inside the image.
**How to avoid:** `COPY tests/fixtures/replay/smoke /app/tests/fixtures/replay/smoke` (read-only, no secrets) and a root `.dockerignore` that excludes `vendor/`, `.git`, `var/`, `.env`, `.planning/` and `tests/` except that fixture path.

### Pitfall 6: `restart: unless-stopped` with a one-shot command
**What goes wrong:** the R50 replay exits 0 after one cycle; with `restart: unless-stopped` Compose restarts it in a loop, so `docker compose up pumpgrok` never reaches a stable healthy state. FOUND-003 text still says "starts the desk ... compose healthcheck passes". Open Question Q1.
**How to avoid:** for Phase 1 drop the restart policy (or use `restart: "no"`), and let the orchestrator confirm SC4 as reworded by R50.

### Pitfall 7: `.env.example` carries superseded values
**What goes wrong:** FOUNDATION_STACK 3.5 still contains `PUMPGROK_DATA__API_KEY=<pumpportal-key-or-empty>` (line 378, R45 forbids a trade key) and `PUMPGROK_JUPITER__QUOTE_URL=https://lite-api.jup.ag/swap/v1/quote` (line 379, R44 replaces it).
**How to avoid:** drop both lines; the x.ai model names at lines 386-387 (`grok-4-fast`, `grok-4`) are retired (V-10, R48); omit the Grok section in Phase 1 or use `grok-4.3` and `grok-4.20-0309-non-reasoning` (R48). The `.env.example` G-3 check must pass on placeholders only.

### Pitfall 8: Ownership gaps and bare-pattern matching
**What goes wrong:** G-1 self-test fails on `banner.jpg` (verified). Bare-pattern rules also match in vendor and tools trees (Pattern 6).
**How to avoid:** add `banner.jpg`; place vendor and tools rules after the root-file rules; keep the self-test.

### Pitfall 9: `check.sh` still checks vendor paths
**What goes wrong:** `scripts/check.sh` requires `vendor/grokbot-pumpfun/src/pipeline.py` and `vendor/grokbot-pumpfun/PUMPGROK.md` (`scripts/check.sh:117-119`). STRUCT-001 requires the rewrite without vendor paths.
**How to avoid:** replace that block with `docs/VENDOR_PIN.md` (the moved pin note). Keep the emoji check (it scans `**/*.md` excluding `vendor/`), the frontmatter checks, the hermes executability check and the constitution phrase check. The `your-org` warning stays as an allowlist until STRUCT-007.

### Pitfall 10: Emoji and check.sh on the planning docs
**What goes wrong:** `check.sh` scans every `**/*.md` (excluding `vendor/`), including `.planning/**`. Non-ASCII symbols in the U+2600-U+27BF block (for example check marks) fail the emoji regex in `scripts/check.sh:140-146`. Keep planning and docs ASCII.

### Pitfall 11: Crossing the `uv` version
**What goes wrong:** the local `uv` is 0.11.26 (`uv --version`). A lock generated by it may differ from what CI (0.13.4) produces.
**How to avoid:** generate `uv.lock` with `uvx --from uv==0.13.4 uv lock` (verified this works: `uv 0.13.4` ran `uv lock` and `uv sync --frozen --group dev` in the probe). CI and Docker use 0.13.4 as well.

### Pitfall 12: mypy --strict on settings
An unannotated `settings_customise_sources` fails `--strict` (verified). Annotate it with the pydantic types above.

## Code Examples

### Forbidden-name and unknown-key refusal (skeleton; implement in config/settings.py)
```python
# Source: derived from verified behaviour (Pitfalls 1-3); names from hermes/profiles.yaml:18-23 and CONTEXT
FORBIDDEN_SUBSTRINGS = (
    "PRIVATE_KEY",
    "SECRET_KEY",
    "SEED",
    "MNEMONIC",
    "PHANTOM",
    "WALLET_SECRET",
    "KEYPAIR",
)
EXEMPT_ENV = frozenset({"PUMPGROK_REPLAY__SEED"})


def refuse_forbidden_env(environ: Mapping[str, str]) -> list[str]:
    bad = []
    for name in environ:
        if name in EXEMPT_ENV:
            continue
        upper = name.upper()
        if any(s in upper for s in FORBIDDEN_SUBSTRINGS):
            bad.append(name)  # report the NAME only, never the value
    return bad
```

### Append (skeleton; ledger/store.py)
```python
# Source: paper-engine.md:282-313 schema and hash rule; BEGIN IMMEDIATE verified
def append(self, event: EventRecord) -> int:
    with self._conn_lock:
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            prev = self._conn.execute(
                "SELECT seq, hash FROM events ORDER BY seq DESC LIMIT 1"
            ).fetchone()
            seq = (prev[0] + 1) if prev else 1
            prev_hash = prev[1] if prev else "0" * 64
            body = canonical_json(
                {
                    "prev_hash": prev_hash,
                    "seq": seq,
                    "ts_utc": event.ts_utc,
                    "source": event.source,
                    "correlation_id": event.correlation_id,
                    "type": event.type,
                    "payload_json": event.payload_json,
                    # recommended addition, Open Question Q3:
                    "idempotency_key": event.idempotency_key,
                }
            )
            h = hashlib.sha256(body.encode()).hexdigest()
            self._conn.execute(
                "INSERT INTO events (seq, ts_utc, source, correlation_id, idempotency_key, type, payload_json, prev_hash, hash) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    seq,
                    event.ts_utc,
                    event.source,
                    event.correlation_id,
                    event.idempotency_key,
                    event.type,
                    event.payload_json,
                    prev_hash,
                    h,
                ),
            )
            self._conn.execute("COMMIT")
            return seq
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
```

### Replay verification (skeleton)
```python
# Source: CONTEXT FOUND-012 / INV-R-30: mismatch exits 4, no ledger is created
def verify_manifest(dataset: Path) -> None:
    manifest = json.loads((dataset / "manifest.json").read_text())
    for name, digest in manifest["sha256"].items():
        if hashlib.sha256((dataset / name).read_bytes()).hexdigest() != digest:
            raise CorruptFixture(name)  # CLI maps to exit 4 before opening any ledger
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|---|---|---|---|
| `websockets.connect` top-level import | `websockets.asyncio.client.connect` | websockets 14.0 | Use the new path (M-1) |
| pytest-asyncio `event_loop` fixture | `asyncio_default_fixture_loop_scope` | pytest-asyncio 1.0 | Set explicitly (V-9) |
| pydantic-settings 2.16.0 | 2.16.1 (CLI regressions fixed) | 2026-10-20 | Floor raised (V-1) |
| uv 0.13.3 | 0.13.4 | 2026-10-20 | Installer and uv_build floor (V-2) |
| `uv export` includes project | `--no-emit-project` | uv audit path | Required for pip-audit (V-4) |
| Jupiter lite-api v1 quote | `api.jup.ag/swap/v2/order` (quote-only) | R44 | Not in Phase 1 files |

**Deprecated / to remove in Phase 1:** `default=str` in `canonical_json` (interfaces.md:256); the PumpPortal key line and lite-api URL in `.env.example`; `requirements.txt`/`requirements-dev.txt` are NOT touched in Phase 1 (they belong to vendor, batch 5).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `requests` as a dev-only pinned dependency is acceptable until Phase 2 removes `tools/` | Pitfall 4 | Orchestrator may prefer another approach; SC5 blocked until decided |
| A2 | Keeping the replay Docker command one-shot and dropping `restart` satisfies FOUND-003 as reworded by R50 | Pitfall 6 | FOUND-003 text still says `up` healthy |
| A3 | Including `idempotency_key` in the hash input is the right fix to the open design item | Pattern 2, code example | Ledger hash rule changes before first write; must be documented in paper-engine.md 3.2 |
| A4 | `journal_note` `note_kind` enum follows paper-engine.md 3.3 (no `halt`) | Open Question Q4 | ROSTER section 8 includes `halt`; schema generated from one of them |
| A5 | The 15 SUS packages are safe to install after one human checkpoint | Legitimacy Audit | Supply-chain risk if an identity is wrong; the source repos listed match the canonical projects |
| A6 | Phase 1 needs no prompt content beyond what `agents/*.md` already carry, migrated into `prompts/*.xml` | Open Question Q6 | Agents' prose changes shape; generated files differ from today |
| A7 | `ruff`/`mypy`/`pytest` configs in FOUNDATION_STACK 3.1 are otherwise correct | Standard Stack | Lint noise on the port; not verified by running the full toolchain |

**If this table is empty:** not applicable; items above need confirmation.

## Open Questions

1. **Compose restart and FOUND-003 wording (Q1)**
   - What we know: R50 makes the container one-shot; FOUND-003 text requires `docker compose up pumpgrok` to start a healthy desk.
   - What's unclear: whether `compose up` is still expected to show `healthy`.
   - Recommendation: keep SC4 as reworded (`docker compose run --rm pumpgrok` exits 0); drop `restart` for Phase 1; the healthy long-running check moves to Phase 5 (R50).

2. **`requests` for the legacy CLI test (Q2)** - see Pitfall 4. Recommendation: dev-group pin, removed in Phase 2.

3. **Idempotency key in the hash (Q3)** - recommend including it; the orchestrator must approve the paper-engine.md 3.2 change before the first ledger write.

4. **`journal_note` note_kind enum (Q4)**
   - What we know: paper-engine.md:339 lists `lead/whale/social/signal/verdict/safety_report/review/ticket/note`; ROSTER.md section 8 lists the same plus `halt`. MIGRATION row uses `cycle` (not in either).
   - Recommendation: use the paper-engine list plus `halt` only if the ROSTER owner confirms; the Phase 1 skip note uses `note` (CONTEXT).

5. **Repository URL (Q5)** - `git remote -v` shows `swcstudiospace/PumpGrok`; FOUNDATION_STACK U-9 assumes `swcstudio/pumpgrok`. Pick one before writing `[project.urls]`.

6. **Prompt sources and placeholders (Q6)**
   - What we know: `prompts/` does not exist; `agents/` has 8 seat files (chief, exit, risk, rug, scout, shill, sniper, whale) and no `signal.md` or `journal.md`. The precedent `assemble-prompts.sh` and `generate-templates.py` read `grokbot/rosters/*.json` and substitute `{{DESK_GATEWAY_URL}}`, `{{SEAT_UUID:<SEAT>}}`, `{{DESK_CHANNEL_ID}}`, none of which exists before the Phase 3 gateway.
   - Recommendation: retarget the scripts to `contracts/tool-rosters/*.yaml`; either drop unused placeholders from the sources or provide a single minimal roster JSON with `DESK_ROSTER_VERSION`. FOUND-009 still requires no `{{...}}` left. Seed `prompts/bot-0N-<seat>.xml` from the existing `agents/*.md` bodies, and create `agents/signal.md` and `agents/journal.md` from the same generator.

7. **Tool name regex conflict (Q7)** - `interfaces.md:338` `ToolSpec.name` pattern is `^[a-z][a-z0-9]*\.[a-z][a-z0-9_]*$` (exactly one dot). R19 and FOUNDATION_STACK G-7 require `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$`. Use the R19 pattern in both the gate and `ToolSpec`.

8. **`execution/live/` placement (Q8)** - CONTEXT places it in Phase 1; MIGRATION batch 4 does not. Follow CONTEXT; update the batch table.

9. **httpx and websockets: runtime or dev (Q9)** - CONTEXT lists them as declared imports; in Phase 1 only `tests/conftest.py` imports them. Recommendation: runtime dependencies (they are the Phase 2 runtime; avoids a second lock change).

10. **SUS checkpoint granularity (Q10)** - see Legitimacy Audit. Recommendation: one checkpoint before `uv lock`.

11. **Ownership for `banner.jpg` (Q11)** - proposed owner bot-00-chief (README neighbour). Confirm.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | all | yes | 3.12.3 at `/usr/bin/python3.12` (uv `sync` used it) | - |
| uv | sync, lock, all `uv run` | yes, version mismatch | local 0.11.26; `uvx --from uv==0.13.4 uv` works (verified) | use `uvx --from uv==0.13.4` or `uv self update` |
| uv_build | build backend | via PyPI | 0.13.4 (module-root build verified in probe) | - |
| make | Makefile targets | yes | `/usr/bin/make` | - |
| bash | scripts | yes | `/usr/bin/bash` | - |
| PyPI network | `uv lock`, `pip-audit` | yes | 200 from pypi.org; pip-audit "No known vulnerabilities found" for probe runtime pins | - |
| Docker daemon | SC4 | yes | Server 29.6.2 (`docker version`) | - |
| Docker Compose | SC4 | yes | v5.3.1; `env_file` `required: false` validated with `docker compose config --quiet` (exit 0) | - |
| Registry pulls | Dockerfile FROM | yes | `python:3.12-slim`, `ghcr.io/astral-sh/uv:0.13.4`, `busybox:1.36` pulled | - |
| origin/main | `check_secrets.py --base origin/main` | yes | `origin/main` resolves (`d16963a`) | - |
| gsd_run | legitimacy seam | yes | `/usr/local/bin/gsd_run` | - |
| pre-commit, actionlint | local hooks, workflow lint | not checked | - | validate YAML with pyyaml only, and say so |

**Missing dependencies with no fallback:** none found.
**Missing dependencies with fallback:** uv version (use uvx 0.13.4).

## Validation Architecture

> Included: `workflow.nyquist_validation` is absent in `.planning/config.json`, so it is treated as enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.1.1 + pytest-asyncio 1.4.0 (auto mode), plus stdlib unittest for `tests/test_tools_cli.py` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (to create in Wave 0) |
| Quick run command | `uv run pytest -q tests/<file>::<test>` |
| Full suite command | `uv run pytest -q` (product and `ci/tests`) |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File exists? |
|--------|----------|-----------|-------------------|-------------|
| FOUND-001 | `uv sync --frozen` on clean checkout | smoke | `uv sync --frozen --group dev` | no, Wave 0 (pyproject, uv.lock) |
| FOUND-002 | canonical make targets | integration | `make lint typecheck test audit` | no, Wave 0 (Makefile) |
| FOUND-003 | image builds, runs replay | smoke | `docker compose config --quiet && docker compose build pumpgrok && docker compose run --rm pumpgrok` | no |
| FOUND-004 | loader precedence, refusals | unit | `uv run pytest -q tests/config/` | no, Wave 0 |
| FOUND-005 | registry I1-I4; LIVE_WRITE refused | unit | `uv run pytest -q tests/core/` | no, Wave 0 |
| FOUND-006 | ownership manifest validates | gate | `python3 ci/gates/check_ownership.py --validate-manifest` | no (manifest to write) |
| FOUND-007 | gate self-tests | gate | `python3 -m pytest ci/tests/ -q` | no (port) |
| FOUND-008 | contracts and schemas, G-7 | gate | `python3 ci/gates/check_desk_integrity.py --repo .` | no |
| FOUND-009 | prompts assemble, agents regenerate | gate | `bash scripts/assemble-prompts.sh --check && python3 scripts/generate-templates.py --check` | no |
| FOUND-010 | workflows exist and parse | static | `python3 -c "import yaml,glob; [yaml.safe_load(open(p)) for p in glob.glob('.github/workflows/*.yml')]"` | no |
| FOUND-011 | docs present, check.sh passes | gate | `./scripts/check.sh` | partial (rewrite) |
| FOUND-012 | network blocked; replay clock/rng/fixtures; FaultInjector | unit | `uv run pytest -q tests/test_network_block.py tests/replay/` | no |
| FOUND-013 | skip cycle, JournalNote count 1, doctor | e2e | SC2 command below | no |
| STRUCT-001 | pyc/tissue removed; pin doc | static | `git ls-files | grep -E '\.pyc$|tissue' ; test -f docs/VENDOR_PIN.md` | no |
| STRUCT-008 | no wallet/Jito field | static | `! grep -rn -e JitoConfig -e wallet_private_key src/pumpgrok` | no |
| OBS-001 | JSON logs, redaction | unit | `uv run pytest -q tests/test_logging.py::test_log_redaction` | no, Wave 0 (name from REQUIREMENTS) |
| OBS-002 | correlation chain | unit | `uv run pytest -q tests/test_correlation.py::test_correlation_id_chain` | no, Wave 0 |
| SEC-001 | no secrets, G-3 | gate | `python3 ci/gates/check_secrets.py --base origin/main` | no (port) |
| SEC-002 | env-only secrets; URL key refusal | unit | `uv run pytest -q tests/config/test_secret_refusal.py` | no |

### Success Criteria -> Automated Command

| SC | Command(s) | Pass condition |
|----|-----------|----------------|
| SC1 | `uv sync --frozen && make lint typecheck test audit` | exit 0 |
| SC2 | `uv run pumpgrok run --mode paper --once --replay tests/fixtures/replay/smoke`; then `uv run python -c "import sqlite3; print(sqlite3.connect('var/replay/smoke/ledger.sqlite').execute(\"select count(*) from events where type='JournalNote' and source='replay'\").fetchone()[0])"` | exit 0; prints `1` |
| SC3 | `python3 ci/gates/check_ownership.py --validate-manifest`; `python3 ci/gates/check_desk_integrity.py --repo .`; `python3 ci/gates/check_secrets.py --base origin/main`; `python3 -m pytest ci/tests/ -q` | each exit 0 |
| SC4 | `docker compose config --quiet`; `docker compose build pumpgrok`; `docker compose run --rm pumpgrok`; `./scripts/check.sh` | each exit 0 (R51: if daemon unreachable, record exact error) |
| SC5 | `uv run pytest -q`; `! grep -rn -e JitoConfig -e wallet_private_key src/pumpgrok`; `test ! -d config` | exit 0; grep prints nothing; dir absent |

### Sampling Rate
- **Per task commit:** the single test file or gate for the task (`uv run pytest -q <file>`, or the gate script).
- **Per wave merge:** `uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest -q`.
- **Phase gate (once, after all waves):** SC1-SC5 in order. Docker commands (SC4) take minutes and run once here.

### Wave 0 Gaps
- [ ] `pyproject.toml`, `uv.lock` (generated with uv 0.13.4), `.python-version`, `Makefile`, `.gitignore`
- [ ] `tests/conftest.py` (httpx and websockets guard), `tests/fixtures/replay/smoke/manifest.json` plus events (hand-authored, sha256 listed)
- [ ] `tests/test_network_block.py`, `tests/config/`, `tests/core/`, `tests/replay/`, `tests/test_logging.py`, `tests/test_correlation.py`
- [ ] Static guard test: `tests/safety/test_virtual_time_only.py` (allowlist `replay/clock.py`) and `tests/safety/test_no_uuid.py`
- [ ] `ci/gates/*.py` port, `ci/tests/test_gates.py` port, `ownership.yaml`, `.receipts/<seat>/.gitkeep` x10
- [ ] Framework install: `uv sync --frozen --group dev` (after lock)

## Security Domain

Required: `security_enforcement` is absent, so treated as enabled. ASVS level 1, block on high.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no operator login in Phase 1) | - |
| V3 Session Management | no | - |
| V4 Access Control | yes (live gate, registry grants) | `ToolRegistry.find` I1-I4; LiveGate fail-closed |
| V5 Input Validation | yes | pydantic `extra="forbid"`; env unknown-name refusal; loader errors without values |
| V6 Cryptography | yes (hash chain) | `hashlib.sha256` only; no custom crypto; HMAC is Phase 4 (GOLIVE-001) |
| V7 Error Handling and Logging | yes | JSON log with RedactionFilter; exceptions print names/types only |
| V8 Data Protection | yes | no secrets in repo or image; `.env` gitignored; G-3 |
| V9 Communications | yes (test-time) | network blocked in tests; no live transport in Phase 1 |
| V14 Configuration | yes | env-only secrets; forbidden names; no `config/` at root |

### Known Threat Patterns for Python config and ledger

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Secret echoed in validation error | Information disclosure | Format errors from `loc` and `type` only (verified leak) |
| Typo'd or forbidden env var silently applied | Tampering / elevation | Explicit `PUMPGROK_*` unknown-name refusal; forbidden substring scan (verified gap) |
| Mode raised to live through env | Elevation | Refuse `PUMPGROK_EXECUTION__MODE`; live gate exit 3 |
| Ledger row edited or deleted | Tampering | Append-only triggers (verified); hash chain; INCONSISTENT in Phase 4 |
| Replay with altered fixture | Tampering | sha256 manifest, exit 4 before any ledger write |
| Non-deterministic ids enabling forgery | Spoofing | Ids only from `IdFactory` (no `uuid`, `random`, `secrets`) |
| Compromised dependency | Tampering | Lock file, `pip-audit --strict` (clean on runtime pins), 12 SUS packages checkpointed |
| Secret in image | Information disclosure | No `.env` copied; `.dockerignore`; non-root user |

## Sources

### Primary (HIGH confidence)
- PyPI JSON API, 2026-10-21: versions and release dates for uv, uv-build, pydantic, pydantic-settings, httpx, respx, websockets, tenacity, prometheus-client, pyyaml, ruff, mypy, pytest, pytest-asyncio, pip-audit, types-PyYAML [VERIFIED].
- Local probes in `/tmp/probe` (outside repo): uv_build module-root build and `uv run` (uv 0.11.26 and 0.13.4); `uv export --no-emit-project`; pydantic-settings TOML list and env nesting; unknown-env and forbidden-env behaviour; ValidationError contents; sqlite WAL and append-only trigger; httpx network block and MockTransport; ULID spec vector; `pip-audit --strict` on runtime pins; `docker compose config --quiet`; registry pulls.
- `docs/FOUNDATION_STACK.md` sections 2, 3.1-3.7, 4, 5.1-5.6, 6, 7 (read this session) [CITED].
- `docs/design/interfaces.md` lines 52-404, 589-683, 689-1003 (read) [CITED].
- `docs/design/paper-engine.md` lines 263-345, 434-470 (read) [CITED].
- `docs/MIGRATION_MAP.md` lines 28-50, 131-175, 545-606 (read) [CITED].
- `docs/ROSTER.md` lines 355-414, 415-600, 860-910 (read); ownership simulation over `git ls-files` [VERIFIED].
- `.planning/research/STACK.md` V-1..V-10 (read) [CITED].
- `hermes/profiles.yaml:18-24` (read) [VERIFIED: quoted names PRIVATE_KEY, SECRET_KEY, SEED, MNEMONIC, PHANTOM, WALLET_SECRET].
- `scripts/check.sh` lines 1-150 (read), `tests/test_tools_cli.py` lines 1-70 (read), `tools/jupiter_quote.py:14-22` (read) [VERIFIED].
- Precedent `~/src/repos/programming-desk/ci/gates/check_ownership.py:29-75,86-140`, `check_secrets.py:25-80,152-155`, `check_desk_integrity.py` constants `:29-62`, `run_all.py` (read) [VERIFIED].
- `gsd_run query package-legitimacy check` outputs (read) [VERIFIED].

### Secondary (MEDIUM confidence)
- `docs/design/paper-engine.md` event table (`:321-340`) and the `journal_note` row of `docs/ROSTER.md` section 8 (note_kind list) - the two sources differ (Q4).

### Tertiary (LOW confidence)
- `uv_build` repository URL reported by the legitimacy seam (`pypi.org/project/uv/`) - unverified; Q11 checkpoint.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - versions from PyPI JSON on the research date; dependency behaviour probed.
- Architecture: HIGH for config, ledger, ids and network guard (probed); MEDIUM for gate and prompt ports (read the precedent, not run).
- Pitfalls: HIGH for the probed items (1-3, 12); HIGH by code read for 4-5, 8-10; MEDIUM for 6 (depends on Q1 answer).

**Research date:** 2026-10-21
**Valid until:** 2026-11-20 for pins (30 days; uv and pydantic-settings released within 2 days of this date - re-check before `uv lock`); the design-document facts are valid until those files change.
