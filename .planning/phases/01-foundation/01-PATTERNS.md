# Phase 1: Foundation - Pattern Map

**Mapped:** 2026-10-21
**Inputs:** 01-CONTEXT.md (binding decisions, R16-R51), 01-RESEARCH.md (verified mechanics)

## How to read this map

- An **analog** is a file that already exists in this repo or in the programming-desk precedent
  (`~/src/repos/programming-desk`, shape only, never imported). Line numbers were checked with
  grep or sed on 2026-10-21 unless marked "approx".
- Where no code precedent exists, the design doc is the spec and is cited instead:
  `docs/design/interfaces.md` (IF), `docs/design/paper-engine.md` (PE), `docs/FOUNDATION_STACK.md` (FS).
- `vendor/grokbot-pumpfun/` is the legacy engine. Copy its shape where marked. Never copy its money
  types, wallet fields or Jito config (see Anti-patterns).
- Match: exact (same role and flow), role (same role, different flow), partial (same mechanism,
  different domain), none (spec only).

## File Classification

### Toolchain, container, CI

| New/Modified File | Role | Flow | Closest Analog | Match |
|---|---|---|---|---|
| `pyproject.toml` | config | build | `vendor/grokbot-pumpfun/pyproject.toml`; FS 3.1 draft | role |
| `.python-version`, `uv.lock` | config | build | none (generated, uv 0.13.4) | none |
| `Makefile` | config | batch | `vendor/grokbot-pumpfun/Makefile` (`help` grep over `##`); FS 3.2 | role |
| `.gitignore` | config | batch | `vendor/grokbot-pumpfun/.gitignore` (config.yaml, .env, state/, logs/) | partial |
| `.dockerignore` | config | batch | `vendor/grokbot-pumpfun/.dockerignore` | exact |
| `Dockerfile` | config | build | `vendor/grokbot-pumpfun/Dockerfile` (non-root user, HEALTHCHECK, STOPSIGNAL); FS 3.3 | role |
| `docker-compose.yml` | config | batch | `vendor/grokbot-pumpfun/docker-compose.yml`; FS 3.4 | role |
| `.env.example` | config | batch | `vendor/grokbot-pumpfun/.env.example` (placeholders only) | role |
| `.github/workflows/ci.yml` | config | event | `vendor/grokbot-pumpfun/.github/workflows/ci.yml` (matrix; docker negative check) | role |
| `.github/workflows/gates.yml`, `security-pr.yml` | config | event | `programming-desk/.github/workflows/gates.yml`, `security-pr.yml` | role |
| `scripts/check.sh` (exists, keep) | utility | batch | itself (stdlib Python heredoc) | exact |

### Config, core, ledger, replay, logging, execution

| New/Modified File | Role | Flow | Closest Analog | Match |
|---|---|---|---|---|
| `src/pumpgrok/config/settings.py` | config | startup | `vendor/grokbot-pumpfun/src/models.py` (`ConfigError`, `mask`, `PLACEHOLDER_MARKERS`) | partial |
| `src/pumpgrok/config/overlays/{dev,paper,live}.toml` | config | batch | none (vendor config is YAML) | none |
| `src/pumpgrok/cli.py`, `doctor.py` | controller | request-response | `vendor/grokbot-pumpfun/src/pipeline.py` (`parse_args`, `--check`, `main`) | role |
| `src/pumpgrok/core/atomic_write.py` | utility | file-I/O | `vendor/grokbot-pumpfun/src/state.py` (`StateStore.save`) | exact |
| `src/pumpgrok/core/bot.py` (RiskBudget) | model | transform | IF 728-745; vendor `RiskConfig` (layout only; vendor uses float) | partial |
| `src/pumpgrok/core/ids.py` | utility | transform | IF 157-183 (`IdFactory`, `_crockford`) | none |
| `src/pumpgrok/core/registry.py`, `interfaces.py`, `approvals.py`, `__init__.py`, other core modules | service/model | request-response | IF sections 2.1-2.9, 923- (`ToolRegistry.find`) | none |
| `src/pumpgrok/ledger/store.py` | repository | append-only | none for SQLite; PE 282-316 (schema, triggers, hash rule); `state.py` for file atomicity | partial |
| `src/pumpgrok/ledger/events.py` | model | event | `vendor/grokbot-pumpfun/src/log.py` (`buy`, `skip`, `close`, `_write`); PE 317-343 (18 types) | partial |
| `src/pumpgrok/replay/clock.py`, `rng.py` | utility | transform | none; PE 449-465 | none |
| `src/pumpgrok/replay/fixtures.py` | utility | file-I/O | `vendor/grokbot-pumpfun/src/log.py` (`read_log`) for reader; sha256 manifest is new | partial |
| `tests/fixtures/replay/smoke/*` | fixture | batch | none; hand-authored with sha256 manifest | none |
| `src/pumpgrok/logging/json.py` | middleware | transform | `vendor/grokbot-pumpfun/src/log.py` (`setup_logging`); FS 5.1-5.2 | partial |
| `src/pumpgrok/logging/redaction.py` | middleware | transform | `programming-desk/ci/gates/check_secrets.py` (`SECRET_NAME_RE`, `_redact`) | partial |
| `src/pumpgrok/execution/live/live_gate.py` | guard | request-response | `vendor/grokbot-pumpfun/src/models.py` (live precondition list); PE 752-790 | role |
| `src/pumpgrok/execution/live/live_adapter.py` | adapter stub | request-response | IF 611-620 (`LiveAdapterStub`) | none |

