# Phase 12: Event runtime core - Research

**Researched:** 2026-11-08
**Domain:** In-repo typed event library, config-gated settings skeleton, sidecar sqlite. No new package.
**Confidence:** HIGH for patterns copied from this tree. MEDIUM for the numeric constants and EventKind names, which CONTEXT leaves to discretion and no v4 design doc names yet.

## Summary

Phase 12 adds a library. It does not change the desk loop. `load_settings()` must keep constructing the same paper desk it constructs today. `pumpgrok verify` and `pumpgrok run --mode paper` must not import the bus, must not open the sidecar, and must not open a socket. That is how the smoke-10m hash stays `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` and how live stays exit 3.

The settings work is ten new section classes in a new module, ten new fields appended after `health`, and one assertion change in the surface test. The assertion today requires the field tuple to equal `PRE_V4_FIELDS`. The test's own docstring says a new field does not touch the pins. Change the assertion to a prefix check. Do not edit `PRE_V4_FIELDS`, the digest map, or any PRE-v4 class.

The runtime work is one `EventKind` class, a bus with three lanes, a sidecar sqlite that is not the ledger, a deterministic drain, and a `SourceSupervisor` that is not wired into the supervisor. Replay fixtures stay byte-identical. Fixture `kind: "tick"` is not an `EventKind`.

**Primary recommendation:** Build `src/pumpgrok/events/` as a closed library that opens only `var/desk/events.sqlite`, takes `Clock` and `make_rng` from the caller, and is not imported by `supervisor`, `execution`, `engine`, or the replay runner.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Already on origin/main (do not reimplement)

- Platform is declared: chain `solana`, venue `pumpfun-bonding-curve`, execution `paper`, quote-only `jupiter-swap-v2`. `PlatformSettings` selects no endpoint and changes no mode (`src/pumpgrok/config/sections/core.py`).
- Wallet allowlist accepts only base58 text that decodes to exactly 32 bytes. A refusal names the index, never the value. This is the Phase 12 slice of the allowlist. The Ed25519 curve-point check and the operator confirm-by-typing step are ONB-06, Phase 14. Do not add `solders` or `solana`.
- `LiveSettings.notional_cap_lamports` defaults to 1 SOL and refuses a value outside `(0, 1 SOL]`. `live`, `platform`, and `wallet` are PRE-v4 fields pinned by `tests/config/test_settings_surface_characterization.py`. Do not edit those classes or their defaults.
- `tests/safety/test_wallet_allowlist_settings.py` and `tests/safety/test_live_gate_wallet_cap.py` already cover that slice. New cap tests go in `tests/config/test_live_settings_caps.py` and must pass without changing the pinned classes.
- The branch `bot-00-chief/desk-built-ins` (worktree `/root/src/repos/pumpgrok-desk-builtins`, `3bf9239`) is 229 commits behind `origin/main`. Its platform, allowlist, and cap code is already on main. Do not merge that branch. Do not port `upgrade/scheduled.py`, the 3600 second promotion cadence, or the serve-loop promotion search. Cadence remains the supervisor default through v4 (OD-20). A fixed cadence is not a conflict with this library, and it is not this phase's job.

### Settings skeleton (PRC-11)

- Add new fields only. A new v4 section is one class plus one import and one field on `Settings`. Never edit a PRE-v4 section. The surface test says a new field does not touch the pins.
- Sections that must exist once, each config-gated off: `events`, `grok_gateway`, `datafeed`, `recorder`, `strategies`, `backtest_v2`, `risk_strategy`, `promotion`, `signer`, `paper_fees`. `live` already exists and stays pinned.
- "Off" means enabled/default false, empty allowlists, and no network, no socket, and no supervisor wiring. Loading settings with the new sections absent from TOML must succeed and leave them off.
- A notional cap above 1.0 SOL still refuses to load. Do not raise the ceiling.

### Event runtime

- One catalog. `class EventKind` appears in exactly one module under `src/pumpgrok`. Ledger CamelCase types in `ledger/events.py` stay the ledger vocabulary. Do not add a second `EventKind` there, and do not edit `contracts/` (criterion 10: `git diff --name-only v4-base -- contracts` is empty).
- Frozen models, derived event ids, priority as a function of kind, integer money only. No float money.
- Lanes: per-entity FIFO. P0 is never dropped and is isolated from a slow P1 handler. P1 overflow goes to a persisted DLQ. P2 coalesces.
- Dedup TTL, persisted for P0 and P1. Debounce or latest-wins coalescing uses the injected `Clock` only. No `datetime.now`, `time.time`, or `time.sleep` under `src/pumpgrok/events`.
- Retry only transient errors, with seeded jitter from the replay RNG root. Poison goes to the DLQ. `pumpgrok events dlq list|replay|purge` republishes or drops as named. The verb lives in `src/pumpgrok/cli/events.py`.
- Handlers are idempotent under double delivery: a second delivery writes no new ledger row.
- Shutdown persists pending events. `recover()` processes each pending event exactly once.
- The DLQ and the pending store are a sidecar sqlite. They never open or write `var/ledger.sqlite`.
- `SourceSupervisor` owns reconnect backoff, staleness, resync, and cursors. Backoff resets only after `stable_s`. 121 seconds of silence yields stale. Resync seeds held mints. A corrupt cursor starts clean. One staleness owner.
- Deterministic drain: two drains of the same events and seed are byte-identical, including the trading-smoke parity test, with zero skipped tests. Do not claim smoke-10m fixture_compat parity here.
- Typed errors go in `core/errors.py` only if that edit does not change a pinned surface. `FaultyEventSource` and `FaultyGrokTransport` go in `tests/harness/faults.py`. `FaultyGrokTransport` is a test fake only. Do not build the Grok gateway.

### Safety and hashes

- Paper only. `pumpgrok run --mode live --once` still exits 3. No signing symbol, no live adapter, no key material.
- smoke-10m `events.hash` stays `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`. Record both Phase 12 before and after pairs, and the trading-smoke pair, in `CHANGELOG.md`.
- Phase 11 is closed (PR 55 merged, `11-VERIFICATION.md` status passed). Do not replan or re-execute Phase 11. The ROADMAP progress table still says 0/11; that row is stale. This run stops after Phase 12. Do not start Phase 13. The owner receipt-approval ship checkpoint is after Phase 12.

### Ownership

- `.planning/**` is `bot-00-chief`. This context and the plans stay on `bot-00-chief/phase-12-event-runtime`.
- `src/pumpgrok/**` (including `events/`, `config/`, `cli/` package, `core/errors.py`) and `tests/**` and `docs/**` default to `bot-02-risk`. Implementation commits for those paths go on `bot-02-risk/phase-12-event-runtime`, not on the chief branch.
- `CHANGELOG.md` is `bot-09-journal`. The hash-pair entry is a journal commit on `bot-09-journal/phase-12-event-runtime`.
- Do not edit another seat's path to unblock a seat. Do not add a pull-request-number waiver. Criterion 10 forbids contract edits, so no `contracts/changes/` document is required if `contracts/` is untouched.

### Claude's Discretion

- Lane capacities, dedup TTL values, retry attempt count, and the sidecar path, as long as they are named constants, covered by the named tests, and use the injected Clock and seeded RNG.
- Module split inside `src/pumpgrok/events/` (`models`, `bus`, `store`, `dlq`, `drain`, `sources`), matching the roadmap deliverable list.
- Whether `core/errors.py` gains new typed errors or the events package owns its errors, if the pinned surface and the single-catalog rule still hold.

### Deferred Ideas (OUT OF SCOPE)

- Wiring the bus into the supervisor, event-mode seat wakes, Hermes cron cutover, Grok gateway, idle-zero-Grok measurement (Phase 14).
- Flipping the default `wake_mode` to event (next milestone after a week of live-paper evidence, OD-20).
- Curve-layout probe review, live market data, recorder sealing (Phase 13). Human review is required before any VERIFIED flip.
- ONB-06 curve-point check and operator address confirmation (Phase 14).
- Enabling live, funding a wallet, devnet airdrops, and a $200 mainnet book. v4 builds the live path dormant in Phase 18 and never enables it. Notional cap stays at most 1.0 SOL.
- Scheduled promotion cadence from `desk-built-ins`. Not this phase.
- Phase 13 and later. This autonomous run stops at the Phase 12 ship checkpoint.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EVT-01 | Typed frozen event models, derived ids, priority by kind, integer money only | `events/models.py` plus `core/idempotency.py` `canonical_json`. Test: `tests/events/test_models.py`. |
| EVT-02 | P0 never drops, P1 overflow to persisted DLQ, P2 coalesces | Named caps in `events/constants.py`. Test: `tests/events/test_bus_backpressure.py`. |
| EVT-03 | Per-entity FIFO and P0 isolation from a slow P1 handler | Separate P0 dispatch task. Test: `tests/events/test_bus_lanes.py`. |
| EVT-04 | Dedup TTL persisted for P0 and P1; debounce or latest-wins on the injected Clock | Sidecar `dedup` table. Test: `tests/events/test_bus_dedup_coalesce.py`. |
| EVT-05 | Transient retry with seeded jitter, poison to DLQ, `pumpgrok events dlq replay` | `events/bus.py`, `events/dlq.py`, `cli/events.py`. Tests: `tests/events/test_bus_retry_dlq.py`, `tests/cli/test_events_cli.py`. |
| EVT-06 | Handler idempotent under double delivery; no new ledger row | Caller-supplied append plus `idempotency_key`. Test: `tests/events/test_handler_idempotency.py`. Product code does not import `LedgerStore`. |
| EVT-07 | Shutdown persists pending events; `recover()` runs each once | Sidecar `pending` table. Test: `tests/events/test_bus_shutdown.py`. |
| EVT-08 (first half only) | Two drains of the same events and seed are byte-identical, including trading-smoke parity, zero skips. No smoke-10m fixture_compat claim | `events/drain.py`. Test: `tests/replay/test_event_drain_parity.py` with `-k determinism` and `-k smoke_trading` only. |
| EVT-09 | Backoff resets only after `stable_s`; 121s silence is stale; resync seeds held mints; corrupt cursor starts clean | `events/sources.py`. Tests: `tests/events/test_sources.py`, `tests/degradation/test_event_source_faults.py`. |
| EVT-14 | One `EventKind`, one source and staleness owner inside the events package | `class EventKind` only in `events/models.py`. `SourceSupervisor` is the events-package staleness owner. Do not edit `DegradedState`. Test: `tests/events/test_models_v4_kinds.py`. |
| PRC-11 | Every v4 settings section exists once, config-gated off | `config/sections/v4.py` plus appended `Settings` fields. Tests: `tests/config/test_v4_settings_skeleton.py`, `tests/config/test_events_settings.py`, `tests/config/test_live_settings_caps.py`. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

