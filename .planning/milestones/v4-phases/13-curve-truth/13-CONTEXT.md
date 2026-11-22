# Phase 13: Curve truth, live market data and recorder - Context

**Gathered:** 2026-11-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Correct the bonding-curve account layout to the official token-first order (49 and
166 byte accounts), probe it read-only against live mainnet accounts, make the paper
fee model v2 selectable (v1 stays the default) with a paper factory and an entry-gate
hook, and build a bounded, rate-limited, read-only live feed that produces integer
ticks, a fail-closed `LivePriceSource`, marks for held mints, and a recorder that seals
self-verifying datasets with gaps recorded. The datafeed events are bridged onto the
Phase 12 event bus. `LAYOUT_STATUS` and `EVENT_DECODE_STATUS` become `VERIFIED` only
after a human review. Live trading stays refused (`run --mode live` exits 3) and
nothing in this phase can send a transaction.

This phase covers MKT-01, MKT-02, MKT-03, MKT-04, MKT-05, MKT-06, MKT-07, MKT-08,
MKT-10, REC-01 and REC-02, plus the selectable half of FEE-01 (the default flip and
its trading-smoke re-pin are Phase 15), the first half of MKT-09 (the read-only
allowlist; the composition-root test completes in Phase 15), and the Phase 13
PRC-03 hash pair. Recorder CLI verbs (`run --record`, `replay trim`, `replay import`)
are Phase 16 (REC-03). Effort is 7 plans (13-01 to 13-07) in 6 waves, matching the
v4 plan index list of record; plan 13-05 is human-gated.

## Out of scope

- Live trading enablement, signing, custody, wallet funding, any send path. No key
  material enters the desk package. The desk keeps zero signing symbols.
- PumpPortal trade-stream key (R45, default no): trade events come from Solana
  JSON-RPC `logsSubscribe` on bonding-curve accounts (R46), not from a funded stream.
- Paid RPC procurement or spend (V4-13): defaults use the public mainnet endpoint
  with a reduced watch set. A human may choose and record a provider later; no v4
  code assumes one.
- PumpSwap sells and post-graduation CPMM modelling (OD-08). Live-eligible
  strategies exit before the curve completes.
- The composition-root no-send proof (`supervisor/live_paper.py`, MKT-09 second half,
  Phase 15) and the `run --mode live` refusal change (none; it stays exit 3).
- Event-mode supervisor wake, Grok gateway, Hermes cutover (Phase 14).
- Strategy runtime and the fee v2 default flip (Phase 15). Backtest v2 and the
  recorder CLI (Phase 16). Runbooks are Phase 19 (OBS-04); this phase ships
  docstrings and `docs/CURVE_LAYOUT_PROBE.md` only.
- Constitution amendments. Drafted for the owner, applied only by a human-approved
  PR (Phase 18, PRC-07). This phase changes no `contracts/` surface.

</domain>

<decisions>
## Implementation Decisions

### D-01 Token-first layout, both sizes (MKT-01)

- `src/pumpgrok/tools/onchain/curve_layout.py` decodes the official token-first
  order. Both the 49 byte account (the current `<8sQQQQQB` shape, 8 discriminator +
  five u64 counters + completion flag) and the 166 byte account (the same counters
  plus the token-mint and related pubkeys) must decode. A bad discriminator is
  rejected with `CurveDecodeError`. Field order, not just length, is what changes:
  the current layout is SOL-first in effect and stays `ASSUMED` until the probe
  records the official order.
- `CurveState` keeps its existing field names (integer lamports/units only,
  `Decimal` for ratios). New fields for the 166 byte variant (e.g. token mint) are
  added with defaults so `tools/market/price.py`, `tools/market/liquidity.py` and
  `execution/paper_adapter/{buy,confirm_stages}.py` keep compiling unchanged.
- `encode_curve_fixture` must be able to build both sizes; the 49 byte call stays
  backward compatible so existing tests do not drift.

### D-02 Statuses stay ASSUMED by default; VERIFIED only by a human (MKT-03, MKT-10)

- `LAYOUT_STATUS` in `curve_layout.py` and new `EVENT_DECODE_STATUS` in
  `pump_events.py` both ship as `"ASSUMED"`. A `VERIFIED` literal must not
  appear as a default anywhere in `src/pumpgrok`.
- The flip to `VERIFIED` needs a human-set `reviewed_by` (name + date, recorded in
  the probe record and as a code comment beside the constant). No plan sets
  `reviewed_by`; plan 13-05 records `decoded_pending_review` and stops at a
  `checkpoint:human-verify`. If the human does not review, the record stays
  `ASSUMED` with the exact probe error and the phase still closes.