### Tests

| New/Modified File | Role | Flow | Closest Analog | Match |
|---|---|---|---|---|
| `tests/conftest.py` (network block) | test | batch | `vendor/grokbot-pumpfun/conftest.py` (sys.path only); block is new (RESEARCH Pattern 4) | partial |
| `tests/test_tools_cli.py` (keep until Phase 2) | test | batch | itself (stdlib unittest) | exact |
| `tests/config/test_settings.py` | test | batch | `vendor/grokbot-pumpfun/tests/test_config.py` (example rejected, good passes, bad values) | exact |
| `tests/core/*`, `tests/replay/*`, `tests/ledger/*` | test | batch | `vendor/grokbot-pumpfun/tests/test_state.py`, `test_log.py` (style) | partial |
| `tests/safety/test_static_guards.py` | test | batch | none; PE 441; RESEARCH Pattern 5 | none |
| `tests/test_logging.py`, `tests/test_correlation.py`, `tests/test_network_block.py` | test | batch | `vendor/grokbot-pumpfun/tests/test_log.py` (style) | partial |

### Gates, desk tooling, prompts, contracts (ported from precedent)

| New/Modified File | Role | Flow | Closest Analog | Match |
|---|---|---|---|---|
| `ownership.yaml` | config | batch | `programming-desk/ownership.yaml`; `docs/ROSTER.md:427-840` (R36) | exact |
| `ci/gates/check_ownership.py` | gate | batch | `programming-desk/ci/gates/check_ownership.py` (`_match` :36, `resolve_owner` :62, `main` :115) | exact |
| `ci/gates/check_secrets.py` | gate | batch | same dir `check_secrets.py` (`PATTERNS` :29, `ALLOWLIST_MARKER` :26, `SECRET_NAME_RE` :56, `_redact` :123, `changed_files` :152, `staged_files` :158, `main` :164) | exact |
| `ci/gates/check_receipt.py` | gate | batch | `check_receipt.py` (`BYPASS_PATTERNS` :26, `REQUIRED_FIELDS` :48, `SEAT_ID_RE` :57) | exact |
| `ci/gates/check_contracts.py`, `check_rollback.py` | gate | batch | precedent files (294 and 177 lines) | exact |
| `ci/gates/check_desk_integrity.py` | gate (G-7) | batch | precedent (`ROSTERS_DIR` :31, `ROSTER_MIN_TOOLS` :41, `TOOL_NAME_RE` :46, `SEAT_RE` :47, `TEMPLATE_FORBIDDEN` :66-77) | exact |
| `ci/gates/run_all.py` | controller | batch | precedent `run_all.py` (`run()` subprocess, summary) | exact |
| `ci/tests/test_gates.py`, `test_security_workflows.py` | test | batch | precedent (temp git repo fixtures, real receipts) | exact |
| `.receipts/bot-0N-*/.gitkeep` (x10) | config | batch | precedent `.receipts/` layout | exact |
| `contracts/tool-rosters/`, `contracts/tool-packs/` | config | batch | precedent `contracts/` (`check_desk_integrity.py:31-32`) | role |
| `contracts/events/<snake>.schema.json` (18, generated) | config | batch | none; generate from `ledger/events.py` | none |
| `prompts/_shared/core-directives.xml`, `prompts/<SEAT>.xml` | config | batch | precedent `prompts/` layout | role |
| `scripts/assemble-prompts.sh`, `scripts/generate-templates.py` | utility | batch | precedent scripts (header and `--check` mode) | exact |
| `AGENTS.md` (keep marker blocks), `SECURITY.md`, `docs/*.md` | docs | batch | `AGENTS.md` (335 lines, 7 GSD marker blocks) | role |