These directives have the same force as the locked decisions. Do not recommend a path that breaks them.

- Product code is `src/pumpgrok/`. Python 3.12 only (`requires-python`, `python_version = "3.12"`). Install with `uv sync --frozen --group dev`. Lint is `ruff check` and `ruff format --check`. Types are `mypy src/` under `--strict`. Tests are `pytest -q`.
- Money is integer lamports via `src/pumpgrok/core/units.py`. Ratios and prices are `Decimal`, never `float`.
- Time comes from the injected `Clock` in `src/pumpgrok/replay/clock.py`. `WallClock` is production. `FixtureClock` is replay.
- Config arrives as `PUMPGROK_*` env vars with nested delimiter `__`. There is no `--rpc` flag.
- Live mode refuses with exit 3 when any live-gate precondition is unmet. Do not add a live adapter, a signing symbol, or key material.
- Secrets are `PUMPGROK_*` env vars. Key-bearing endpoint values are refused at startup.
- ASCII-only new docs. `scripts/check.sh` fails on emoji.
- Every tracked path has one owner in `ownership.yaml` (last match wins). New `src/pumpgrok/events/**`, `src/pumpgrok/config/**`, `src/pumpgrok/cli/events.py`, `tests/events/**`, `tests/cli/**`, `tests/config/**`, `tests/degradation/**`, `tests/replay/**`, and `docs/design/events-grok.md` resolve to `bot-02-risk`. `CHANGELOG.md` resolves to `bot-09-journal`. `.planning/**` resolves to `bot-00-chief`.
- Do not edit `contracts/`. Criterion 10 is `git diff --name-only v4-base -- contracts` empty.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| v4 settings sections, off by default | API / Backend (library config) |  -  | `Settings` is the process config object. Loading it must not open a socket or start a task. |
| Event catalog, ids, priority | API / Backend (library) |  -  | Pure functions of kind and payload. No I/O. |
| Lanes, dedup, coalesce, retry, drain | API / Backend (library) |  -  | In-process. Time and randomness are injected. |
| DLQ, pending, cursors | Database / Storage (sidecar sqlite) |  -  | A second file. Not `var/ledger.sqlite`. Not the hash chain. |
| SourceSupervisor backoff, staleness, resync | API / Backend (library) |  -  | Owns event-source staleness. Does not replace `DegradedState` this phase. |
| `pumpgrok events dlq` | API / Backend (CLI) | Database / Storage | Opens the sidecar only. No supervisor, no network. |
| Replay hash, paper run, live refusal | API / Backend (existing desk) |  -  | Untouched. The new library is not on those import paths. |
| Grok gateway, seat wake, live feed, recorder seal |  -  |  -  | Out of scope. Settings exist so later phases have a field. They do not run. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | `>=2.14.1,<3` already in `pyproject.toml` | Frozen section models and frozen events, `extra="forbid"` | Already the settings and ledger-event stack. `[VERIFIED: pyproject.toml dependencies]` |
| pydantic-settings | `>=2.16.1,<3` already in `pyproject.toml` | `Settings` env and TOML load | Already how `load_settings()` works. Do not add a second loader. |
| sqlite3 | stdlib, linked to SQLite 3.45.1 on this machine | Sidecar tables | Same engine as `LedgerStore`. No new driver. `[VERIFIED: python3 -c import sqlite3]` |
| hashlib | stdlib | Derived event ids | Same sha256 width as `derive_idempotency_key`. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | already in the dev group; `asyncio_mode = "auto"` | The named phase tests | Every new test file. |
| pytest-asyncio | already implied by `asyncio_mode = "auto"` | Async lane-isolation and retry tests | Only where the bus awaits a handler. The drain itself stays synchronous. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib sqlite3 sidecar | A new queue package | Rejected. No new dependency, and the ledger already shows the WAL pattern. |
| tenacity for retry | Hand-rolled loop on `Clock` | tenacity waits on the host clock. Forbidden under `src/pumpgrok/events`. |
| ULID event ids | sha256 of canonical payload | A ULID changes when the RNG call order changes. Dedup and drain parity need an id that is a function of the event. |
| Editing `core/errors.py` | `events/errors.py` subclasses of `PumpgrokError` | The events package owns its errors. `core/errors.py` stays untouched, so no pinned surface can move. |

**Installation:**

```bash
# no new packages
```

**Version verification:** No package is added. Do not run `uv add`. Do not add `solders`, `solana`, `tenacity`, or a third-party bus.

## Package Legitimacy Audit

This phase installs no external package. The legitimacy gate has nothing to check.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
caller (test or, later, a phase-14 root)
        |
        | Clock + random.Random from make_rng(seed)
        v
+------------------+     publish(Event)      +----------------------+
| SourceSupervisor | ----------------------> | EventBus             |
| backoff          |                         | P0 queue (unbounded) |
| stale if >120s   |                         | P1 queue (cap 1000)  |
| resync(mints)    |                         | P2 coalesce (cap 1)  |
| cursor load/save |                         +----------+-----------+
+--------+---------+                                    |
         |                                              | handler
         | cursor / pending / dedup / dlq               v
         v                                    idempotent append callback
+------------------+                         (test supplies LedgerStore
| sidecar sqlite   |                          at a tmp path; product code
| var/desk/        |                          does not import LedgerStore)
| events.sqlite    |
+------------------+
         ^
         | list | replay | purge
         |
pumpgrok events dlq     (CLI; sidecar only)

NOT connected this phase:
  supervisor tick loop
  replay runner / verify
  var/ledger.sqlite
  network / socket
  Grok gateway
```

A reader can trace one publish from `SourceSupervisor` or a test into a lane, then into the sidecar on overflow, shutdown, or poison. The paper ledger is not on that path.

### Recommended Project Structure

```
src/pumpgrok/config/sections/v4.py          # ten new section classes only
src/pumpgrok/config/settings.py             # import + one field each, appended after health
src/pumpgrok/events/__init__.py             # re-exports; import must not open sqlite
src/pumpgrok/events/constants.py            # named caps, TTLs, path
src/pumpgrok/events/errors.py               # PumpgrokError subclasses
src/pumpgrok/events/models.py               # the one class EventKind
src/pumpgrok/events/store.py                # sidecar open, pending, dedup, cursors, applied
src/pumpgrok/events/dlq.py                  # list, replay, purge
src/pumpgrok/events/bus.py                  # lanes, dedup, coalesce, retry, shutdown, recover
src/pumpgrok/events/drain.py                # synchronous deterministic drain
src/pumpgrok/events/sources.py              # SourceSupervisor
src/pumpgrok/cli/events.py                  # verb body
src/pumpgrok/cli/parsing.py                 # add the events parser
src/pumpgrok/cli/dispatch.py                # register the handler
docs/design/events-grok.md                  # library contract only; no gateway
tests/config/test_v4_settings_skeleton.py
tests/config/test_events_settings.py
tests/config/test_live_settings_caps.py
tests/events/test_models.py
tests/events/test_models_v4_kinds.py
tests/events/test_bus_lanes.py
tests/events/test_bus_backpressure.py
tests/events/test_bus_dedup_coalesce.py
tests/events/test_bus_retry_dlq.py
tests/events/test_handler_idempotency.py
tests/events/test_bus_shutdown.py
tests/events/test_sources.py
tests/cli/test_events_cli.py
tests/degradation/test_event_source_faults.py
tests/replay/test_event_drain_parity.py
tests/safety/test_events_not_wired.py
tests/harness/faults.py                     # add two fakes; do not replace existing ones
```

Do not create `src/pumpgrok/grok/`, `src/pumpgrok/datafeed/`, or `src/pumpgrok/strategies/` in this phase. Those packages are later phases. The settings classes are the only placeholders.

### Pattern 1: New settings section, appended field

**What:** One frozen class in `config/sections/v4.py`. One import and one field on `Settings`, after `health`.
**When to use:** Every PRC-11 section.
**Example:** Copy the shape of `LiveSettings` (`frozen=True`, `extra="forbid"`, `enabled: bool = False`) without editing that class.

Existing pin, quoted so the planner does not "fix" it by editing the tuple:

```
PRE_V4_FIELDS: tuple[str, ...] = (
    "mode",
    "execution",
    "risk",
    "limits",
    "replay",
    "live",
    "platform",
    "wallet",
    "data",
    "rpc",
    "grok",
    "jupiter",
    "filter",
    "safety",
    "scoring",
    "exits",
    "ops",
    "notify",
    "health",
)
```

`[VERIFIED: tests/config/test_settings_surface_characterization.py:21-41]`

The blocking assertion, quoted:

```
def test_top_level_fields_are_pinned_in_order() -> None:
    assert tuple(Settings.model_fields) == PRE_V4_FIELDS