- While `ASSUMED`, `rpc_curve_price_allowed` keeps failing closed: `curve_source ==
  "rpc"` refuses paper entries with `data_unavailable`. Replay sources stay allowed.

### D-03 Price gate is an allowlist (MKT-04)

- `rpc_curve_price_allowed` is the single gate: unknown and unverified sources are
  refused; replay and fixture sources are allowed. Execution tests must be
  status-agnostic and pass before and after the layout rewrite (ROADMAP criterion 5).
  No second price policy is added in `execution/`; the entry hook (13-03) calls this
  gate.

### D-04 Integer ticks and one token-first truth (MKT-05 to MKT-08)

- All feed ticks carry integer lamports/base units. No float money anywhere under
  `src/pumpgrok/datafeed/`. Ratios stay `Decimal`.
- The watch set never exceeds its cap (named constant in settings, default bounded
  for the public endpoint per V4-13). Held mints are pinned and never evicted by a
  new discovery; overflow is counted, never silently dropped.
- A `FaultInjector` TIMEOUT reconnect yields no duplicate signature, emits gap
  events, and honors the 30 per 10 s limiter. Gap events are first-class bus events
  (`EventKind` mapping in `events/models.py`, extended in 13-01 if a kind is
  missing; one catalog, no second `EventKind`).
- `LivePriceSource` fails closed: `None` when disconnected, completed curve refuses
  entry, a gap holds the position, a timeout marks zero. Marks: every held mint is
  marked within 60 s on an injected `Clock`; no timer or task exists while flat.

### D-05 Read-only by construction (MKT-06, MKT-09 first half)

- PumpPortal use is limited to the free methods `subscribeNewToken` and
  `subscribeMigration` (R45). No trade-stream key, no wallet, no signing.
- Trade events come from `logsSubscribe` on bonding-curve PDAs with bounded
  `getTransaction` follow-ups (R46). The RPC method allowlist is explicit:
  `getAccountInfo`, `logsSubscribe`, `getTransaction`, plus the market-data reads
  already in the repo. Any other method is refused in `readonly.py` before it is
  sent. An AST/allowlist test pins the reachable set.
- The feed connects through the Phase 12 `SourceSupervisor` (backoff, staleness,
  resync, cursors) and the bridge publishes onto the Phase 12 bus. No supervisor
  wiring, no socket, no new dependency. Bounded `getTransaction` reads honor the
  same rate limiter as subscription frames.
- The probe script (`scripts/probe_pump_accounts.py`, Phase 11) stays read-only
  (`getAccountInfo`, no send path) and is extended only to write the probe record.

### D-06 Recorder seals, never fabricates (REC-01, REC-02)

- `replay/live_recorder.py` writes `ticks.jsonl`, `gaps.jsonl` and `manifest.json`
  (sha256 of every listed file, ticks only, non-decreasing `ts_utc`). A sealed
  dataset passes `replay.fixtures.load_dataset` (manifest-gated verification runs
  before any ledger file is created). A torn last line is recovered on startup and
  recorded; gaps are written to `gaps.jsonl`. No back-fill, no interpolation, no
  external history (V3-2/V4-13 self-recorded only).
- `replay/import_data.py` brings an external tick file into the sealed form without
  inventing timestamps; `replay/trim.py` cuts a sealed window without rewriting
  history. CLI verbs that call them are Phase 16; this phase ships the library
  functions and their tests only.
- Recorder and import never open `var/ledger.sqlite`. Dataset directories live under
  the state dir; a dataset name is a plain name validated the same way as
  `FixtureManifest.dataset`.

### D-07 Fee v2 selectable, v1 default (FEE-01, first half)

- `execution/fees.py` gains the v2 model: venue 100 bps plus the PumpPortal fee
  when that builder is used, ATA rent on the first buy of a mint, and the signer
  priority-fee cap. v2 is selected by `paper_fees.model = "v2"`; the default stays
  `"v1"` and every existing v1 number is unchanged. No float arithmetic; all
  integer lamports with flooring.
- `execution/paper_factory.py` is the only constructor path for paper adapters: it
  builds the adapter with the configured `FeeModel` and never imports
  `pumpgrok.execution.live.*` (the import-graph guard in
  `tests/safety/test_import_graph_no_live.py` must cover it).
- `execution/entry_hook.py` enforces the entry gate on `exec.place`: the
  `rpc_curve_price_allowed` allowlist, the graduation check, and the strategy fee
  model. Exit/flatten sells are never blocked by entry-only conditions (V4-12).
  `tests/characterization/execution` must pass with v1 still the default.
- `PaperFeesSettings.model` widens from `Literal["v1"]` to `Literal["v1", "v2"]`.
  The settings surface characterization (PRE_V4 pin) is untouched because v4
  sections are not pinned; tests that assert `model == "v1"` by default keep passing.