## Pattern Assignments

### A. Settings loader (FOUND-004, STRUCT-008, SEC-002)

**Analog:** `vendor/grokbot-pumpfun/src/models.py` lines 399-441 (`PLACEHOLDER_MARKERS`,
`ConfigError`, `mask`). Keep the idea of each. Replace its hand-rolled env table
(`ENV_OVERRIDES`, around line 403) with pydantic-settings.

```python
# vendor/grokbot-pumpfun/src/models.py:423 and :434 (kept idea: exit with a list of problems;
# never show a secret value)
class ConfigError(RuntimeError):
    """Config is not fit to start. The list of problems is the argument."""


def mask(secret: str) -> str:
    """How a secret may appear in logs: enough to recognise, not enough to use."""
```

Required skeleton (RESEARCH Pattern 1, verified on pydantic-settings 2.16.1; annotations are
required for `mypy --strict`):

```python
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
        files.append(Path(config_file))  # later file wins
    return (init_settings, env_settings, TomlConfigSettingsSource(settings_cls, toml_file=files))
```

Precedence (CONTEXT Locked): CLI > env > `PUMPGROK_CONFIG` > overlay (`PUMPGROK_PROFILE`,
default `paper`) > defaults. Mode: `--mode` > `PUMPGROK_MODE` > TOML `execution.mode`.

Guards the library does not provide. Each needs a test in `tests/config/test_settings.py`:

| Input | Required result | Source |
|---|---|---|
| `PUMPGROK_BOGUS=1`, `PUMPGROK_RISK__BOGUS=1` | exit 1, unknown key name only | RESEARCH Pitfall 1 |
| `PUMPGROK_EXECUTION__MODE=live` | startup error | RESEARCH Pitfall 2 |
| `PUMPGROK_RISK__MAX_TRADE_FRACTION=abc` | exit 1; print `loc` and `type` only | RESEARCH Pitfall 3 |
| any env name containing PRIVATE_KEY, SECRET_KEY, SEED, MNEMONIC, PHANTOM, WALLET_SECRET, KEYPAIR (case-insensitive) | exit 1 | `hermes/profiles.yaml:18-24` |
| `PUMPGROK_REPLAY__SEED` | allowed (exact-name exemption) | CONTEXT Locked |
| URL value containing `api-key=`, `key=` or `token=` | exit 1 | CONTEXT Locked |
| unknown profile | exit 1 | CONTEXT Locked |

Forbidden-name list follows the gate style of `check_secrets.py` (`PATTERNS`, `SECRET_NAME_RE`
at :56). Do not echo `ValidationError.input`: map errors to `(loc, type)`.

### B. Risk budget (R20, R28, INV-C-06)

**Analog:** `vendor/grokbot-pumpfun/src/models.py` `RiskConfig` (layout only). Do NOT copy its
`float` fields. Use IF 728-745 exactly, with a validator added:

```python
class RiskBudget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_trade_fraction: Decimal = Field(default=Decimal("0.02"), ge=0, le=1)
    max_token_fraction: Decimal = Field(default=Decimal("0.05"), ge=0, le=1)
    daily_loss_halt_fraction: Decimal = Field(
        default=Decimal("0.05"), ge=0, le=1
    )  # validator: <= 0.05
    drawdown_halt_fraction: Decimal = Field(default=Decimal("0.15"), ge=0, le=1)
    max_open_positions: int = Field(default=3, ge=0)
    max_trades_per_day: int = Field(default=20, ge=0)
    liquidity_floor_multiple: int = Field(default=10, ge=1)
    partial_fill_fraction: Decimal = Field(default=Decimal("0.02"), gt=0, le=1)
```