```

`[VERIFIED: tests/config/test_settings_surface_characterization.py:84-85]`

The docstring already allows the append:

```
A new v4 section is added as a new field and does not touch these pins.
```

`[VERIFIED: tests/config/test_settings_surface_characterization.py:6-7]`

Required test edit, and only this edit, in that file: assert the prefix equals `PRE_V4_FIELDS`, then assert the suffix is exactly the ten new names in the order below. Do not change `PRE_V4_FIELDS` or `PINNED_SECTION_DIGESTS`. `test_pinned_sections_are_every_field_except_mode` compares `PRE_V4_FIELDS` to the digest keys, not to `Settings.model_fields`, so it stays as written.

Append order on `Settings`, after `health`:

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

Each class:

- `model_config = ConfigDict(frozen=True, extra="forbid")`
- `enabled: bool = False`
- `allowlist: tuple[str, ...] = ()`
- no URL field, no socket field, no key field, no interval field

`events` also has:

- `wake_mode: Literal["cadence"] = "cadence"` so the field exists and cannot select event mode yet. Phase 14 widens the literal. Do not default it to `"event"`.
- `sidecar_path: str = "var/desk/events.sqlite"` matching `EVENTS_SIDECAR_PATH`.

`paper_fees` also has `model: Literal["v1"] = "v1"`. Phase 15 widens this when fee model v2 becomes selectable. Do not put fee rates here.

`promotion` has no `interval_s` and no `3600`. Do not import `upgrade/scheduled.py`.

Do not edit `src/pumpgrok/config/overlays/*.toml`. Absent sections must load as the defaults. `Settings` uses `extra="forbid"`, so a typo in operator TOML still fails. The in-package overlays do not mention the new names, which is the off path.

`config/sections/*.py` is in the 60-line function successor set (`MAX_FUNCTION_LINES = 60`, glob `config/sections/*.py`). `[VERIFIED: tests/quality/test_function_size.py:17-24]` Keep every validator in `v4.py` under 60 lines. A path check that the sidecar does not resolve to `PAPER_LEDGER_PATH` belongs in `events/store.py`, not in a long settings validator.

Re-export the ten classes from `pumpgrok.config.settings` `__all__`, the same way `LiveSettings` is re-exported. Callers import section classes from `pumpgrok.config.settings`.

`allowed_env_names()` walks `Settings.model_fields`, so `PUMPGROK_EVENTS__ENABLED` becomes legal without a hand-written allowlist. Do not add those names to `NON_SETTING_ENV_NAMES`.

### Pattern 2: One catalog, derived id, priority by kind

**What:** `class EventKind` lives only in `src/pumpgrok/events/models.py`.
**When to use:** Every v4 bus event. Not for ledger rows.

Ledger vocabulary stays `class EventType(StrEnum)` in `ledger/events.py`. Quoted members, so nobody adds a second catalog there:

```
class EventType(StrEnum):
    """The 18 CamelCase R32 event types."""

    OrderPlaced = "OrderPlaced"
    OrderRejected = "OrderRejected"
    FillRecorded = "FillRecorded"
    PositionOpened = "PositionOpened"
    PositionClosed = "PositionClosed"
    MarkToMarket = "MarkToMarket"
    HaltSet = "HaltSet"
    HaltCleared = "HaltCleared"
    KillSwitchSet = "KillSwitchSet"
    KillSwitchCleared = "KillSwitchCleared"
    BreakerTripped = "BreakerTripped"
    BreakerReset = "BreakerReset"
    DailyRollover = "DailyRollover"
    ConfigChanged = "ConfigChanged"
    LiveWriteAttempted = "LiveWriteAttempted"
    Escalation = "Escalation"
    JournalNote = "JournalNote"
    ApprovalRecorded = "ApprovalRecorded"
```

`[VERIFIED: src/pumpgrok/ledger/events.py:52-72]`

Do not add `EventKind` to that file. Do not edit `contracts/events/`.

Recommended `EventKind` values (discretion; lock them in `docs/design/events-grok.md` in the same plan that creates the class). Names are snake_case so they cannot be confused with `EventType`:

| Kind | Priority | Lane rule |
|------|----------|-----------|
| `kill_switch` | 0 | never drop |
| `halt` | 0 | never drop |
| `exit_signal` | 0 | never drop |
| `risk_veto` | 0 | never drop |
| `token_created` | 1 | overflow to DLQ |
| `migration` | 1 | overflow to DLQ |
| `trade` | 1 | overflow to DLQ |
| `position_opened` | 1 | overflow to DLQ |
| `position_closed` | 1 | overflow to DLQ |
| `strategy_intent` | 1 | overflow to DLQ |
| `curve_tick` | 2 | latest-wins coalesce |
| `mark` | 2 | debounce coalesce |

`priority_of(kind) -> Literal[0, 1, 2]` is a total function. The model has no priority field a caller can set. A kind missing from the table is a `KeyError` at construction, not a silent P2.

Fixture files use `"kind": "tick"`. That string is not an `EventKind`. Do not add `tick`. The drain test maps a fixture row to `curve_tick` in the test, and does not rewrite `events.jsonl` (its sha256 is in the manifest).

Event id: `sha256(canonical_json({"kind", "entity_id", "payload"}))[:32]`. Use `canonical_json` from `src/pumpgrok/core/idempotency.py`. It rejects floats and serialises `Decimal` as `str`. `[VERIFIED: src/pumpgrok/core/idempotency.py:40-46]` Drop `correlation_id` before hashing, matching `derive_idempotency_key`. Do not call `IdFactory.ulid()` for the event id. A ULID moves when the RNG is consumed in a different order, which breaks dedup and drain parity.

Money fields on the event model are `int` with `Field(strict=True)`. No `float`. Prices, if any, are `Decimal` parsed from strings. Do not copy `1_000_000_000`. Import `LAMPORTS_PER_SOL` if a test needs the ceiling. The constant is:

```
LAMPORTS_PER_SOL = 1_000_000_000
```

`[VERIFIED: src/pumpgrok/core/units.py:12]`

### Pattern 3: Lanes, DLQ, retry, sidecar

**What:** Three in-memory lanes plus one sqlite file.
**When to use:** Every publish.

Named constants, all in `src/pumpgrok/events/constants.py`. Tests import these names. Do not inline the numbers in `bus.py`.

| Constant | Value | Rationale |
|----------|-------|-----------|
| `STALE_AFTER_S` | `120.0` | Same budget as `WS_STALE_S`. Comparison is `>`; 121 seconds of silence is stale. Do not import the supervisor constant. |
| `STABLE_S` | `30.0` | Same fresh window as `DATA_STALE_FRESH_WINDOW_S`. Backoff resets only after this much continuous health. |
| `BACKOFF_INITIAL_S` | `1.0` | Same first step as the seat restart schedule (1, 2, 4, 8, 16). |
| `BACKOFF_FACTOR` | `2` | Doubling, same schedule. |
| `BACKOFF_MAX_S` | `16.0` | Hold at the last seat-restart step. Do not grow without bound. |
| `BACKOFF_JITTER_S` | `1.0` | Uniform `[0, 1)` from `rng.random()`, added to the step. Seeded. |
| `RETRY_ATTEMPTS` | `5` | Five transient tries, then poison to the DLQ. Matches the seat restart count before latch. |
| `P0_LANE_CAP` | `None` | Unbounded. P0 is never dropped. |
| `P1_LANE_CAP` | `1000` | Same bound as `LEDGER_BUFFER_CAP`. The 1001st P1 event is written to the DLQ, not discarded. |
| `P2_COALESCE_CAP` | `1` | One pending event per coalesce key. |
| `P0_DEDUP_TTL_S` | `86400` | Persisted. A restarted process must not re-fire a kill or halt inside a day. |
| `P1_DEDUP_TTL_S` | `300` | Persisted. Market events may repeat after five minutes. |
| `P2_DEBOUNCE_S` | `1.0` | In-memory only. `mark` waits this long on the injected clock, then delivers the latest. `curve_tick` is latest-wins with no wait. |
| `EVENTS_SIDECAR_PATH` | `Path("var") / "desk" / "events.sqlite"` | Under `DESK_DATA_DIR`, not beside the ledger. |

Quoted anchors for those choices:

```
WS_STALE_S = 120.0
LEDGER_BUFFER_CAP = 1000
```

`[VERIFIED: src/pumpgrok/supervisor/scheduler/degraded.py:19-22]`

```
def ws_data_stale(self, now: float) -> bool:
    """DataStale trips after 120 s of WS silence."""
    if self.ws_last_frame_at is None:
        return False
    return now - self.ws_last_frame_at > WS_STALE_S
```

`[VERIFIED: src/pumpgrok/supervisor/scheduler/degraded.py:115-119]`

```
DATA_STALE_S = 120.0
DATA_STALE_MISSES = 3
DATA_STALE_COOLDOWN_S = 60.0
DATA_STALE_RESET_OK = 3
DATA_STALE_FRESH_WINDOW_S = 30.0
```

`[VERIFIED: src/pumpgrok/risk/breakers.py:48-52]`

```
PAPER_LEDGER_PATH = Path("var") / "ledger.sqlite"
DESK_DATA_DIR = Path("var") / "desk"
```

`[VERIFIED: src/pumpgrok/ledger/paths.py:19-23]`

Sidecar open copies the ledger connection shape, then points at a different path:

```
self._db = sqlite3.connect(str(self.path), isolation_level=None)
self._db.execute("PRAGMA journal_mode = WAL;")
self._db.execute("PRAGMA synchronous = FULL;")
self._db.execute("PRAGMA busy_timeout = 5000;")
```

`[VERIFIED: src/pumpgrok/ledger/store.py:140-143]`

Tables: `pending`, `applied`, `dedup`, `dlq`, `cursors`, `meta`. No hash chain. No `events` table name that could be confused with the ledger table; if a shared name is tempting, use `bus_pending` and `bus_dlq`. Refuse to open when `Path(path).resolve() == PAPER_LEDGER_PATH.resolve()`. The refusal names the constant path, never a payload. Tests pass `tmp_path / "events.sqlite"`.

P0 isolation: a P0 publish schedules a P0 handler task that does not await the in-flight P1 handler. A test parks a P1 handler on an `asyncio.Event` and asserts a later P0 handler runs before that event is set. Per-entity FIFO: two events with the same `entity_id` on the same lane run in publish order. Different entities may interleave.

Retry: catch only `TransientEventError`. Any other exception, including `PoisonEventError`, goes to the DLQ on the first failure. Jitter is `rng.random() * BACKOFF_JITTER_S` from the `random.Random` the caller passed. Do not construct `random.Random()` inside the package. `make_rng` is the only constructor:

```
def make_rng(seed: int = DEFAULT_SEED) -> random.Random:
    return random.Random(seed)
```

`[VERIFIED: src/pumpgrok/replay/rng.py:15-16]`

`DEFAULT_SEED = 20260101` matches the fixture `seed_hint`. `[VERIFIED: src/pumpgrok/replay/rng.py:12]` and `[VERIFIED: tests/fixtures/replay/smoke/manifest.json:5]`

Do not call `Clock.sleep` from the synchronous drain. `FixtureClock.sleep` waits until some other task calls `advance_to`. The drain calls `clock.advance_to` (or `jump`) itself, in `(when, seq)` order, then runs due retries. Async bus tests may `await clock.sleep` only if the test also advances the fixture clock. Production `WallClock.sleep` is not used under `events/`.

### Pattern 4: SourceSupervisor

**What:** One class owns reconnect backoff, staleness, resync, and cursors for event sources.
**When to use:** Tests and, later, Phase 13. Not the supervisor this phase.

`SourceStatus` is a `StrEnum` in `sources.py`: `live`, `stale`, `resyncing`, `disconnected`. It is not a second `EventKind`.

- Silence: `now - last_frame_at > STALE_AFTER_S` yields `SourceStatus.stale`. A source that has never framed is not stale (same shape as `ws_data_stale` returning false when `ws_last_frame_at is None`). 120.0 seconds is not stale. 121.0 seconds is stale.
- Backoff steps are `min(BACKOFF_INITIAL_S * BACKOFF_FACTOR**n, BACKOFF_MAX_S) + jitter`. A healthy frame before `STABLE_S` does not reset the step. A healthy span of `STABLE_S` resets to the initial step.
- `resync(held_mints: Sequence[str])` records the caller-supplied mint list and sets status `resyncing` until the next good frame. It does not open the ledger and does not fold `PositionOpened` rows. Phase 13 passes the mint list in. This phase's test passes `("mint-a", "mint-b")`.
- `load_cursor()` on invalid JSON or a bad schema version returns an empty cursor and writes a clean cursor back. It does not raise out of the supervisor constructor. The test can read a `cursor_reset` flag on the supervisor. Do not append a ledger row for this.
- Do not edit `src/pumpgrok/supervisor/scheduler/degraded.py`. `DegradedState.ws_data_stale` remains the cadence-path probe until Phase 14. "One staleness owner" in this phase means one owner inside `src/pumpgrok/events/` (`SourceSupervisor`), not a deletion of the supervisor probe.

### Pattern 5: CLI verb

**What:** `pumpgrok events dlq list|replay|purge`
**When to use:** Operator recovery of the sidecar. Copy the nested-parser shape of `scout` in `src/pumpgrok/cli/parsing.py` (`add_subparsers(dest="cmd", required=True)`).

Parser sketch:

- verb `events`, dest remains `verb`
- subparser `dlq`, dest `cmd`
- subparser actions `list`, `replay`, `purge`, dest `dlq_action`
- `replay` and `purge` take one or more event ids
- optional `--sidecar` defaults to `settings.events.sidecar_path`

Register `"events"` in `_VERB_HANDLERS` in `src/pumpgrok/cli/dispatch.py`. The handler is `_events_verb` in `src/pumpgrok/cli/events.py`. It opens the sidecar only. It does not call `run`, does not import `live_adapter`, and does not import `supervisor`.

`list` prints JSON rows and writes nothing. `replay` republishes each named id onto a bus constructed in the verb, then removes the DLQ row. `purge` deletes the named ids and does not republish. Unknown ids exit `EXIT_CONFIG` (1) with the id, not a payload. The verb works when `events.enabled` is false, because recovery is a file operation, not a live loop. It still must not open a socket.

Exit codes already in use, so do not invent a new one:

```
EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_LEDGER = 2
EXIT_LIVE = 3
```

`[VERIFIED: src/pumpgrok/cli/codes.py:10-13]`

### Pattern 6: Deterministic drain

**What:** `drain(events, *, seed, clock) -> bytes`
**When to use:** The parity test. Not `pumpgrok verify`.

The function is synchronous. It publishes in input order, advances the fixture clock through debounce and retry deadlines, and returns canonical JSON bytes of the delivery log (event id, kind, entity_id, handler outcome, in order). Two calls with the same input and seed return equal bytes.

Do not call `verify_fixture`, `cli.main`, or `run_once_replay` from this function. Those write `var/replay/<dataset>/ledger.sqlite` relative to the cwd. The trading-smoke ledger hash is a different object from the drain log. Do not assert they are equal.

Trading-smoke identity, for the test name and the seed only:

```
TRADING_SMOKE_FIXTURE = "smoke"
SMOKE_10M_EVENTS_HASH = "b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d"
```

`[VERIFIED: tests/replay/pin_support.py:37-38]`

```
"events_hash": "bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54",
"fixture": "smoke",
```

`[VERIFIED: tests/fixtures/replay/pins/trading_smoke.json:2-4]`

The smoke fixture is five tick rows in `tests/fixtures/replay/smoke/events.jsonl`. Read them. Do not write them. Map `kind: "tick"` to `EventKind.curve_tick` inside the test. Seed is `20260101`.

Do not add a `fixture_compat` test, skipped or not. Phase 14 owns that parity. A skipped test fails criterion 8 (`grep -q SKIPPED` must be empty).

### Pattern 7: Fault fakes

**What:** Add `FaultyEventSource` and `FaultyGrokTransport` to `tests/harness/faults.py`.
**When to use:** `tests/degradation/test_event_source_faults.py` and a harness import smoke in criterion 7.

Copy the existing fake style: a class that counts how often the fault fired, subclasses or raises `InjectedFault` / `TimeoutError`, and does not open a socket. `FaultyGrokTransport` has `request()` that raises. It stores no URL and imports no `httpx`. Export both from `tests/harness/__init__.py` `__all__` so `pytest tests/harness` still collects.

### Anti-Patterns to Avoid

- Importing `pumpgrok.events` from `supervisor`, `execution`, `engine`, or `replay.runner`. That wires the bus and can move the hash.
- Opening `PAPER_LEDGER_PATH` from `events/` or `cli/events.py`.
- Calling `datetime.now`, `time.time`, or `time.sleep` under `src/pumpgrok/events`. The static guard already bans those outside `replay/clock.py`. Criterion 9 greps the new tree as well.
- Using tenacity, `asyncio.sleep` (except `FixtureClock` internals, which events must not copy), or `random.random()`.
- A second `class EventKind`, including in tests under `src/`. The grep is `grep -rl 'class EventKind' src/pumpgrok`.
- Editing `LiveSettings`, `PlatformSettings`, `WalletSettings`, or any other class whose digest is in `PINNED_SECTION_DIGESTS`.
- Putting `wake_mode = "event"` in an overlay, or implementing seat wakes.
- Adding `solders`, `solana`, `sign`, `send_transaction`, `sendTransaction`, or `Keypair`. The signing guard is an AST exact-name scan of every `src/pumpgrok/**/*.py`.
- A skipped test in `tests/replay/test_event_drain_parity.py`.
- Rewriting `tests/fixtures/replay/smoke/events.jsonl`. The manifest pins its sha256.
- Copying `upgrade/scheduled.py` or a 3600 second promotion loop.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Canonical JSON | A new encoder | `canonical_json` | Float rejection and key order are already the hash-chain rule. A second encoder drifts. |
| Idempotency key width | A new hash scheme | sha256 hex, first 32 chars, same as `derive_idempotency_key` | One width across ledger and bus. |
| Time | A new clock | `Clock` / `FixtureClock.advance_to` | Replay determinism. `replay/clock.py` is the only module allowed to import `time`. |
| RNG | `random.Random()` in events | `make_rng(seed)` at the composition root | The static guard rejects an unseeded constructor. |
| sqlite connection | A new driver or a hash chain on the sidecar | The four PRAGMA lines from `LedgerStore.__init__` | WAL plus FULL sync is the desk pattern. The sidecar is not an audit chain. |
| Retry waits | tenacity | A counted loop and seeded jitter on the injected clock | tenacity sleeps on the host clock. |
| SOL conversion | A literal `1_000_000_000` in new src | `LAMPORTS_PER_SOL` | `units.py` is the one conversion. The cap tests already cover the ceiling. |
| Ledger append | Events package opening the paper ledger | A callback the test supplies | Keeps the sidecar off `var/ledger.sqlite`. |

**Key insight:** The hash stays put only if the new code is unreachable from `verify` and `run`. Isolation is the design, not a later cleanup.

## Common Pitfalls

### Pitfall 1: Surface test rejects the new fields

**What goes wrong:** `test_top_level_fields_are_pinned_in_order` fails as soon as `events` is added.
**Why it happens:** Line 85 asserts equality with `PRE_V4_FIELDS`. The docstring is looser than the assertion.
**How to avoid:** Change that one assertion to a prefix check in the same plan that adds the fields. Do not extend `PRE_V4_FIELDS`.
**Warning signs:** A digest mismatch. That means a PRE-v4 class was edited. Revert the class. Do not update the digest.

### Pitfall 2: Import-time side effect moves the hash

**What goes wrong:** `events/__init__.py` opens sqlite, or `settings.py` constructs an `EventBus`, and `verify` writes a different chain.
**Why it happens:** `load_settings()` runs on every verb, including `verify`.
**How to avoid:** Settings fields are data. The bus is constructed only by tests, the drain, and the `events dlq` verb.
**Warning signs:** A new import of `pumpgrok.events` in `replay/`, `supervisor/`, or `cli/verbs_ops.py`.

### Pitfall 3: Sidecar path resolves to the ledger

**What goes wrong:** A default of `var/ledger.sqlite`, or a relative path that joins onto it.
**Why it happens:** Copy-paste from `LedgerStore` examples in tests, which use `tmp_path / "ledger.sqlite"` as a paper ledger.
**How to avoid:** Constant `var/desk/events.sqlite`. Refuse equality with `PAPER_LEDGER_PATH` after `resolve()`. Tests use `tmp_path / "events.sqlite"`.
**Warning signs:** A test that chdir's to the repo root and then constructs the store with the default path. Those tests must chdir to `tmp_path` or pass an explicit path.

### Pitfall 4: P0 waits on P1

**What goes wrong:** One loop pops the highest priority only after the current handler returns, so a stuck P1 handler blocks P0.
**Why it happens:** A single queue with a priority sort is not isolation.
**How to avoid:** P0 handlers run on their own task. The P1 lane cannot await them, and they do not await P1.
**Warning signs:** The isolation test needs a timeout on the host clock. Use an `asyncio.Event` and a `FixtureClock`, not `time.sleep`.

### Pitfall 5: Derived id uses the RNG

**What goes wrong:** Dedup misses, and two drains differ, because each event drew a ULID.
**Why it happens:** `IdFactory` is the right tool for correlation ids and the wrong tool for event identity.
**How to avoid:** Hash the canonical payload. Pass one `make_rng(seed)` into retry jitter only, and consume it in a fixed order (one `random()` per retry attempt, attempts in event-id order).
**Warning signs:** Drain bytes change when an unused handler is added, or when test collection order changes.

### Pitfall 6: Corrupt cursor fails the process

**What goes wrong:** `json.loads` raises and the supervisor cannot start.
**Why it happens:** Treating corruption as fatal instead of "start clean".
**How to avoid:** Catch `json.JSONDecodeError` and `ValueError`, replace the cursor with `{}`, set a reset flag, return the empty cursor.
**Warning signs:** `test_sources.py` expects an exception. It should expect an empty cursor and a reset flag.

### Pitfall 7: Fixture `tick` becomes an EventKind

**What goes wrong:** The catalog grows a `tick` member to match `events.jsonl`, and Phase 13 then has two names for a curve update.
**Why it happens:** The fixture vocabulary is older than the v4 catalog.
**How to avoid:** Map in the test. Leave the fixture file alone.
**Warning signs:** A diff under `tests/fixtures/replay/smoke/`.

### Pitfall 8: Signing or network symbols in the new tree

**What goes wrong:** `tests/safety` fails, or live refusal changes.
**Why it happens:** A helper named `sign`, a `solders` import, or `socket` in the sidecar path.
**How to avoid:** sqlite3 only. No `httpx`, no `websockets`, no `socket`. `FaultyGrokTransport` raises; it does not connect.
**Warning signs:** `test_no_signing_outside_live_stub.py` or `test_import_graph_no_live.py` naming a new file.

### Pitfall 9: Coverage floor

**What goes wrong:** `make test` fails on coverage, not on a behavior assertion.
**Why it happens:** `fail_under = 89.9` with `branch = true` on source `pumpgrok`. `[VERIFIED: pyproject.toml tool.coverage.report]`
**How to avoid:** Every branch in `events/` and `config/sections/v4.py` has a test. Do not add `pragma: no cover` to skip the floor.
**Warning signs:** A new module imported by nothing the default suite collects.

### Pitfall 10: Journal and risk in one commit

**What goes wrong:** G-1 fails because `CHANGELOG.md` is `bot-09-journal` and the code is `bot-02-risk`.
**Why it happens:** Criterion 11 wants both the hash lines and the code.
**How to avoid:** Risk plans do not edit `CHANGELOG.md`. The journal plan adds only the four hash lines. Chief plans do not edit `src/` or `tests/`.

## Code Examples

Verified patterns from this repository. New code follows these shapes. It does not copy the bodies into the ledger or the supervisor.

### Clock protocol

```python
# Source: src/pumpgrok/replay/clock.py:22-33
class Clock(Protocol):
    def now(self) -> float: ...  # epoch seconds (UTC)
    def monotonic(self) -> float: ...
    def utc_iso(self) -> str: ...
    async def sleep(self, seconds: float) -> None: ...
    def timeout(self, seconds: float) -> AbstractAsyncContextManager[None]: ...