### D-08 Hash, contract and live discipline (PRC-01, PRC-03, PRC-06 names)

- smoke-10m `events.hash` stays
  `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` and the
  trading-smoke ledger hash stays `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54`.
  The fee v1 default is what keeps the trading hash still; Phase 13 records both
  before/after pairs in `CHANGELOG.md` (equal pairs are recorded, not skipped).
- `test "$(git diff --name-only v4-base -- contracts | wc -l)" -eq 0` must hold:
  no contract change and therefore no `contracts/changes/` document.
- `pumpgrok run --mode live --once` still exits 3 listing the nine preconditions.
- Every plan runs its named pytest files; the full `make lint`, `make typecheck`,
  `make test`, `./scripts/check.sh` plus the paper replay smoke complete in 13-07.

### Dependencies

- Phase 13 starts only after Phase 12 merges (ROADMAP Execution Order; `.planning/
  STATE.md` records Phase 12 at the ship checkpoint with owner receipt approval
  pending). Plans assume `src/pumpgrok/events/` (bus, models, sources),
  `src/pumpgrok/config/sections/v4.py` (settings skeleton, PRC-11) and
  `tests/harness/faults.py` (fault fakes) already exist.
- Phase 11 inputs assumed present: replay hash pins (11-01), the paper-adapter
  split (11-06; `execution/paper_adapter/` package), the pump event decoder
  (11-07; `tools/onchain/pump_events.py`), the read-only probe script (11-09;
  `scripts/probe_pump_accounts.py`). `scripts/probe_curve_layout.py` is
  superseded and is deleted in Phase 14, not here.
- Phase 14 needs 13-02 (live price source and marks) for the event-mode wake.
  Phase 15 needs 13-01 (datafeed settings and bridge) and 13-03 (fee v2 and entry
  hook). Phase 16 needs 13-01 (recorder). Keep those seams stable: settings field
  names, bridge event kinds, `LivePriceSource` interface, recorder dataset layout.

### Grey areas (planner discretion; resolve in plan actions, not by scope cuts)

- `DatafeedSettings`/`RecorderSettings` currently carry only `enabled` and
  `allowlist`. Plans decide which caps and paths become settings fields versus named
  constants; whichever is chosen is tested and loads off by default.
- Whether the datafeed package owns its typed errors or reuses `core/errors.py`,
  subject to the pinned surface and the import-graph guard.
- Whether `EventKind` needs a new member for gap/stale in 13-01 (extend the one
  catalog) or gaps ride `curve_tick` with a payload marker. One catalog either way.
- Whether `LivePriceSource` exposes sync or async pricing. The callers are the
  entry hook and the marks loop; the plan picks the shape that keeps those callers
  free of network calls.
- Whether the fee v2 PumpPortal builder fee is a config flag or an argument on the
  fill. The Requirement names the condition, not the surface; either is acceptable
  if the tests pin both branches.

### Ownership

- `.planning/**` is `bot-00-chief`. This context and the plans stay on
  `bot-00-chief/phase-12-verification` (the current branch; do not move branches).
- `src/pumpgrok/**`, `tests/**`, `scripts/probe_pump_accounts.py` and `docs/**`
  implementation belongs to `bot-02-risk` on `bot-02-risk/phase-13-curve-truth`
  unless a plan names otherwise. Implementation commits for those paths do not go on
  the chief branch.
- `CHANGELOG.md` is `bot-09-journal`. The hash-pair entry is a journal commit on
  `bot-09-journal/phase-13-curve-truth` (plan 13-07).
- Plan 13-05 is human-gated: the executor records `decoded_pending_review` and the
  human sets `reviewed_by`; no agent sets `reviewed_by` or flips a status to
  `VERIFIED`. Do not add a pull-request-number waiver. Do not edit `contracts/`.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- `src/pumpgrok/tools/onchain/curve_layout.py`: current 49 byte decode
  (`<8sQQQQQB`), `CurveState`, `LAYOUT_STATUS = "ASSUMED"`, `encode_curve_fixture`,
  `rpc_curve_price_allowed`. Consumers: `tools/market/{price,liquidity}.py`,
  `execution/paper_adapter/{buy,confirm_stages}.py`.
- `src/pumpgrok/tools/onchain/pump_events.py`: five-event Anchor decoder
  (`TradeEvent`, `CreateEvent`, `CompleteEvent`,
  `CompletePumpAmmMigrationEvent`, `PostCompleteBuyEvent`), `decode_event`,
  `EventDecodeError`/`UnknownEventError`. No `EVENT_DECODE_STATUS` yet.