### C. Atomic writer (`core/atomic_write.py`)

**Analog (exact):** `vendor/grokbot-pumpfun/src/state.py:76-86` `StateStore.save`: tmp file in the
same directory, `json.dump`, `flush`, `os.fsync`, `os.replace`, unlink tmp on failure. Keep the
order. Change: the vendor swallows `OSError` so trading continues; the ledger must fail loudly.
Tests to mirror: `vendor/grokbot-pumpfun/tests/test_state.py` (create parent, no temp left
behind, `clear`).

### D. Ledger store (FOUND-013, R26, R28, R32)

**Analog:** none for SQLite. Spec: PE 282-316 (schema, WAL pragmas, append-only triggers, hash rule).
Append pattern (RESEARCH Pattern 2, verified):

```python
conn = sqlite3.connect(path, isolation_level=None)  # explicit transactions
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("BEGIN IMMEDIATE")
# read head (seq, hash); prev_hash = 64 zeros for seq 1; hash = sha256(canonical_json({...}))
# INSERT row; COMMIT - all in one transaction
```

Rules:
- The row hash covers `prev_hash, seq, ts_utc, source, correlation_id, type, payload_json`
  (PE 316, R28).
- `canonical_json`: sorted keys, `separators=(",", ":")`, floats rejected. Do NOT copy
  `default=str` from IF:253.
- Replay ledgers are recreated each run (remove the old file first).

### E. Event models (`ledger/events.py`, 18 types, R32)

**Analog (partial):** `vendor/grokbot-pumpfun/src/log.py` builds one record per event kind
(`buy`, `skip`, `close`) and writes one JSON line per record. Port the one-builder-per-kind
layout, with one pydantic model per type. Spec: PE 317-343 (type table). Rules: CamelCase class
names; money as `<x>_lamports: int` or `<x>_units: int`; prices as `Decimal` strings with the
`price_` prefix. The vendor logger takes `float` prices (`log.py:102-103`); do not copy that.
`journal_note.note_kind`: PE and ROSTER disagree on `halt` (RESEARCH Q4); use PE and record it in the
module docstring.

### F. Ids, correlation, registry (FOUND-005, OBS-001, R29)

**Analog:** none in repo. Spec: IF 157-183.

```python
class IdFactory:
    def __init__(self, clock: Clock, rng: random.Random) -> None:  # type rng tightly, not Any
        self._clock = clock
        self._rng = rng

    def ulid(self) -> str:
        ms = int(self._clock.now() * 1000)
        rand = self._rng.getrandbits(80)
        return _crockford((ms << 80) | rand, 26)
```

`_crockford` and `_CROCKFORD` are IF 165-183 verbatim. CorrelationId is the plain ULID root;
children are `<ulid>.<n>`. `uuid` is banned in `src/pumpgrok`. `ToolRegistry.find` raises
`LiveGateError` for any `LIVE_WRITE` spec (I3) and audits each refusal (I4) (IF 923-).

### G. Live gate and adapter stub (FOUND-005, R21, INV-C-03)

**Analog (role):** `vendor/grokbot-pumpfun/src/models.py` (live-mode check that collects problems
into a list and fails before start, around line 573). Port as `LiveGate.check()` returning the
nine `(id, name, reason)` entries in order (PE 752-790). `run` prints each unmet id as
`[ ] n id reason` and exits 3 before other work. Ids 3, 4, 7, 9 are unmet (need ledger or
confirmation data). Id 8 is always unmet. `LiveAdapterStub` (IF 611-620): every method raises
`LiveGateError` after appending `LiveWriteAttempted`. No wallet-key field anywhere (M-10).

### H. CLI and doctor (FOUND-013, R37)

**Analog (role):** `vendor/grokbot-pumpfun/src/pipeline.py` `parse_args` (around line 504, with
`--check`), `load_and_check` (514), `main` (560). Port the parse/check/main split.