```

The drain uses `now` and `FixtureClock.advance_to`. It does not call `sleep`.

### Idempotency key

```python
# Source: src/pumpgrok/core/idempotency.py:49-65
def derive_idempotency_key(
    tool: str,
    bot: str,
    payload: Mapping[str, Any],
    *,
    scope: str | None = None,
) -> str:
    body = {k: v for k, v in payload.items() if k != "correlation_id"}
    digest = hashlib.sha256(
        canonical_json({"tool": tool, "bot": bot, "scope": scope, "payload": body}).encode()
    ).hexdigest()
    return digest[:32]
```

Handler ledger appends in the test use `idempotency_key=event.event_id`. The second delivery hits the existing unique key and writes no new row. Product `events/` does not import `LedgerStore`.

### Live cap, already pinned

```python
# Source: tests/safety/test_wallet_allowlist_settings.py:67-74
def test_live_notional_cap_defaults_to_one_sol() -> None:
    assert LiveSettings().notional_cap_lamports == 1_000_000_000


@pytest.mark.parametrize("cap", [0, 1_000_000_001])
def test_live_notional_cap_outside_range_is_rejected(cap: int) -> None:
    with pytest.raises(ValidationError):
        LiveSettings(notional_cap_lamports=cap)
```

`tests/config/test_live_settings_caps.py` repeats the refusal through `load_settings` / `Settings` without editing `LiveSettings`. A cap of `1_000_000_001` raises. A cap of `1_000_000_000` loads. Do not raise the ceiling.

### Signing ban

```python
# Source: tests/safety/test_no_signing_outside_live_stub.py:25-29
FORBIDDEN = frozenset({"sign", "send_transaction", "sendTransaction", "Keypair"})
BANNED_VENUE_IMPORTS = frozenset({"solders", "solana"})
```

New files under `src/pumpgrok/events/` and `src/pumpgrok/cli/events.py` must not contain these names.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Cadence supervisor tick | Stays the default through v4 | OD-20, still in force | This phase does not flip `wake_mode`. |
| `DegradedState.ws_data_stale` | Remains the cadence probe; `SourceSupervisor` is the new library owner | Phase 12 adds the library owner only | Do not delete `WS_STALE_S`. |
| Ledger `EventType` | Stays the ledger vocabulary | Unchanged | v4 `EventKind` is a different class in a different module. |
| No v4 settings sections | Ten sections, off | This phase | Overlays stay unchanged. |

**Deprecated/outdated:**

- `desk-built-ins` promotion cadence: do not port it.
- Fixture `kind: "tick"` as a bus kind: do not promote it into `EventKind`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---------|---------|---------------|
| A1 | EventKind member names in the table above | Pattern 2 | Phase 13 may expect different strings. Mitigation: one class, one module, names locked in `docs/design/events-grok.md` before Phase 13. Extending the enum is an edit to that module, not a second class. |
| A2 | `P0_DEDUP_TTL_S = 86400`, `P1_DEDUP_TTL_S = 300`, `P2_DEBOUNCE_S = 1.0` | Pattern 3 | Tests pin the constants, so a later change is a deliberate edit. Wrong TTL only affects how long a duplicate is suppressed. |
| A3 | `RETRY_ATTEMPTS = 5` and backoff `1,2,4,8,16` with jitter in `[0, 1)` | Pattern 3 | A different attempt count still satisfies EVT-05 if the test uses the constant. The rationale is consistency with seat restart, not a v4 spec line. |
| A4 | `P1_LANE_CAP = 1000` | Pattern 3 | Same as `LEDGER_BUFFER_CAP`. A smaller cap still satisfies overflow-to-DLQ. |
| A5 | Sidecar path `var/desk/events.sqlite` | Pattern 3 | Any path that is not `var/ledger.sqlite` meets the lock. This one sits under the existing desk dir. |
| A6 | `wake_mode` literal is only `"cadence"` in this phase | Pattern 1 | Phase 14 must widen the literal. Safer than accepting `"event"` before the wake path exists. |
| A7 | `paper_fees.model` literal is only `"v1"` | Pattern 1 | Phase 15 widens it when v2 becomes selectable. |
| A8 | DLQ verb runs when `events.enabled` is false | Pattern 5 | If the planner wants a hard refuse, the CLI test must expect exit 1. File recovery without a socket is the recommended reading of "off". |
| A9 | Errors live in `events/errors.py`, not `core/errors.py` | Don't Hand-Roll | CONTEXT allows either. This choice avoids editing `core/errors.py`. Codes: `event_transient`, `event_poison`, `event_cursor_corrupt`. |

**If this table is empty:** not empty. The planner should treat A1 as the item to lock in the design doc, and A2-A5 as constants the tests name.

## Open Questions

1. **Exact EventKind strings (RESOLVED)**
   - What we know: CONTEXT requires one class and priority as a function of kind. No design doc lists members. `docs/design/events-grok.md` is written by this phase (PROJECT.md says plan 12-02).
   - Resolution: Plan 12-02 locks the twelve names in docs/design/events-grok.md. No tick member. Phase 13 must map, not rename.
   - Recommendation: Lock the table in Pattern 2 in `docs/design/events-grok.md` in the models plan. Do not leave the names implicit in tests only.

2. **Whether core/errors.py should gain types (RESOLVED)**
   - What we know: No test pins the set of classes in that file. CONTEXT allows the events package to own its errors.
   - What's unclear: A later phase might look for event codes only in `core/errors.py`.
   - Resolution: events/errors.py owns PumpgrokError subclasses. Do not edit core/errors.py.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | runtime | yes | 3.12.3 |  -  |
| sqlite3 | sidecar | yes | 3.45.1 |  -  |
| uv | phase commands | yes | 0.13.4 |  -  |
| ruff | criterion 2 | yes | 0.15.18 |  -  |
| mypy | criterion 2 | yes | not recorded; binary is on PATH |  -  |
| pytest | named tests | yes | project dev group; `asyncio_mode = "auto"` |  -  |

Probes were version commands only. Lint, format, tests, and gates were not run.

**Missing dependencies with no fallback:** none

**Missing dependencies with fallback:** none

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest, `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"` `[VERIFIED: pyproject.toml tool.pytest.ini_options]` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]`; `addopts = "-q --strict-markers -m 'not slow'"` |
| Quick run command | `uv run pytest -q tests/events tests/config/test_v4_settings_skeleton.py tests/config/test_events_settings.py tests/config/test_live_settings_caps.py tests/cli/test_events_cli.py tests/degradation/test_event_source_faults.py tests/replay/test_event_drain_parity.py tests/safety/test_events_not_wired.py` |
| Full suite command | `make test` |

