# Phase 12: Event runtime core - Pattern Map

**Mapped:** 2026-11-08
**Files analyzed:** 31
**Analogs found:** 28 / 31
**Tracked-source gate:** every analog below is printed by git ls-files from this worktree. No .gsd mirror paths.

## Do not copy

These files look related and are the wrong analog. Do not edit them. Do not import them from src/pumpgrok/events/.

| Path | Why it is not the analog |
|------|--------------------------|
| src/pumpgrok/config/sections/core.py LiveSettings | PRE-v4 pin. Copy the shape into v4.py. Do not edit the class, its defaults, or notional_cap_lamports. |
| src/pumpgrok/ledger/events.py EventType | Ledger CamelCase vocabulary. The one class EventKind lives only in events/models.py. |
| src/pumpgrok/ledger/store.py LedgerStore | Paper ledger. Sidecar must not open PAPER_LEDGER_PATH, must not hash-chain, must not name a table events. |
| src/pumpgrok/ledger/desk_bus.py | Atomic desk.md halt mirror. Not a bus. Do not extend it. |
| src/pumpgrok/supervisor/lifecycle.py shutdown | Opens LedgerStore and reduces the paper chain. Do not wire the bus into the supervisor. |
| src/pumpgrok/replay/sources.py FixtureEventSource | Replay fixture iterator. SourceSupervisor must not replace it. Fixture kind tick is not an EventKind. |
| contracts/, config/overlays/*.toml, degraded.py, live refusal path | Locked out of this phase. |

Ownership: src/pumpgrok/**, tests/**, and docs/** are bot-02-risk. CHANGELOG.md is bot-09-journal. Chief planning files stay on this branch. Do not implement product code here.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| src/pumpgrok/config/sections/v4.py | model | transform | src/pumpgrok/config/sections/core.py LiveSettings | role-match (copy shape, new file) |
| src/pumpgrok/config/settings.py | config | transform | same file, fields after health | exact (append only) |
| src/pumpgrok/events/__init__.py | package | request-response | src/pumpgrok/replay/sources.py __all__ | role-match |
| src/pumpgrok/events/constants.py | config | transform | src/pumpgrok/ledger/paths.py | role-match |
| src/pumpgrok/events/errors.py | utility | request-response | src/pumpgrok/core/errors.py | role-match |
| src/pumpgrok/events/models.py | model | transform | src/pumpgrok/ledger/events.py _ClosedModel | role-match |
| src/pumpgrok/events/store.py | service | file-I/O | src/pumpgrok/ledger/store.py open/PRAGMA only | partial |
| src/pumpgrok/events/dlq.py | service | CRUD | src/pumpgrok/ledger/store.py sqlite handle | partial |
| src/pumpgrok/events/bus.py | service | event-driven | none | none |
| src/pumpgrok/events/drain.py | service | batch | src/pumpgrok/replay/clock.py FixtureClock.advance_to | partial |
| src/pumpgrok/events/sources.py | service | event-driven | src/pumpgrok/replay/sources.py FixtureEventSource | partial |
| src/pumpgrok/cli/events.py | controller | request-response | src/pumpgrok/cli/verbs_ops.py _doctor_verb | role-match |
| src/pumpgrok/cli/parsing.py | route | request-response | same file _add_state | exact |
| src/pumpgrok/cli/dispatch.py | route | request-response | same file _VERB_HANDLERS | exact |
| docs/design/events-grok.md | config | transform | docs/design/paper-engine.md section table | role-match |
| tests/config/test_settings_surface_characterization.py | test | transform | same file prefix assertion | exact |
| tests/config/test_v4_settings_skeleton.py | test | request-response | tests/config/test_settings_surface_characterization.py | role-match |
| tests/config/test_events_settings.py | test | request-response | same surface test | role-match |
| tests/config/test_live_settings_caps.py | test | request-response | surface test; do not edit LiveSettings | role-match |
| tests/events/test_models.py | test | transform | src/pumpgrok/ledger/events.py closed models | role-match |
| tests/events/test_models_v4_kinds.py | test | transform | same | role-match |
| tests/events/test_bus_lanes.py | test | event-driven | none; assert RESEARCH lane rules | none |
| tests/events/test_bus_backpressure.py | test | event-driven | none | none |
| tests/events/test_bus_dedup_coalesce.py | test | event-driven | src/pumpgrok/replay/clock.py | partial |
| tests/events/test_bus_retry_dlq.py | test | event-driven | src/pumpgrok/replay/rng.py | partial |
| tests/events/test_handler_idempotency.py | test | CRUD | src/pumpgrok/core/idempotency.py | role-match |
| tests/events/test_bus_shutdown.py | test | file-I/O | sidecar store, not supervisor shutdown | partial |
| tests/events/test_sources.py | test | event-driven | src/pumpgrok/replay/sources.py | partial |
| tests/cli/test_events_cli.py | test | request-response | tests/cli/test_expiry_and_day_validation.py | role-match |
| tests/degradation/test_event_source_faults.py | test | event-driven | tests/harness/faults.py | role-match |
| tests/replay/test_event_drain_parity.py | test | batch | replay hash pins; do not change fixtures | partial |
| tests/safety/test_events_not_wired.py | test | request-response | tests/safety/test_import_graph_no_live.py | role-match |
| tests/harness/faults.py | test | event-driven | same file FaultMode | exact (append two fakes) |
| CHANGELOG.md | config | transform | same file Phase 11 Verified hash lines | exact (journal seat only) |

## Pattern Assignments

### `src/pumpgrok/config/sections/v4.py` (model, transform)

**Analog:** `src/pumpgrok/config/sections/core.py` lines 181-198. New module. Do not edit `core.py`.

**Imports pattern** (lines 8-16):

```python
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
```

Do not import `LAMPORTS_PER_SOL` into `v4.py`. No URL, socket, key, or interval field. Validators stay under 60 lines (`tests/quality/test_function_size.py` glob `config/sections/*.py`).

**Core pattern** (lines 181-198). Copy the frozen off-by-default shape, not the cap validator:

```python
class LiveSettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = False
    notional_cap_lamports: int | None = LAMPORTS_PER_SOL
```

Ten classes in this file only: `EventsSettings`, `GrokGatewaySettings`, `DatafeedSettings`, `RecorderSettings`, `StrategiesSettings`, `BacktestV2Settings`, `RiskStrategySettings`, `PromotionSettings`, `SignerSettings`, `PaperFeesSettings`. Each has `enabled: bool = False` and `allowlist: tuple[str, ...] = ()`.

`EventsSettings` also has `wake_mode: Literal["cadence"] = "cadence"` and `sidecar_path: str = "var/desk/events.sqlite"`. Do not default `wake_mode` to `"event"`. `PaperFeesSettings` also has `model: Literal["v1"] = "v1"`. `PromotionSettings` has no `interval_s` and no `3600`.

Sidecar-vs-ledger refusal belongs in `events/store.py`, not a long settings validator.

### `src/pumpgrok/config/settings.py` (config, transform)

**Analog:** the same file. Append only. Do not edit PRE-v4 field defaults.

**Re-export pattern** (lines 66-89). Add the ten new class names to `__all__` the way `LiveSettings` is listed. Callers import section classes from `pumpgrok.config.settings`.

**Field pattern** (lines 156-174). After `health`, append in this order, each `Field(default_factory=...)`:

1. `events`
2. `grok_gateway`
3. `datafeed`
4. `recorder`
5. `strategies`
6. `backtest_v2`
7. `risk_strategy`
8. `promotion`
9. `signer`
10. `paper_fees`

One import from `pumpgrok.config.sections.v4` plus those ten fields. Do not add the new env names to `NON_SETTING_ENV_NAMES`. `allowed_env_names()` already walks `Settings.model_fields`.

Do not edit `settings_customise_sources` (lines 175-204) or overlay loading. Absent TOML sections must stay at the class defaults. Do not edit `config/overlays/*.toml`.

### `src/pumpgrok/events/constants.py` (config, transform)

**Analog:** `src/pumpgrok/ledger/paths.py` lines 16-26.

```python
from pathlib import Path

__all__ = ["DESK_DATA_DIR", "PAPER_LEDGER_PATH"]

PAPER_LEDGER_PATH = Path("var") / "ledger.sqlite"
DESK_DATA_DIR = Path("var") / "desk"
```

Name the sidecar as `EVENTS_SIDECAR_PATH = DESK_DATA_DIR / "events.sqlite"` (string default `"var/desk/events.sqlite"` must match). Import `PAPER_LEDGER_PATH` only to refuse opening it. Do not point the sidecar at `var/ledger.sqlite`. Caps, TTLs, and retry counts are named constants in this module. Clock and RNG are injected; they are not constants read from the host.

### `src/pumpgrok/events/errors.py` (utility, request-response)

**Analog:** `src/pumpgrok/core/errors.py` lines 8-20. Subclass `PumpgrokError`. Do not edit `core/errors.py`.

```python
class PumpgrokError(Exception):
    code: ClassVar[str] = "pumpgrok_error"

    def __init__(self, message: str, **fields: Any) -> None:
        super().__init__(message)
        self.message = message
        self.fields: dict[str, Any] = fields
```

A refusal names an index or a constant path, never a secret or a payload value. A corrupt sidecar cursor starts clean in product code rather than raising through the live path.

### `src/pumpgrok/events/models.py` (model, transform)

**Analog:** `src/pumpgrok/ledger/events.py` lines 44-72. Do not add `EventKind` there. Do not edit `contracts/`.

```python
class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventType(StrEnum):
    """The 18 CamelCase R32 event types."""

    OrderPlaced = "OrderPlaced"
```

`class EventKind` is a `StrEnum` in this module only. Names are snake_case (`kill_switch`, `halt`, `exit_signal`, `risk_veto`, `token_created`, `migration`, `trade`, and the remaining P1/P2 kinds from RESEARCH.md). Priority is a function of kind: P0 never dropped, P1 overflow to DLQ, P2 coalesces. Money fields are `int` lamports. No float money. Event id is derived, not a ULID. A ULID changes when RNG call order changes.

**Id derivation analog:** `src/pumpgrok/core/idempotency.py` lines 40-65. Product `events/` does not import `LedgerStore`. Tests may pass `idempotency_key=event.event_id` into a tmp ledger.

```python
def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(_normalize(dict(payload), "$"), sort_keys=True, separators=(",", ":"))
```

Float leaves raise `TypeError`. Copy that refusal for event payloads. `derive_idempotency_key` (lines 49-65) returns `digest[:32]` over canonical JSON. Do not import `LedgerStore` from product `events/`.

### `src/pumpgrok/events/store.py` (service, file-I/O)

**Analog:** `src/pumpgrok/ledger/store.py` lines 136-145. Copy the connect pragmas only.

```python
self.path = Path(path)
self.path.parent.mkdir(parents=True, exist_ok=True)
self._db = sqlite3.connect(str(self.path), isolation_level=None)
self._db.execute("PRAGMA journal_mode = WAL;")
self._db.execute("PRAGMA synchronous = FULL;")
self._db.execute("PRAGMA busy_timeout = 5000;")
```

Do not copy `_SCHEMA` (the `events` table, hash columns, append-only triggers), `recreate_ledger_db`, `_row_hash`, or `append`. Tables are `pending`, `applied`, `dedup`, `dlq`, `cursors`, `meta` (or `bus_pending` / `bus_dlq`). No hash chain.

Before connect, refuse when `Path(path).resolve() == PAPER_LEDGER_PATH.resolve()`. The message names the constant path, never a payload. Default path is `var/desk/events.sqlite`. Tests pass `tmp_path / "events.sqlite"`.

Importing `pumpgrok.events` must not open sqlite. Open happens in the store constructor, not in `__init__.py`.

### `src/pumpgrok/events/dlq.py` (service, CRUD)

**Analog:** same sqlite handle as `store.py`. No ledger analog for list/replay/purge. Operations are sidecar-only: list, replay (republish onto the bus), purge (drop). `cli/events.py` calls these. Neither module imports `LedgerStore` or opens `PAPER_LEDGER_PATH`.

### `src/pumpgrok/events/bus.py` (service, event-driven)

**No analog.** See No Analog Found. Do not adapt `ledger/desk_bus.py` or `supervisor/lifecycle.py`.

Caller supplies `Clock` and `random.Random` from `make_rng`. Lanes: per-entity FIFO. P0 queue unbounded and never dropped; a P0 handler must not await an in-flight P1 handler. P1 cap 1000, overflow persisted to sidecar DLQ. P2 coalesce cap 1, latest-wins on the injected clock. Dedup TTL persisted for P0 and P1. Retry only transient errors, jitter from the seeded RNG. No `datetime.now`, `time.time`, `time.sleep`, or `asyncio.sleep`. Poison goes to the DLQ. `shutdown` persists pending. `recover()` processes each pending event exactly once. A corrupt cursor starts clean.

### `src/pumpgrok/events/drain.py` (service, batch)

**Analog:** `src/pumpgrok/replay/clock.py` lines 22-33 and 101-114. Synchronous. Uses `now` and `FixtureClock.advance_to`. Does not call `sleep`.

```python
class Clock(Protocol):
    def now(self) -> float: ...
    def monotonic(self) -> float: ...
    def utc_iso(self) -> str: ...
```

```python
def advance_to(self, ts: float) -> None:
    if ts < self._now:
        raise ValueError("virtual time cannot move backwards")
```

Drain must not import the replay runner, must not open the paper ledger, and must not change smoke-10m bytes. Fixture `kind: "tick"` stays a fixture record, not an `EventKind`.

### `src/pumpgrok/events/sources.py` (service, event-driven)

**Analog:** `src/pumpgrok/replay/sources.py` lines 22-42, for the thin source shape only. Do not replace `FixtureEventSource`.

```python
class FixtureEventSource:
    def __init__(self, dataset: FixtureDataset) -> None:
        self._dataset = dataset

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._dataset.events)
```

`SourceSupervisor` takes `Clock` and `make_rng`, loads and saves a cursor on the sidecar, backs off, treats a source stale after 120s, and can `resync(mints)`. It is not imported by `supervisor`, `execution`, `engine`, or the replay runner. No socket, no `httpx`, no `websockets`.

### `src/pumpgrok/events/__init__.py` (package, request-response)

**Analog:** `src/pumpgrok/replay/sources.py` line 18 (`__all__`). Re-export models, bus, store, and errors. The import must not construct a store, must not connect sqlite, and must not touch the network.

### `src/pumpgrok/cli/events.py` (controller, request-response)

**Analog:** `src/pumpgrok/cli/verbs_ops.py` lines 45-47 for the verb signature. Do not copy the ledger imports on lines 29-32.

```python
def _doctor_verb(_args: argparse.Namespace, settings: Settings) -> int:
    _say(sys.stdout, *doctor_report(settings))
    return EXIT_OK
```

Handler signature is `Callable[[argparse.Namespace, Settings], int]`. Subcommands: `dlq list`, `dlq replay`, `dlq purge`. Sidecar only. If `settings.events.enabled` is false, refuse without opening a socket and without opening the paper ledger. Exit codes come from `pumpgrok.cli.codes`. Usage failures raise `UsageError`.

**CLI test analog:** `tests/cli/test_expiry_and_day_validation.py` lines 15-26.

```python
from pumpgrok.cli import EXIT_CONFIG, EXIT_OK, main


def _confirm(expires: str) -> int:
    return main(["live", "confirm", "--by", _BY, "--notional-cap", _CAP, "--expires", expires])
```

`tests/cli/test_events_cli.py` calls `main(["events", "dlq", ...])` under `monkeypatch.chdir(tmp_path)`. Do not use the live confirm path.

### `src/pumpgrok/cli/parsing.py` (route, request-response)

**Analog:** lines 132-137 and 188-210. Add `_add_events` in the same style as `_add_state`: parent verb `events`, required subparsers, then `dlq` with `list|replay|purge`. Call it from `build_parser` next to the other `_add_*` calls. Do not change `run`, `verify`, or `live`.

```python
state = verbs.add_parser("state", parents=[mode_option], help="desk state verbs")
state_cmd = state.add_subparsers(dest="cmd", required=True, metavar="STATE")
```

```python
verbs = parser.add_subparsers(dest="verb", required=True, metavar="VERB")
_add_run(verbs, mode_option)
_add_tail(verbs, mode_option)
return parser
```

### `src/pumpgrok/cli/dispatch.py` (route, request-response)

**Analog:** lines 36-58. Add one import and one map entry `"events": _events_verb`. Do not import `events` from `supervisor`.

```python
_VERB_HANDLERS: dict[str, Callable[[argparse.Namespace, Settings], int]] = {
    "doctor": _doctor_verb,
    "verify": _verify_verb,
}

handler = _VERB_HANDLERS.get(args.verb)
if handler is None:
    return _not_implemented(args.verb)
return handler(args, settings)
```

`_dispatch` still calls `load_settings` before the handler. Loading settings must not open the sidecar. `pumpgrok verify` and `pumpgrok run --mode paper` must not import the bus.

### `docs/design/events-grok.md` (config, transform)

**Analog:** `docs/design/paper-engine.md` lines 12-18, the scope table only. Library contract: kinds, lanes, sidecar path, clock/RNG injection, and the statement that the bus is not wired into the supervisor. No Grok gateway, no wake-mode flip, no live path. Lock the discretionary `EventKind` names in the same plan that creates the class.

### `tests/config/test_settings_surface_characterization.py` (test, transform)

**Analog:** the same file, lines 6-7 and 84-85. The only edit: prefix check, then suffix of the ten names in append order. Do not change `PRE_V4_FIELDS` or `PINNED_SECTION_DIGESTS`.

```python
def test_top_level_fields_are_pinned_in_order() -> None:
    assert tuple(Settings.model_fields) == PRE_V4_FIELDS
```

`test_pinned_sections_are_every_field_except_mode` compares `PRE_V4_FIELDS` to digest keys, not to `Settings.model_fields`. Leave it. The docstring already says a new v4 section is added as a new field and does not touch these pins.

### `tests/config/test_live_settings_caps.py` (test, request-response)

New file. A notional cap above 1.0 SOL still refuses to load. The test must pass without editing `LiveSettings`. Existing coverage in `tests/safety/test_wallet_allowlist_settings.py` and `tests/safety/test_live_gate_wallet_cap.py` stays as written.

### `tests/harness/faults.py` (test, event-driven)

**Analog:** lines 28-36. Append `FaultyEventSource` and `FaultyGrokTransport`. Do not replace existing fakes. `FaultyGrokTransport` raises; it does not connect.

```python
class FaultMode(StrEnum):
    STALE = "stale"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    RAISE = "raise"
```

Count how often the fault fired, matching the module docstring (lines 1-11).

### `tests/safety/test_events_not_wired.py` (test, request-response)

**Analog:** `tests/safety/test_import_graph_no_live.py` lines 1-36. AST closure. Assert `supervisor`, `execution`, `engine`, and the replay runner do not import `pumpgrok.events`. Do not weaken the live-adapter quarantine.

```python
GUARDED_PREFIXES = (
    "pumpgrok.backtest",
    "pumpgrok.upgrade",
    "pumpgrok.supervisor",
)
```

### `CHANGELOG.md` (config, transform)

**Analog:** lines 20-24. Journal seat only. Four hash lines: Phase 12 smoke-10m before/after and trading-smoke before/after. Do not remeasure by importing the bus into `verify`. Known pin:

```
- Phase 11: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
- Phase 11: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
```

Risk plans do not edit this file.

## Shared Patterns

### Injected clock, no host time

**Source:** `src/pumpgrok/replay/clock.py` lines 1-6 and `tests/safety/test_static_guards.py` lines 18-35.
**Apply to:** every module under `src/pumpgrok/events/` and `cli/events.py`.

```python
CLOCK_ALLOWLIST = frozenset({"replay/clock.py"})
```

Banned call names include `time.time`, `datetime.now`, `asyncio.sleep`, `asyncio.timeout`, `asyncio.wait_for`. Drain and retry delays use `Clock` plus `make_rng`. Do not add `events/` to the allowlist.

### Seeded RNG

**Source:** `src/pumpgrok/replay/rng.py` lines 14-16.
**Apply to:** bus retry jitter and `SourceSupervisor` backoff.

```python
def make_rng(seed: int = DEFAULT_SEED) -> random.Random:
    return random.Random(seed)
```

Do not call `random.random()` or construct `random.Random` outside `replay/rng.py`.

### Identity

**Source:** `src/pumpgrok/core/ids.py` lines 29-45.
**Apply to:** correlation ids in tests only. Event ids are derived hashes, not ULIDs. Do not import `uuid`.

```python
class IdFactory:
    def __init__(self, clock: Clock, rng: random.Random) -> None:
        self._clock = clock
        self._rng = rng
```

### Fail closed, no secret echo

**Source:** `src/pumpgrok/config/settings.py` `ConfigError` and `src/pumpgrok/core/errors.py` `fields`.
**Apply to:** settings validators, sidecar path refusal, DLQ CLI errors. A refusal names an index or a constant path, never a value.

### Import graph

**Source:** `tests/safety/test_import_graph_no_live.py` lines 40-52.
**Apply to:** `events/` and `cli/events.py`. No `httpx`, `websockets`, `socket`, `solders`, or `solana`. `pumpgrok run --mode live --once` still exits 3.

### Settings off by default

**Source:** `LiveSettings.enabled: bool = False` and the surface-test docstring lines 6-7.
**Apply to:** all ten v4 sections. Loading with the sections absent from TOML succeeds and leaves them off. A new field does not touch PRE-v4 pins.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/pumpgrok/events/bus.py` | service | event-driven | No in-process lane bus. `ledger/desk_bus.py` writes `desk.md`. `supervisor/lifecycle.py` drains seat tasks into the paper ledger. Use RESEARCH.md lane rules, not those files. |
| `src/pumpgrok/events/dlq.py` | service | CRUD | No persisted DLQ. Copy sqlite connect pragmas from `ledger/store.py` only. |
| `src/pumpgrok/events/drain.py` | service | batch | No second drain. `FixtureClock.advance_to` is the time primitive. Do not call supervisor `shutdown`. |

## Metadata

**Analog search scope:** `src/pumpgrok/config/`, `src/pumpgrok/ledger/`, `src/pumpgrok/cli/`, `src/pumpgrok/replay/`, `src/pumpgrok/core/`, `src/pumpgrok/supervisor/lifecycle.py`, `tests/safety/`, `tests/config/`, `tests/cli/`, `tests/harness/`, `docs/design/`, `CHANGELOG.md`.
**Files scanned:** 22 tracked analogs, plus confirmation that `src/pumpgrok/ledger/desk_bus.py` is a markdown mirror.
**Pattern extraction date:** 2026-11-08

## PATTERN MAPPING COMPLETE

**Phase:** 12 - Event runtime core
**Files classified:** 31
**Analogs found:** 28 / 31

### Coverage

- Files with exact analog: 6 (`settings.py`, `parsing.py`, `dispatch.py`, surface test, `faults.py`, `CHANGELOG.md`)
- Files with role-match or partial analog: 22
- Files with no analog: 3 (`events/bus.py`, `events/dlq.py`, `events/drain.py`)

### Key Patterns Identified

- New v4 section is a frozen `extra="forbid"` class in a new module, plus one field appended after `health`. PRE-v4 classes stay untouched.
- One `EventKind` in `events/models.py`. Ledger `EventType` stays CamelCase and is not edited.
- Sidecar sqlite copies WAL/FULL/busy_timeout only, path `var/desk/events.sqlite`, and refuses `PAPER_LEDGER_PATH`.
- Clock and `make_rng` are injected. `events/` must not call host time or ambient random.
- CLI verb is a `(Namespace, Settings) -> int` handler registered in `_VERB_HANDLERS`, sidecar only, not wired into the supervisor.

### File Created

`.planning/phases/12-event-runtime-core/12-PATTERNS.md`

### Ready for Planning

Pattern mapping complete. Planner can now reference analog patterns in PLAN.md files.