Commands: `pumpgrok run --mode paper --once --replay <dir>` and `pumpgrok doctor`.
Exit codes (CONTEXT Discretion): 0 ok; 1 config; 2 ledger inconsistent (reserved); 3 live refused;
4 corrupt fixture; 5 not implemented (`run` without `--once --replay`). `doctor` marks absent
subsystems `not-yet-implemented` (warning, exit 0).

Skip cycle order: LiveGate check (unmet ids print, paper continues) -> fixture manifest check
(mismatch exits 4 before any ledger file exists, INV-R-30) -> open ledger -> append one
`JournalNote` with `source="replay"` and the cycle ULID -> exit 0.

### I. Logging (OBS-001, OBS-002)

**Analog (partial):** `vendor/grokbot-pumpfun/src/log.py` `setup_logging` (line 30): one
`basicConfig` call to stderr. Keep the single setup call; replace the human format with the JSON
record in FS 5.1 (`ts`, `level`, `logger`, `msg`, `event`, `correlation_id`, `seat`, `ticket_id`,
`mode`, `profile`, `data`; `separators=(",", ":")`, `sort_keys=True`).
`PUMPGROK_LOG_JSON=false` is honoured only when `PUMPGROK_PROFILE=dev`.

**RedactionFilter analog:** `programming-desk/ci/gates/check_secrets.py:123-126`:

```python
def _redact(line: str, secret: str) -> str:
    keep = 4
    masked = secret[:keep] + "*" * max(4, len(secret) - keep) if len(secret) > keep else "****"
    return line.replace(secret, masked).strip()[:160]
```

Apply to `msg` and every string leaf in `data` (FS 5.3). Key-based redaction uses
`SECRET_NAME_RE` (`check_secrets.py:56`) plus `keypair|mnemonic|seed|wallet_secret`.

### J. Replay: clock, rng, fixtures (FOUND-012, R27, INV-R-30)

**Analog for reader (partial):** `vendor/grokbot-pumpfun/src/log.py` `read_log` (around line 197):
tolerant JSONL reader that skips undecodable lines. For fixtures, do NOT skip: a corrupt fixture is
exit 4. Use the shape, raise instead of continue.

Spec for clock and rng: PE 449-465. `WallClock` is the only module allowed `time`, `asyncio.sleep`,
`asyncio.timeout`. `make_rng(seed)` is the only `random.Random(...)` constructor; default seed
`20260101`. The manifest check hashes each listed file with sha256 and raises a typed error that
`cli.py` maps to exit 4.

### K. Static guards and network block (FOUND-012, SC5)

**Analog for conftest:** `vendor/grokbot-pumpfun/conftest.py` (sys.path insert only). Network block
is new: patch `httpx.AsyncHTTPTransport.handle_async_request` and `httpx.HTTPTransport.handle_request`
to raise (RESEARCH Pattern 4, verified; `httpx.MockTransport` still works).

Static guard: AST walk of `src/pumpgrok/**/*.py` rejecting `asyncio.sleep`, `asyncio.timeout`,
`asyncio.wait_for`, `time.time`, `time.monotonic`, `datetime.now`, `import uuid`, `random.random`,
and unseeded `random.Random()`. Allowlist exactly `src/pumpgrok/replay/clock.py` (PE 441).

### L. Gates G-1..G-7 (FOUND-006, 007, 010; SEC-001)

Port `programming-desk/ci/gates/*.py`. Keep script names and CLI (FS section 4). Change constants
only, and add one test per changed constant.

- **G-1 ownership.** `check_ownership.py` `_match` (:36) and `resolve_owner` (:62, last match
  wins). Add a self-test that every path in `git ls-files` resolves to exactly one owner (R36).
  Place the `execution/live/**` rule AFTER `execution/**` (R31). Add `banner.jpg` (RESEARCH
  Pitfall 8). Scope `vendor/**` and `tools/**` explicitly, because bare patterns match at any depth.
- **G-2 receipt.** Keep `REQUIRED_FIELDS` (:48) verbatim. Extend `BYPASS_PATTERNS` (:26) with
  `PUMPGROK_LIVE_ENABLE=(?:1|true)` and `--i-understand-the-risk` (FS section 4). Replace the seat
  alternation in `SEAT_ID_RE` (:57) with `bot-0[0-9]`.