New tests are not marked `slow`. The default addopts exclude `slow`. A `skip` or `xfail` in the drain file fails criterion 8.

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PRC-11 | Ten sections exist once, off, absent TOML loads | unit | `uv run pytest -q tests/config/test_v4_settings_skeleton.py tests/config/test_events_settings.py` | no, Wave 0 |
| PRC-11 | Cap above 1 SOL refuses, class unedited | unit | `uv run pytest -q tests/config/test_live_settings_caps.py` | no, Wave 0 |
| EVT-01 | Derived id, priority by kind, int money | unit | `uv run pytest -q tests/events/test_models.py` | no, Wave 0 |
| EVT-02 | P0 kept, P1 to DLQ, P2 coalesced | unit | `uv run pytest -q tests/events/test_bus_backpressure.py` | no, Wave 0 |
| EVT-03 | FIFO per entity, P0 not blocked by P1 | unit | `uv run pytest -q tests/events/test_bus_lanes.py` | no, Wave 0 |
| EVT-04 | Dedup TTL and coalesce on FixtureClock | unit | `uv run pytest -q tests/events/test_bus_dedup_coalesce.py` | no, Wave 0 |
| EVT-05 | Transient retry, poison DLQ, CLI replay | unit | `uv run pytest -q tests/events/test_bus_retry_dlq.py tests/cli/test_events_cli.py` | no, Wave 0 |
| EVT-06 | Second delivery adds no ledger row | unit | `uv run pytest -q tests/events/test_handler_idempotency.py` | no, Wave 0 |
| EVT-07 | Shutdown and recover exactly once | unit | `uv run pytest -q tests/events/test_bus_shutdown.py` | no, Wave 0 |
| EVT-08 first half | Two drains match; trading-smoke parity; no skips | unit | `uv run pytest -q tests/replay/test_event_drain_parity.py -k determinism` and `-k smoke_trading` | no, Wave 0 |
| EVT-09 | Backoff, 121s stale, resync, corrupt cursor | unit | `uv run pytest -q tests/events/test_sources.py tests/degradation/test_event_source_faults.py` | no, Wave 0 |
| EVT-14 | One EventKind, one events-package staleness owner | unit | `uv run pytest -q tests/events/test_models_v4_kinds.py` | no, Wave 0 |

