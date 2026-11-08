# Phase 12: Event runtime core - Context

**Gathered:** 2026-11-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a typed, bounded, deterministic event runtime as a library, plus the missing v4 settings sections, config-gated off. The bus is not wired into the supervisor. The replay path and the smoke-10m hash stay untouched. Live stays refused.

This phase covers EVT-01, EVT-02, EVT-03, EVT-04, EVT-05, EVT-06, EVT-07, EVT-09, EVT-14, and PRC-11, plus the first half of EVT-08 (deterministic drain and trading-smoke parity). Fixture-compat parity against smoke-10m is Phase 14. Event-mode wake, Grok gateway, Hermes cutover, and idle-zero-Grok are Phase 14 (EVT-10, EVT-12, EVT-13, GRK-*). Curve layout, live feed, and recorder sealing are Phase 13.

</domain>

<decisions>
## Implementation Decisions

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

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- `src/pumpgrok/config/sections/` and `src/pumpgrok/config/settings.py`: section classes plus one field per section. PRE-v4 digests in `tests/config/test_settings_surface_characterization.py`.
- `src/pumpgrok/config/sections/core.py`: `PlatformSettings`, `WalletSettings`, `LiveSettings` with the 1 SOL cap. Do not edit.
- `src/pumpgrok/replay/clock.py`: `Clock`, `WallClock`, `FixtureClock`. Sole time allowlist.
- `src/pumpgrok/replay/rng.py`: seeded RNG. `os.urandom` is confined to `core/ids.py` and `core/binding_key.py`.
- `src/pumpgrok/ledger/events.py`: ledger event vocabulary. Not the v4 `EventKind` catalog.
- `src/pumpgrok/ledger/desk_bus.py`: atomic tmp plus `os.replace` mirror. Not an event bus.
- `src/pumpgrok/replay/sources.py`: `FixtureEventSource` for replay. The new supervisor must not replace it in this phase.
- `tests/harness/faults.py`: existing fault fakes. Add the two new fakes here.
- `src/pumpgrok/cli/dispatch.py`: verb registration pattern for `events`.

### Established Patterns

- Integer money, `Decimal` only for ratios. ULIDs from `core/ids.py`.
- Frozen pydantic models, `extra="forbid"`.
- Fail closed. A bad config value raises `ConfigError` or `ValidationError` mapped to a name, never the value.
- Tests follow the module they pin. New event tests live under `tests/events/`. Config tests under `tests/config/`.

### Integration Points

- Settings composition in `config/settings.py` (new fields only).
- CLI dispatch in `src/pumpgrok/cli/dispatch.py` for `pumpgrok events`.
- No import from `events` into `supervisor`, `execution`, `engine`, or the live adapter. The import-graph guard must stay green.
- Sidecar store is separate from `ledger/store.py`.

</code_context>

<specifics>
## Specific Ideas

The operator wants event-driven routines so idle time does not spend Grok credits. That behavior is Phase 14 (`wake_mode=event`, idle-zero-Grok). This phase builds the library those routines will sit on. Cadence stays the default (OD-20).

Platform for paper and for any later live decision remains pump.fun bonding-curve fills, PumpPortal websocket plus pump.fun REST, Jupiter Swap V2 quote-only, Solana mainnet JSON-RPC, x.ai Grok. No second venue. No devnet execution path.

</specifics>

<deferred>
## Deferred Ideas

- Wiring the bus into the supervisor, event-mode seat wakes, Hermes cron cutover, Grok gateway, idle-zero-Grok measurement (Phase 14).
- Flipping the default `wake_mode` to event (next milestone after a week of live-paper evidence, OD-20).
- Curve-layout probe review, live market data, recorder sealing (Phase 13). Human review is required before any VERIFIED flip.
- ONB-06 curve-point check and operator address confirmation (Phase 14).
- Enabling live, funding a wallet, devnet airdrops, and a $200 mainnet book. v4 builds the live path dormant in Phase 18 and never enables it. Notional cap stays at most 1.0 SOL.
- Scheduled promotion cadence from `desk-built-ins`. Not this phase.
- Phase 13 and later. This autonomous run stops at the Phase 12 ship checkpoint.

</deferred>