- **G-3 secrets.** Keep `PATTERNS` (:29-47) and add the trading families from FS section 4.
  Keep `changed_files` (:152) and `staged_files` (:158). Keep the `pragma: allowlist secret` marker
  (:26). `.env.example` must pass on placeholders only.
- **G-4 contracts, G-5/6 rollback.** Port `check_contracts.py` and `check_rollback.py` with new
  roots (`contracts/events/`, `contracts/tool-rosters/`) and verbs (`pumpgrok state halt --clear`,
  R22).
- **G-7 integrity.** Change `ROSTER_MIN_TOOLS` (:41) from `10` to `8` (R19). Keep
  `ROSTER_MAX_TOOLS = 15`. Replace `TOOL_NAME_RE` (:46) with the dotted form
  `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$` (R19). Replace `SEAT_RE` (:47) with
  `^bot-0[0-9]-[a-z-]+$`. Keep `GATE_REQUIRED_FIELDS` and `TEMPLATE_FORBIDDEN`.
- **Runner.** `run_all.py`: `run()` uses `subprocess.run([sys.executable, *argv], cwd=REPO_ROOT)`,
  then a summary table and "never bypass a gate". Port verbatim, changing gate names.
- **Workflow trust model.** `programming-desk/.github/workflows/gates.yml`, step "Use trusted gate
  scripts from base ref": `git checkout "origin/$BASE_REF" -- ci/gates/`, with `BASE_REF` passed
  through `env:` (never `${{ }}` inside `run:`). Copy the step. Do not copy `runs-on:
  [self-hosted, Linux, X64]`; use `ubuntu-latest` and record it as FS U-3.

### M. Container and compose (FOUND-003, R50, R51)

**Dockerfile.** Analog `vendor/grokbot-pumpfun/Dockerfile` for the non-root user (`useradd --system`),
`HEALTHCHECK` stdlib one-liner and `STOPSIGNAL SIGTERM`. FS 3.3 for the multi-stage uv build.
Use: `python:3.12-slim`; `COPY --from=ghcr.io/astral-sh/uv:0.13.4 /uv /uvx /bin/`; `uv sync --frozen
--no-dev --no-editable`; `ENV PUMPGROK_PROFILE=paper`; HEALTHCHECK runs `pumpgrok doctor` (CONTEXT).
Do NOT create `/app/config` (vendor does; CONTEXT: no root `config/`). Add
`COPY tests/fixtures/replay/smoke /app/tests/fixtures/replay/smoke` (RESEARCH Pitfall 5) so the R50
path exists. CMD: `["run", "--mode", "paper", "--once", "--replay", "/app/tests/fixtures/replay/smoke"]`.

**.dockerignore.** Copy `vendor/grokbot-pumpfun/.dockerignore`; add `vendor/`, `var/`, `.env`,
`.planning/`, `tests/` with a negation for the smoke fixture path.

**docker-compose.yml.** From the vendor file keep the loopback port form (`127.0.0.1:8080:8080`),
the json-file logging block and the memory limit. Changes:
- `env_file: {path: .env, required: false}` (CONTEXT, FOUND-003).
- Drop `restart: unless-stopped`: the one-shot R50 command exits 0 and a restart policy loops it
  (RESEARCH Pitfall 6, Q1). Note the reason in a comment.
- Do not copy the vendor's `${GROKBOT_GROK_API_KEY:?...}` required-key form; the paper replay needs
  no secret.

**.env.example.** Copy the vendor layout (placeholder values, one comment per key). Drop
`PUMPGROK_DATA__API_KEY` (R45), `PUMPGROK_JUPITER__QUOTE_URL` (R44) and the retired Grok model
names (V-10, R48). Every value must pass G-3.

### N. Makefile and scripts (FOUND-002, FOUND-011)

**Analog:** `vendor/grokbot-pumpfun/Makefile` (`help` target that greps `##` lines, `check` target).
Targets from FS 3.2: `sync lint fmt typecheck test audit run-paper replay report gates prompts check
doctor clean`. `typecheck` is `uv run mypy --strict src/` (V-5, no prometheus or respx overrides).
`audit` is `uv export --no-emit-project` piped to `pip-audit --strict` (V-4). Keep `scripts/check.sh`
as is.