### How each success-criterion file should be structured

Shared fixture, in `tests/events/conftest.py` if more than one file needs it: a `FixtureClock` at `0.0`, `make_rng(20260101)`, and a store pointed at `tmp_path / "events.sqlite"`. No test chdir's to the repo root unless it is proving the default path, and that test must not leave a file at `var/desk/events.sqlite` (use `tmp_path` and monkeypatch the cwd, then assert the repo `var/ledger.sqlite` was not created).

1. `tests/config/test_v4_settings_skeleton.py` (criterion 2, PRC-11)
   - `EXPECTED_V4_FIELDS` is the ten names in append order.
   - `test_v4_fields_are_the_suffix_after_pre_v4` asserts `tuple(Settings.model_fields)[len(PRE_V4_FIELDS):] == EXPECTED_V4_FIELDS`.
   - `test_each_v4_section_defaults_off` builds `Settings()` and asserts `enabled is False` and `allowlist == ()` on every new section.
   - `test_absent_toml_sections_stay_off` writes a temp TOML with only `[execution] mode = "paper"`, sets `PUMPGROK_CONFIG`, and loads. No `ValidationError`.
   - `test_unknown_v4_key_is_forbidden` puts `events.socket = "x"` in TOML and expects `ConfigError` or `ValidationError`. The message must not echo a secret; this key is not a secret.
   - `test_no_section_class_is_duplicated` asserts each annotation appears once in `Settings.model_fields`.

2. `tests/config/test_events_settings.py` (criterion 2)
   - `test_wake_mode_defaults_to_cadence`.
   - `test_event_mode_literal_is_rejected` expects `ValidationError` on `wake_mode="event"`.
   - `test_sidecar_default_is_not_the_paper_ledger` asserts the default path is `var/desk/events.sqlite` and is not `PAPER_LEDGER_PATH`.
   - `test_enabled_true_does_not_open_a_socket` loads with `enabled=True` via init kwargs and asserts no bus was constructed (importing settings does not import `pumpgrok.events.bus` as a side effect of load). Do not start a server.

3. `tests/config/test_live_settings_caps.py` (criterion 2)
   - Do not import-edit `LiveSettings`. Construct `Settings(live={"notional_cap_lamports": 1_000_000_001})` or the TOML equivalent and expect refusal.
   - Accept `1` and `1_000_000_000`.
   - Assert `LiveSettings` field default is still `LAMPORTS_PER_SOL` by reading the class, not by rewriting it.
   - One test that `PlatformSettings` and `WalletSettings` still construct with their current defaults, so a future edit to those classes fails here too. Do not change the classes to make this pass.