- `src/pumpgrok/events/models.py`: one `EventKind` catalog, priority as a function
  of kind, derived event ids, frozen payloads. `src/pumpgrok/events/sources.py`:
  `SourceSupervisor` (backoff after `stable_s`, 121 s silence yields stale, resync
  seeds held mints, corrupt cursor starts clean).
- `src/pumpgrok/config/sections/v4.py`: `DatafeedSettings`, `RecorderSettings`,
  `PaperFeesSettings` (bare: `enabled=False`, empty allowlist, `model="v1"`).
  PRE_V4 surface pins are in
  `tests/config/test_settings_surface_characterization.py`; v4 classes are unpinned.
- `src/pumpgrok/execution/fees.py`: v1 `FeeModel` (venue 100 bps, base 5000,
  priority 200000 CU). Consumed via `PaperAdapter(fees=...)`; `FeeModel()` default
  is v1.
- `src/pumpgrok/replay/fixtures.py`: `load_dataset` (manifest-gated, digest-first,
  strict readers, `CorruptFixture` to exit 4). `src/pumpgrok/replay/recorder.py`
  is the LLM-outcomes recorder, not a market-data recorder; the new module is
  `replay/live_recorder.py`.
- `tests/harness/faults.py`: `FaultyEventSource`, `FaultyGrokTransport` (Phase 12).
- `tests/safety/test_import_graph_no_live.py`: AST import-closure guard over
  backtest, upgrade, supervisor, paper adapter and CLI.
- `scripts/probe_pump_accounts.py`: read-only probe (no send path), Phase 11.
  `scripts/probe_curve_layout.py`: superseded, deleted in Phase 14.
- `docs/CURVE_LAYOUT_PROBE.md`: current state `Status: ASSUMED` with the exact
  probe error (no bonding-curve account configured).

### Established Patterns

- Integer money, `Decimal` only for ratios. Frozen pydantic models,
  `extra="forbid"`. ULIDs from `core/ids.py`. All time through the injected
  `Clock`; no `datetime.now`/`time.time`/`time.sleep` outside the clock.
- Fail closed. A bad config value or unknown price source raises or returns
  `None`/`data_unavailable`, never a silent default.
- Tests follow the module they pin. New datafeed tests live under `tests/datafeed/`;
  execution tests under `tests/execution/`; replay tests under `tests/replay/`.
  The 60-line function guard (`tests/quality/test_function_size.py`) and the
  complexity ratchet apply to every new module.
- No network in `make test` by default; live-shaped tests use fakes, recorded
  fixtures, or `respx` fixtures. A live-shaped network call needs an explicit
  network-block test (`tests/test_network_block.py` pattern).

### Integration Points

- Settings composition in `config/settings.py` (v4 section field edits only).
- Bus bridge: `datafeed/bridge.py` publishes `events.Event` onto the injected bus
  publisher; no import from `events` into `supervisor` and no import from
  `datafeed` into `execution.live`.
- Price gate: `tools/onchain/curve_layout.rpc_curve_price_allowed` is called by
  the entry hook and `LivePriceSource`; no second policy.
- Recorder output is consumed by `replay/fixtures.load_dataset` and later by
  Phase 16 backtest v2.

</code_context>

<specifics>
## Specific Ideas

The operator wants paper trading to be priced only from market data the desk can
explain: a verified layout, an allowlisted feed, and a recorder that proves what it
recorded. Phase 13 makes every price source explicit and every gap visible. Nothing
here arms a live book, funds a wallet, or spends anything: the probe runs against the
public mainnet endpoint read-only, the feed runs against free PumpPortal methods and
public RPC, and the desk stays in paper mode. The human review in 13-05 is the
exercise of judgment this phase refuses to automate: only a human can flip
`ASSUMED` to `VERIFIED`, because the flip authorizes RPC-derived prices for entries.

</specifics>

<deferred>
## Deferred Ideas

- Composition-root no-send proof and `supervisor/live_paper.py` (Phase 15, MKT-09
  second half). Flipping the fee v2 default and its trading-smoke re-pin (Phase 15).
- Recorder CLI verbs `run --record`, `replay trim`, `replay import` (Phase 16,
  REC-03).
- Event-mode supervisor wake, Grok gateway, Hermes cutover (Phase 14). Strategy
  runtime, attribution, four baseline strategies (Phase 15).
- Runbooks for datafeed and recorder (Phase 19, OBS-04). The probe-script deletion
  of `scripts/probe_curve_layout.py` (Phase 14).
- Paid RPC provider, PumpPortal trade-stream key, PumpSwap sells, devnet/testnet
  execution, wallet funding: out of v4 scope unless a later milestone admits them.
- Constitution amendment application. Phase 18, human-approved PR only.

</deferred>