### O. Prompts and contracts (FOUND-008, 009)

**Analog:** `programming-desk/scripts/assemble-prompts.sh` (header comment; `--check` assembles into
a temp dir, diffs, exits 1 on drift) and `programming-desk/scripts/generate-templates.py` (`--check`).
Port both, pointing at `contracts/tool-rosters/` and the Phase 1 prompt sources.
`contracts/events/*.schema.json`: no analog; generate with `model_json_schema()` from `ledger/events.py`
and check drift with a `--check` mode.

### P. Ownership manifest (FOUND-006)

**Analog:** `programming-desk/ownership.yaml`: `ownership:` list of `pattern`, `owner`, optional
`contract_surface`; `bots:` map; `contract_consumers:`. Source: `docs/ROSTER.md:427-840` (R36).
Validate with `check_ownership.py --validate-manifest` (every owner declared, no repeated pattern).
Last match wins, so broad rules come first and specific rules later.

## Shared Patterns

### Forbidden names and placeholders
**Sources:** `hermes/profiles.yaml:18-24`; `vendor/grokbot-pumpfun/src/models.py:399`
(`PLACEHOLDER_MARKERS`); `programming-desk/ci/gates/check_secrets.py:64` (`PLACEHOLDER_RE`) and
`:87` (`is_placeholder`).
**Apply to:** `settings.py`, `.env.example`, `check_secrets.py`, compose. One list, used by the loader
and by G-3.

### Never print values
**Source:** `vendor/grokbot-pumpfun/src/models.py:434` (`mask`); the same file masks the wallet
field in its dump (around line 610).
**Apply to:** settings errors, logging, doctor, CLI.

### Deterministic ids and time
**Source:** IF 157-183; PE 449-465.
**Apply to:** all of `src/pumpgrok`. No `uuid`, `time.time`, `datetime.now` outside `replay/clock.py`;
ids from `IdFactory`; randomness from `make_rng`.

### Atomic writes
**Source:** `vendor/grokbot-pumpfun/src/state.py:76-86`.
**Apply to:** `atomic_write`, the fixture manifest, ledger snapshots, the KILLSWITCH file.

### Gate script shape
**Source:** `programming-desk/ci/gates/*.py`: stdlib plus pyyaml only; `REPO_ROOT =
Path(__file__).resolve().parents[2]`; `argparse` with `--base` and a `--files` override;
`changed_files(base)` via `git diff --name-only base...HEAD`; exit 1 with the reason on stderr;
`print("G-N PASS ...")` on success.

### Test style
**Source:** `vendor/grokbot-pumpfun/tests/test_state.py` and `test_config.py` (fixtures, `tmp_path`,
one behaviour per test); `tests/test_tools_cli.py` (stdlib unittest, keep).
pytest with `asyncio_mode = "auto"` and `asyncio_default_fixture_loop_scope = "function"` (V-9).

## Anti-patterns (do not copy)

| Where | What not to copy | Reason |
|---|---|---|
| `vendor/grokbot-pumpfun/src/models.py` `JitoConfig`, `SolanaConfig.wallet_private_key` | Jito config and wallet key field | M-10; delete |
| `vendor/grokbot-pumpfun/src/models.py` `ENV_OVERRIDES` (around line 403-416) | `GROKBOT_WALLET_PRIVATE_KEY` mapping | forbidden name (SEC-002) |
| `vendor/grokbot-pumpfun/src/models.py` `RiskConfig` | `float` money fields | R28: `int` lamports |
| `vendor/grokbot-pumpfun/Dockerfile` | `pip install -r requirements.txt`, `mkdir /app/config`, `src.pipeline` entrypoint | uv lock; no root config; `pumpgrok` entrypoint |
| `vendor/grokbot-pumpfun/docker-compose.yml` | `restart: unless-stopped` and required API key | R50 one-shot; no secret needed |
| `docs/design/interfaces.md:253` | `json.dumps(..., default=str)` | hides floats; CONTEXT forbids |
| `vendor/grokbot-pumpfun/src/state.py:84-86` | swallowing `OSError` | ledger must fail loudly |
| `programming-desk/ci/gates/check_desk_integrity.py:41` | `ROSTER_MIN_TOOLS = 10` | R19: minimum is 8 |
| `programming-desk/ci/gates/check_desk_integrity.py:46` | underscore-only tool name regex | R19: dotted names |
| FS 3.5 `.env.example` draft | `PUMPGROK_DATA__API_KEY`, `PUMPGROK_JUPITER__QUOTE_URL`, `grok-4-fast` | R45, R44, V-10 |