4. `tests/events/test_models.py` (criterion 3, EVT-01)
   - `test_event_id_is_a_function_of_kind_entity_and_payload`: same inputs, same 32-hex id; a payload change changes the id.
   - `test_priority_is_a_function_of_kind`: P0 kinds return 0, P1 return 1, P2 return 2. No priority argument on the constructor.
   - `test_float_money_is_rejected`: a float lamports field raises. An int is accepted.
   - `test_model_is_frozen`: assignment raises.
   - No clock and no sqlite in this file.

5. `tests/events/test_bus_lanes.py` (criterion 3, EVT-03)
   - `test_same_entity_is_fifo`: three events, one `entity_id`, handler log equals publish order.
   - `test_p0_runs_while_p1_is_parked`: P1 handler waits on an `asyncio.Event`; P0 handler appends to a list before that event is set.
   - Use `pytest-asyncio` (mode is `auto`). Do not `time.sleep`.

6. `tests/events/test_bus_backpressure.py` (criterion 3, EVT-02)
   - `test_p0_above_cap_is_still_delivered`: publish `P1_LANE_CAP + 5` P0 events; all are delivered; DLQ count for those ids is 0.
   - `test_p1_overflow_is_persisted`: publish `P1_LANE_CAP + 1` P1 events with a handler that does not run; the extra id is in the sidecar DLQ.
   - `test_p2_coalesce_keeps_latest`: three `curve_tick` events, same entity, one delivery, the last payload.

7. `tests/events/test_bus_dedup_coalesce.py` (criterion 4, EVT-04)
   - `test_p0_dedup_survives_reopen`: publish, close the store, reopen the same tmp file, publish the same id, handler count stays 1. Advance the clock by `P0_DEDUP_TTL_S + 1` and assert a new delivery.
   - `test_p1_dedup_expires_on_fixture_clock`: same shape with `P1_DEDUP_TTL_S`.
   - `test_mark_debounce_uses_clock`: two `mark` events inside `P2_DEBOUNCE_S` collapse; `advance_to` past the window delivers one, the latest. No `datetime.now`.

8. `tests/events/test_bus_retry_dlq.py` (criterion 4, EVT-05)
   - `test_transient_retries_then_delivers`: handler raises `TransientEventError` twice, then succeeds. Attempt count is 3. Jitter consumed from a known seed; a second bus with the same seed records the same delays.
   - `test_poison_goes_to_dlq_without_retry`: `PoisonEventError` on the first call; DLQ has one row; handler count is 1.
   - `test_attempt_cap_poisons`: `RETRY_ATTEMPTS` transient failures, then DLQ.

9. `tests/cli/test_events_cli.py` (criterion 4, EVT-05)
   - Call `pumpgrok.cli.main` with `["events", "dlq", "list"]` and a temp sidecar via `--sidecar` or `PUMPGROK_EVENTS__SIDECAR_PATH`.
   - `test_replay_republishes`: seed a DLQ row, run `replay <id>`, assert the handler saw it and the row is gone.
   - `test_purge_drops`: seed a row, run `purge <id>`, assert it is gone and the handler was not called.
   - `test_verb_does_not_open_the_paper_ledger`: after the call, `var/ledger.sqlite` does not exist in the tmp cwd.
   - Do not mark skip.

10. `tests/events/test_handler_idempotency.py` (criterion 5, EVT-06)
    - Build a `LedgerStore` at `tmp_path / "ledger.sqlite"` (this is a paper ledger for the test, not the sidecar, and not `var/ledger.sqlite`).
    - Handler appends with `idempotency_key=event.event_id`.
    - Call the handler twice. `store.read()` length is unchanged on the second call.
    - Assert the sidecar path used by the bus is a different file from that ledger path.

11. `tests/events/test_bus_shutdown.py` (criterion 5, EVT-07)
    - Publish two events, do not run handlers, call `shutdown()`.
    - Reopen from the same sidecar. `recover()` returns each id once. A second `recover()` returns nothing.
    - Crash substitute: construct a second bus on the same file without calling recover twice in-process, and assert the pending rows are still there until recover.

12. `tests/events/test_sources.py` (criterion 6 and 7, EVT-09, EVT-14)
    - `test_backoff_resets_only_after_stable_s`: fail once, frame at `STABLE_S - 1`, assert the next delay is still the second step; frame and advance `STABLE_S`, assert the next delay is the initial step.
    - `test_121_seconds_is_stale`: `note_frame(0)`, `status_at(120.0)` is not stale, `status_at(121.0)` is `SourceStatus.stale`.
    - `test_resync_seeds_held_mints`: `resync(("mint-a", "mint-b"))` exposes that pair. No ledger import.
    - `test_corrupt_cursor_starts_clean`: write `{` into the cursor row, load, assert empty cursor and reset flag, and a second load stays clean.
    - `test_one_staleness_owner`: the module that defines `SourceSupervisor` is `pumpgrok.events.sources`, and `events/` does not import `DegradedState`.

13. `tests/degradation/test_event_source_faults.py` (criterion 6, EVT-09)
    - Use `FaultyEventSource` from `tests/harness/faults.py`.
    - `test_silent_source_trips_stale`: no frame, advance 121 seconds, status stale. Assert the fake's fire count so a skipped fault cannot pass.
    - `test_fault_then_stable_window_resets_backoff`.
    - `test_malformed_cursor_from_source_starts_clean`.
    - No network. `FaultyGrokTransport` is constructed and asserted to raise `TimeoutError` or `InjectedFault` without a socket. That is the whole Grok fake test. Do not add a gateway module.

14. `tests/events/test_models_v4_kinds.py` (criterion 7, EVT-14)
    - `test_event_kind_class_is_unique`: subprocess or in-process grep is the criterion command, not this test. This test imports `EventKind` from `pumpgrok.events.models` and asserts `EventKind.__module__ == "pumpgrok.events.models"`.
    - `test_ledger_module_has_no_event_kind_class`: `hasattr` on `pumpgrok.ledger.events` is false for `EventKind`.
    - `test_priority_table_covers_every_member`: every member has a priority; no extra keys.

15. `tests/replay/test_event_drain_parity.py` (criterion 8, EVT-08 first half)
    - `test_determinism_two_drains_match`: build a fixed list of three events, `drain` twice with seed `20260101`, assert equal bytes, assert pending count 0 (quiescence).
    - `test_smoke_trading_drain_matches_itself`: read `tests/fixtures/replay/smoke/events.jsonl`, map ticks to `curve_tick`, drain twice with seed `20260101`, assert equal bytes and quiescence. Do not call `verify`. Do not compare to `bdcbe2d3...` or `b69c2959...`.
    - No other tests. No `pytest.mark.skip`. No `fixture_compat` test.

16. `tests/safety/test_events_not_wired.py` (criterion 9, supports the import rule)
    - AST-scan `supervisor/`, `execution/`, `engine/`, and `replay/` for an import of `pumpgrok.events`.
    - AST-scan `events/` for an import of `supervisor`, `execution`, `engine`, or `live_adapter`.
    - This file is new. The existing `test_import_graph_no_live.py` does not know about `events`. Keep that file green by not importing `live_adapter` from the CLI closure. The CLI is a guarded root. `[VERIFIED: tests/safety/test_import_graph_no_live.py:32-40]`

17. `tests/harness/faults.py` and `tests/config/` (criterion 7 command `uv run pytest -q tests/events/test_models_v4_kinds.py tests/harness tests/config`)
    - Existing harness and config tests must still pass. Adding fakes must not change `FaultInjector` behavior.
    - Do not put a collection error in `tests/harness/__init__.py`. If `__all__` grows, update the import list in that file in the same edit.

Criterion 1 (`make lint`, `make typecheck`, `make test`, `./scripts/check.sh`, paper smoke run) is the phase gate, not a new file.

Criterion 9 also greps `src/pumpgrok/events` for `datetime.now`, `datetime.utcnow`, `time.time(`, and `time.sleep(`. The events package must not contain those calls. Comments that mention the banned names are safe for the static AST guard (it ignores docstrings and comments) but the criterion grep is text. Do not put those call spellings in comments under `events/`.

Criterion 10 is a git command. No test file. Do not touch `contracts/`.

Criterion 11 is `CHANGELOG.md` lines, exact:

```
Phase 12: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
Phase 12: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
Phase 12: trading-smoke events.hash before: bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54
Phase 12: trading-smoke events.hash after: bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54
```

The after lines use the same hashes. This phase does not re-pin. Journal owns the file. Place them under a new `## [Unreleased] - v4 Phase 12: event runtime core` heading, in a `### Verified` list, matching the Phase 11 shape in `CHANGELOG.md`. Do not edit the Phase 11 lines.

Criterion 12 is the existing live refusal. Do not edit `src/pumpgrok/cli/verbs_state.py` live path. `EXIT_LIVE` is 3.

### Sampling Rate

- **Per task commit:** the quick command for the files that task added.
- **Per wave merge:** `uv run pytest -q tests/events tests/config tests/cli/test_events_cli.py tests/degradation/test_event_source_faults.py tests/replay/test_event_drain_parity.py tests/safety/test_events_not_wired.py tests/harness`
- **Phase gate:** Full suite green before `/gsd:verify-work`, plus the twelve roadmap commands. The main agent runs those. This research did not run them.

### Wave 0 Gaps

- [ ] `src/pumpgrok/config/sections/v4.py`  -  PRC-11 classes
- [ ] `src/pumpgrok/events/`  -  the library
- [ ] `src/pumpgrok/cli/events.py`  -  DLQ verb
- [ ] `tests/config/test_v4_settings_skeleton.py`  -  PRC-11
- [ ] `tests/config/test_events_settings.py`  -  events section
- [ ] `tests/config/test_live_settings_caps.py`  -  cap refusal without editing `LiveSettings`
- [ ] `tests/events/test_models.py`  -  EVT-01
- [ ] `tests/events/test_bus_lanes.py`  -  EVT-03
- [ ] `tests/events/test_bus_backpressure.py`  -  EVT-02
- [ ] `tests/events/test_bus_dedup_coalesce.py`  -  EVT-04
- [ ] `tests/events/test_bus_retry_dlq.py`  -  EVT-05
- [ ] `tests/events/test_handler_idempotency.py`  -  EVT-06
- [ ] `tests/events/test_bus_shutdown.py`  -  EVT-07
- [ ] `tests/events/test_sources.py`  -  EVT-09, EVT-14
- [ ] `tests/events/test_models_v4_kinds.py`  -  EVT-14
- [ ] `tests/cli/test_events_cli.py`  -  EVT-05
- [ ] `tests/degradation/test_event_source_faults.py`  -  EVT-09
- [ ] `tests/replay/test_event_drain_parity.py`  -  EVT-08 first half
- [ ] `tests/safety/test_events_not_wired.py`  -  import isolation
- [ ] `docs/design/events-grok.md`  -  catalog and constants, no gateway
- [ ] Prefix assertion in `tests/config/test_settings_surface_characterization.py`
- [ ] `FaultyEventSource` and `FaultyGrokTransport` in `tests/harness/faults.py`
- [ ] CHANGELOG hash lines, journal seat only

Framework install: none. pytest is already the suite.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | No new login. The DLQ verb is a local CLI. |
| V3 Session Management | no | No session. |
| V4 Access Control | yes | The verb does not gain a live-write path. CLI stays inside the existing import-graph guard. No `live_adapter` import. |
| V5 Input Validation | yes | pydantic `extra="forbid"` on every new model. `canonical_json` rejects floats. Cursor JSON that does not parse starts clean instead of being trusted. DLQ ids that are absent are refused by id, not executed. |
| V6 Cryptography | no | sha256 for ids only, via `hashlib`, the same function the ledger uses. No signing. No new cipher. |

### Known Threat Patterns for this library

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Sidecar path pointed at `var/ledger.sqlite` | Tampering | Resolve and refuse `PAPER_LEDGER_PATH` before `sqlite3.connect`. |
| Float money in an event payload | Tampering | `canonical_json` plus strict int fields. |
| Double delivery writes a second fill | Tampering | Handler idempotency key equals the derived event id. Test uses a tmp ledger. |
| Poison event retried forever | Denial of service | Non-transient errors DLQ on the first failure. Transient errors stop at `RETRY_ATTEMPTS`. |
| Host clock in retry or debounce | Repudiation / replay break | Injected `Clock` only. Criterion 9 grep. |
| Signing symbol or `solders` import | Elevation | AST guard. Do not add those names. |
| Error text echoing a wallet or key | Information disclosure | Follow `ConfigError`: names and indexes, never values. Wallet allowlist code already does this; do not reimplement it. |
| DLQ replay as a hidden live send | Elevation | Replay republishes onto the in-process bus. No adapter. No socket. |
| Gateway built "while here" | Elevation | `FaultyGrokTransport` raises. No `src/pumpgrok/grok/`. |

## Sources

### Primary (HIGH confidence)

- `tests/config/test_settings_surface_characterization.py:6-7,21-41,84-85`  -  pin tuple, docstring, blocking assertion.
- `src/pumpgrok/config/settings.py:140-169`  -  field order ending at `health`.
- `src/pumpgrok/config/sections/core.py:132-198`  -  pinned platform, wallet, and live classes. Not edited.
- `src/pumpgrok/ledger/events.py:52-72`  -  ledger `EventType`, not `EventKind`.
- `src/pumpgrok/ledger/paths.py:19-23`  -  ledger path and desk dir.
- `src/pumpgrok/ledger/store.py:140-143`  -  sqlite open and PRAGMAs.
- `src/pumpgrok/replay/clock.py:22-33,101-112`  -  `Clock` and `advance_to`.
- `src/pumpgrok/replay/rng.py:12-16`  -  `make_rng`.
- `src/pumpgrok/core/idempotency.py:40-65`  -  canonical JSON and key width.
- `src/pumpgrok/core/units.py:12`  -  `LAMPORTS_PER_SOL`.
- `src/pumpgrok/supervisor/scheduler/degraded.py:19-22,115-119`  -  120s stale comparison and buffer cap.
- `src/pumpgrok/risk/breakers.py:48-52`  -  30s fresh window.
- `src/pumpgrok/cli/dispatch.py:36-47`  -  verb handler map.
- `src/pumpgrok/cli/codes.py:10-13`  -  exit codes.
- `tests/safety/test_no_signing_outside_live_stub.py:25-29`  -  banned names.
- `tests/safety/test_import_graph_no_live.py:32-40`  -  CLI is a guarded root.
- `tests/replay/pin_support.py:37-38` and `tests/fixtures/replay/pins/trading_smoke.json:2-4`  -  hashes that must not move.
- `tests/fixtures/replay/smoke/manifest.json` and `events.jsonl`  -  fixture shape and `kind: "tick"`.
- `pyproject.toml`  -  pydantic bounds, pytest asyncio mode, coverage `fail_under = 89.9`.
- `ownership.yaml`  -  last-match owners for the new paths.
- `.planning/phases/12-event-runtime-core/12-CONTEXT.md`  -  locked decisions.
- `.planning/ROADMAP.md` Phase 12 success criteria, including criterion 11 hash lines.
- `.planning/REQUIREMENTS.md` EVT-01 through EVT-09, EVT-14, PRC-11.

### Secondary (MEDIUM confidence)

- Seat restart backoff shape `1,2,4,8,16` with jitter in `[0, 1)`, cited from `docs/design/paper-engine.md` test plan text in this repo. Used only as the rationale for matching that schedule. The events constants are still discretion.

### Tertiary (LOW confidence)

- None. Kind names and TTL numbers are tagged `[ASSUMED]` in the assumptions log rather than presented as verified.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH  -  no new package; pydantic and sqlite3 are already the desk stack.
- Architecture: HIGH  -  module split and isolation follow CONTEXT and the files read this session.
- Pitfalls: HIGH for the surface-test assertion and the hash-isolation rule, because both were read in source. MEDIUM for TTL numbers, which are discretion.

**Research date:** 2026-11-08
**Valid until:** 2026-12-08 for the in-repo patterns. Re-check if `Settings` field order or `PRE_V4_FIELDS` changes before planning.

## Plan Split (for the planner)

Roadmap ids are 12-01 through 12-05, five waves. Suggested file cuts, one seat per plan:

| Plan | Seat | Files | Proves |
|------|------|-------|--------|
| 12-01 | bot-02-risk | `config/sections/v4.py`, `settings.py` append, surface-test prefix assertion, three config tests | PRC-11, cap refusal, digests unchanged |
| 12-02 | bot-02-risk | `events/models.py`, `constants.py`, `errors.py`, `bus.py` lanes and backpressure, `docs/design/events-grok.md`, model and lane tests, harness fakes | EVT-01, EVT-02, EVT-03, EVT-14 catalog half |
| 12-03 | bot-02-risk | `store.py`, `dlq.py`, retry and shutdown in `bus.py`, `cli/events.py`, parsing and dispatch registration, retry, shutdown, idempotency, CLI tests | EVT-04, EVT-05, EVT-06, EVT-07 |
| 12-04 | bot-02-risk | `sources.py`, degradation test, `test_sources.py`, `test_models_v4_kinds.py`, `test_events_not_wired.py` | EVT-09, EVT-14 owner half |
| 12-05 | bot-02-risk for the drain test; bot-09-journal for CHANGELOG only | `drain.py`, `tests/replay/test_event_drain_parity.py`, CHANGELOG hash lines in a separate journal commit | EVT-08 first half, PRC-03 hash lines |

Do not put `CHANGELOG.md` in a risk plan. Do not put `src/` in a chief plan. Do not start 12-06. There is no Phase 13 plan in this run.

## Planner Notes

- The surface-test prefix edit is required. It is not a pin move.
- Do not edit PRE-v4 classes. Do not edit overlays. Do not edit `contracts/`. Do not edit `degraded.py`. Do not edit `verbs_state.py` live refusal.
- Do not merge `desk-built-ins`. Do not port the 3600 second promotion.
- `FaultyGrokTransport` is a raising fake. There is no Grok gateway in this phase.
- smoke-10m fixture_compat is Phase 14. The drain file must not contain a skipped test for it.
- Hash lines are copies of the known pins, not a remeasure. If a measure is run, it must use a temp cwd, the way `pin_support.py` does, and the measured hash must equal the pin or the implementation imported the bus into `verify`.