## No Analog Found

| File | Role | Spec to follow |
|---|---|---|
| `uv.lock`, `.python-version` | config | RESEARCH Standard Stack (uv 0.13.4) |
| `src/pumpgrok/config/overlays/*.toml` | config | CONTEXT Locked (`[live] enabled = false` in all three); PE 728-752 |
| `src/pumpgrok/core/registry.py` | service | IF 923- |
| `src/pumpgrok/core/ids.py` | utility | IF 157-183 |
| `src/pumpgrok/ledger/store.py` | repository | PE 282-316; RESEARCH Pattern 2 |
| `src/pumpgrok/replay/clock.py`, `rng.py` | utility | PE 449-465 |
| `src/pumpgrok/replay/fixtures.py` manifest | utility | CONTEXT Locked (mismatch exits 4, INV-R-30) |
| `tests/fixtures/replay/smoke/*` | fixture | PE 505-507 (CI smoke dataset) |
| `src/pumpgrok/logging/json.py` | middleware | FS 5.1-5.2 |
| `src/pumpgrok/execution/live/live_adapter.py` | stub | IF 611-620 |
| `contracts/events/*.schema.json` | config | generated from `ledger/events.py` |
| `tests/safety/test_static_guards.py`, `tests/test_network_block.py` | test | PE 441; RESEARCH Patterns 4-5 |
| `.receipts/bot-0N-*/.gitkeep` | config | precedent layout only |
| `SECURITY.md` | docs | `rules/pumpgrok-team.mdc` constitution text (SECURITY.md is not in the repo) |

## Planner notes (from the analogs and RESEARCH)

1. Analog excerpts are starting points. Money, time and RNG rules from the design docs override them.
2. `tests/test_tools_cli.py` imports `tools/jupiter_quote.py`, which exits at import when `requests`
   is missing (`jupiter_quote.py:14-19`). Add `requests` to the dev group until Phase 2 removes
   `tools/` (RESEARCH Pitfall 4, Q2). Do not skip the test.
3. `hermes/profiles.yaml` and `rules/pumpgrok-team.mdc` are read-only inputs: copy the forbidden list
   and constitution bytes, do not edit them here.
4. The repo has no root `.github/`, `.gitignore`, `Makefile`, `pyproject.toml` or `Dockerfile`. Create
   them; do not extend the vendor files at the root.
5. R51: the docker CLI is installed (29.6.2) but a reachable daemon is needed for criterion 4. If the
   daemon is unreachable, record the exact error as a blocker; do not substitute another check.

## Metadata

**Search scope:** repo root, `docs/`, `docs/design/`, `hermes/`, `rules/`, `scripts/`, `tests/`,
`tools/`, `vendor/grokbot-pumpfun/`; `~/src/repos/programming-desk/ci/`, `scripts/`, `.github/workflows/`.
**Read for excerpts:** vendor `state.py`, `models.py`, `log.py`, `pipeline.py`, `Dockerfile`,
`Makefile`, `pyproject.toml`, `docker-compose.yml`, `conftest.py`, `.dockerignore`, `.gitignore`,
`.env.example`, `.github/workflows/ci.yml`, `tests/test_config.py`, `tests/test_state.py`;
`hermes/profiles.yaml`; `tests/test_tools_cli.py`; `tools/jupiter_quote.py`; `scripts/check.sh`;
precedent gates, `run_all.py`, `assemble-prompts.sh`, `generate-templates.py`, `gates.yml`;
`docs/FOUNDATION_STACK.md` 3.1-3.7, 4, 5.1-5.3, 6; `docs/design/interfaces.md` 150-260, 600-625,
720-745; `docs/design/paper-engine.md` 282-343, 449-465.
**Line numbers:** verified by grep or sed on 2026-10-21 where given without "approx"; a few
vendor ranges may drift by a few lines.
