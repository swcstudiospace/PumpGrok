# Phase 13 CONTEXT: Curve truth, live market data and recorder

Milestone v4, Phase 13. Goal per ROADMAP: the bonding-curve account layout is corrected to the official token-first order and probed read-only against live accounts; a bounded, rate-limited, READ-ONLY live feed (PumpPortal create and migration frames plus logsSubscribe trade events) produces integer ticks, a LivePriceSource that fails closed, marks for held mints, and a recorder that seals self-verifying datasets with gaps recorded; datafeed events are bridged onto the Phase 12 bus. Also here (sniper): paper fee model v2 as a selectable option, a paper adapter factory, and the entry-check hook against a Protocol.

Depends on: Phase 12 (settings skeleton 12-01, catalog 12-02, SourceSupervisor 12-03) and Phase 11 pulls (decoder 11-07, probe script 11-09, adapter split 11-06). Reuses without re-implementing: core RateLimiter, core/atomic_write.py, replay/fixtures.py load_dataset and FixtureManifest, tools/social/client.py, tools/onchain/authorities.py, execution/curve_math.py.

## Locked decisions (NON-NEGOTIABLE)

- D-01: Money integer lamports; Decimal only for ratios.
- D-02: Clock-only time and no direct sleep.
- D-03: Live stays refused (exit 3); nothing in the feed can send, sign or simulate.
- D-04: hashes are identity only; dataset digests identify, never score.
- D-05: mypy --strict, ruff, no dead code, no swallowed errors, no placeholders, ASCII-only docs.
- D-06: Layout fix: keep struct `<8sQQQQQB` but unpack as (disc, vtok, vsol, rtok, rsol, supply, complete) (token first); accept len >= 49; require discriminator 17b7f83760d8ac60; parse extended fields as optional (creator at offset 49, mayhem at 81, quote_mint at 83; None for short legacy accounts). `CURVE_ACCOUNT_SIZE` keeps its NAME and value 49 (three other seats' tests import it) and `CURVE_ACCOUNT_SIZE_V2 = 166` is added; `encode_curve_fixture` keeps its keyword signature and 49-byte output. Reason: no foreign import changes.
- D-07: `rpc_curve_price_allowed` becomes an allowlist: fixture, rest, pumpportal always allowed; source "rpc" or log-derived prices need the status VERIFIED; unknown names refused (today it is fail-open for new names).
- D-08: LAYOUT_STATUS and EVENT_DECODE_STATUS stay ASSUMED until a human sets `reviewed_by: human:NAME` (OD-04). Plan 13-05 flips both only then; if the owner declines or the probe fails the flip commit is dropped, the phase closes ASSUMED with the exact probe error, live-fed paper buys fail closed and the event desk runs recorded datasets only. No agent writes VERIFIED. The 13-05 receipt is committed WITHOUT approved_by.
- D-09: Order that removes the rug to risk to rug cycle: status-agnostic tests first (13-02 probe artifacts and tests, 13-03 sniper tests), then the layout rewrite (13-04), then the human flips (13-05).
- D-10: ReadOnlyRpc allowlist: getAccountInfo, getMultipleAccounts, getSignaturesForAddress, getTransaction, getSlot, getHealth, getTokenSupply, getRecentPrioritizationFees, logsSubscribe, logsUnsubscribe. PumpPortal: subscribeNewToken, subscribeMigration, unsubscribeNewToken. Anything else raises ReadOnlyViolation (core/errors.py). One PumpPortal connection; paid trade streams are never subscribed; an AST test forbids signing libraries and sendTransaction, simulateTransaction, signTransaction, requestAirdrop outside the allowlist file.
- D-11: WatchSet: watch_max default 128 (ceiling 256; OD-05 without a paid provider: 32 and logsSubscribe only for held mints), probation 180 s, promotion to long watch needs ub >= 3 or rS >= 2 SOL, evict on completion, 900 s without trades or age over 7200 s, held mints pinned, subscribe limiter 30 per 10 s, overflow drops newest and is counted in the recorder manifest.
- D-12: LivePriceSource returns a price only if the feed is connected, the subscription acknowledged and no resync pending (reads SourceStateBook, no private staleness clock); else None. COMPLETE refuses entries; last_open_reserves None holds the exit; after migration_gap_timeout_s 600 the position is marked 0 with a JournalNote graduation_stuck. Marks: every held mint within 60 s (mtm_refresh_s 45) and NO timer while flat.
- D-13: Recorder: events.jsonl holds only `kind: tick` rows with ts_utc non-decreasing (load_dataset rejects regression, replay/fixtures.py:183); resynced events keep receipt time in ts and original time in `bt`; manifest `sources` is dict[str, str] (integer counts and digests written as strings) and EVERY jsonl is listed; a recorded dataset must load back through load_dataset in the same test; torn last line recovered; seal via atomic write and rename.
- D-14: REST fallback (frontend-api.pump.fun) may be blocked: it degrades to SourceStatus(blind) and refuses buys, never assuming availability. datafeed/* only decodes frames and runs transports; reconnect, staleness, resync and cursor logic are 12-03's.
- D-15: FEE1: `FeeModel` gains `version` and `FeeModel.for_version`; v1 is byte-identical to today and the default, so no hash moves here. v2 = venue 100 bps plus PumpPortal 50 bps when the builder is PumpPortal, ATA rent 2_039_280 lamports on the first buy of a mint, signer priority-fee cap; constants are REVIEW (OD-09) and listed in the receipt unverified.
- D-16: PF1: `build_paper_adapter` lives in its own module and never imports execution/live; `build_adapter` keeps its signature and delegates for paper and replay. C-03s: `EntryRefresh.refresh(mint)` Protocol in execution/entry_hook.py, gated by risk.entry.enabled (default false); risk implements EntryGate in 17-02.

## Grey-area defaults

- G-01: Tick compaction keeps first tick per mint, last tick per mint per tick_min_interval_s 1, every completion and every held-mint mark. Reason: bound dataset size.
- G-02: Recorder rotate_s 3600, seal on FeedGap over 120 s or size cap; trades.jsonl optional and off. Reason: Design B section 3.
- G-03: Progress is approximated by rS / 85 SOL; `complete` and real_token == 0 are authoritative (tick S is virtual, starts at 30 SOL).

## Phase boundary

In scope: tools/onchain/{curve_layout,pump_events}.py, docs/CURVE_LAYOUT_PROBE.md and probe artifacts, src/pumpgrok/datafeed/, replay/{live_recorder,import_data,trim}.py, core/errors.py additions, execution/{fees,paper_factory,entry_hook}.py, tests/conftest.py websocket patch (plan 13-02 only). Out of scope: strategies, risk entry-check implementation, composition root, running the mainnet probe, paid RPC procurement.

## Canonical references

src/pumpgrok/tools/onchain/curve_layout.py, replay/fixtures.py, execution/{fees,__init__}.py and paper_adapter/{buy,confirm,adapter}.py (rpc_curve_price_allowed at buy.py:250 and confirm.py:127), tests/execution/{test_graduation_blind,test_curve_source_gate}.py, tests/conftest.py, scripts/probe_pump_accounts.py (11-09), research/B-strategies-backtest-data.md sections 1 to 3, research/owner-decisions.md OD-04, OD-05, OD-09.

## Existing code insights

- Today the layout unpacks (disc, vsol, vtok, rsol, rtok, supply, complete), requires len == 49 and never checks the discriminator; encode_curve_fixture writes the same swapped order, so existing curve tests pass against a wrong layout.
- CurveSnapshot S and T are VIRTUAL reserves; a decoded TradeEvent is a full integer tick with no account read.
- ExitRules is typed on FixtureCurveSource but uses only curve, reserves, last_open_reserves; a live source with those three methods fails closed in the migration gap.
- Program discriminators: TradeEvent bddb7fd34ee661ee, CreateEvent 1b72a94ddeeb6376, CompleteEvent 5f72619cd42e9808, CompletePumpAmmMigrationEvent bde95db95c94ea94; decode only when the top invoke frame is the pump program 6EF8rrec...; truncation raises typed EventDecodeError.

## Specifics

- Datafeed events carry ts from the Clock plus integer aggregates nb, ns, bv, sv, ub (None unless observed), cs, topb_ppm, mm; bridge mapping is the tested constant from 12-02.
- Hash rule this phase: both pairs EQUAL; FEE1 defaults v1; B05e/B05 touch only status constants.
- tests/execution under both statuses: tests are status-agnostic and must pass before and after 13-04.

## Deferred ideas

PumpSwap pool pricing beyond the pooled-vault approximation; trades.jsonl by default; direct pump instruction building; REST polling for idle mints.

## Ownership, receipt and hash rules (every plan of this phase)

- Branch `bot-0N-seat/v4-pPHASE-slug`, one PR per (phase, seat) (PR table below). Receipt `.receipts/bot-0N-seat/v4-pPHASE-slug.json` (task_id = slug, branch = the branch), tracked through the glob `!.receipts/bot-0*/v4-p*.json` from plan 11-01; no other seat edits .gitignore.
- `approved_by` is NEVER self-written and a seat never approves its own work. An agent reviewer (chief for risk-authored work, risk for other seats) reads the diff; human-gated receipts are committed WITHOUT approved_by and the owner adds `human:SomeRandmGuyy` in a batch at the ship checkpoint (after phases 12, 14, 17, 19).
- Seat purity: every path resolves to the plan seat via `resolve_owner(path, load_manifest(DEFAULT_MANIFEST))`; tests/** is risk except tests/desk/** (chief) and tests/engine/** (signal); execution/** sniper; cli/** risk; supervisor/** chief. A foreign-test failure gets a one-file companion plan by the owning seat, merged first.
- Replay hashes: smoke-10m `events.hash` is `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` (seq=2 events=41, verdict and rollover rows only). Trading `smoke` (5 events, seq 11) gave `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54` at HEAD 641927c; plan 11-01 pins it at v4-base; it moves only in plan 15-01. Run receipts in a fresh worktree without var/ledger.sqlite.
- Live stays refused: `uv run pumpgrok run --mode live --once; test $? -eq 3`; nothing arms it.
- Acceptance lines are real commands; exit 0 means success. The G-2 bypass family (collect-only, `--co`, `|| true`, stderr to /dev/null, `--force`, `--dry-run`, inline PUMPGROK_LIVE_ENABLE) never appears; `! cmd -rs | grep -q SKIPPED` proves no skips. Plans touching src also run make lint and make typecheck.


## Plans (7 planned; research/plans.json is the source)

Pull requests in merge order (numbers from research/pr-plan.md):

| PR | Branch | Plans | Approver | Checkpoint |
|----|--------|-------|----------|------------|
| PR-12 | `bot-02-risk/v4-p13-datafeed-recorder-probe` | 13-01, 13-02 | bot-00-chief (agent) | CP14 |
| PR-13 | `bot-04-sniper/v4-p13-fees-paper-factory-hooks` | 13-03 | bot-02-risk (agent) | CP14 |
| PR-14 | `bot-05-rug/v4-p13-curve-layout-status-flips` | 13-04, 13-05 | human:SomeRandmGuyy (batch); agent review first | CP14 |
| PR-15 | `bot-09-journal/v4-p13-changelog` | 13-06 | bot-02-risk (agent) | CP14 |
| PR-16 | `bot-00-chief/v4-p13-close` | 13-07 | bot-02-risk (agent) | CP14 |

### 13-01: datafeed core, bridge onto the event catalog, live recorder and importer

- seat bot-02-risk; wave 1; PR-12; depends_on: 12-01, 12-02; requirements: MKT-05, MKT-09, REC-01, REC-02; owner decisions: OD-05.
- files: src/pumpgrok/datafeed/__init__.py, src/pumpgrok/datafeed/events.py, src/pumpgrok/datafeed/mintbook.py, src/pumpgrok/datafeed/watchset.py, src/pumpgrok/datafeed/readonly.py, src/pumpgrok/core/errors.py, tests/datafeed/test_watchset.py, tests/datafeed/test_readonly.py, tests/datafeed/test_mintbook.py, src/pumpgrok/datafeed/bridge.py, tests/datafeed/test_bridge.py, src/pumpgrok/replay/live_recorder.py, src/pumpgrok/replay/import_data.py, src/pumpgrok/replay/trim.py, tests/replay/test_live_recorder.py, tests/replay/test_live_recorder_manifest_strings.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/datafeed/test_watchset.py tests/datafeed/test_readonly.py tests/datafeed/test_mintbook.py tests/config
uv run pytest -q tests/events tests/datafeed/test_bridge.py
uv run pytest -q tests/replay tests/config
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 13-02: Portal and logs sources on SourceSupervisor, LivePriceSource and marks, probe artifacts and status-agnostic tests

- seat bot-02-risk; wave 2; PR-12; depends_on: 11-07, 11-09, 12-02, 12-03, 13-01; requirements: MKT-06, MKT-07, MKT-08, MKT-03; owner decisions: OD-04, OD-05.
- files: src/pumpgrok/datafeed/portal.py, src/pumpgrok/datafeed/logs.py, src/pumpgrok/datafeed/resync.py, src/pumpgrok/datafeed/fallback.py, tests/datafeed/test_feed.py, tests/conftest.py, src/pumpgrok/datafeed/price.py, src/pumpgrok/datafeed/graduation.py, src/pumpgrok/datafeed/marks.py, tests/datafeed/test_price_source.py, tests/datafeed/test_graduation.py, tests/datafeed/test_marks.py, tests/fixtures/rpc/**, docs/CURVE_LAYOUT_PROBE.md, tests/docs/test_verify_doc_commands_offline.py, tests/cli/test_review_trade_prices.py, tests/safety/test_blind_advisory.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/datafeed/test_feed.py tests/test_network_block.py
uv run pytest -q tests/datafeed/test_price_source.py tests/datafeed/test_graduation.py tests/datafeed/test_marks.py
uv run pytest -q tests/docs tests/safety tests/cli
grep -q 'decoded_pending_review' docs/CURVE_LAYOUT_PROBE.md
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 13-03: Status-agnostic execution tests, paper fee model v2 (selectable), paper factory, entry hook Protocol

- seat bot-04-sniper; wave 1; PR-13; depends_on: 11-01, 11-06; requirements: MKT-04, FEE-01, MKT-09, LIV-06, RSK-05; owner decisions: OD-09.
- files: tests/execution/test_graduation_blind.py, tests/execution/test_curve_source_gate.py, src/pumpgrok/execution/fees.py, tests/execution/test_fee_model_v2.py, src/pumpgrok/execution/paper_factory.py, src/pumpgrok/execution/__init__.py, tests/execution/test_paper_factory.py, src/pumpgrok/execution/paper_adapter/adapter.py, tests/execution/test_entry_gate_hook.py, src/pumpgrok/execution/entry_hook.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/execution
uv run pytest -q tests/execution/test_fee_model_v2.py tests/execution
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pytest -q tests/execution/test_paper_factory.py tests/safety/test_import_graph_no_live.py
uv run pytest -q tests/execution tests/characterization/execution
make lint
make typecheck
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 13-04: Curve layout fix and allowlist price gate (status stays ASSUMED)

- seat bot-05-rug; wave 3; PR-14; depends_on: 11-01, 13-02, 13-03; requirements: MKT-01, MKT-04.
- files: src/pumpgrok/tools/onchain/curve_layout.py, tests/tools/onchain/test_curve_layout.py, tests/tools/onchain/test_price_gate.py, tests/tools/onchain/test_onchain_reads.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/tools tests/execution tests/safety
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 13-05: Human-reviewed status flips: LAYOUT_STATUS and EVENT_DECODE_STATUS

- seat bot-05-rug; wave 4; PR-14; depends_on: 11-01, 11-07, 13-02, 13-03, 13-04; requirements: MKT-03, MKT-10, MKT-02; HUMAN-GATED; owner decisions: OD-04.
- files: src/pumpgrok/tools/onchain/curve_layout.py, tests/tools/onchain/test_probe_record.py, src/pumpgrok/tools/onchain/pump_events.py, tests/tools/onchain/test_event_decode_status.py.
- acceptance (run from the repo root, each exits 0):

```sh
uv run pytest -q tests/tools/onchain/test_probe_record.py tests/execution tests/safety tests/docs
uv run pytest -q tests/tools/onchain/test_event_decode_status.py tests/tools/onchain/test_pump_events.py tests/datafeed/test_price_source.py
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
make lint
make typecheck
uv run pytest -q tests/replay/test_trading_smoke_pin.py
uv run pumpgrok run --mode live --once; test $? -eq 3
python3 ci/gates/check_ownership.py --validate-manifest
```

### 13-06: CHANGELOG entry for Phase 13 with both hash pairs

- seat bot-09-journal; wave 5; PR-15; depends_on: 13-01, 13-02, 13-03, 13-04, 13-05; order_after 12-04; requirements: PRC-03, PRC-06.
- files: CHANGELOG.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -qF 'Phase 13: smoke-10m events.hash before: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
grep -qF 'Phase 13: smoke-10m events.hash after: b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d' CHANGELOG.md
p=$(python3 -c "import json;print(json.load(open('tests/fixtures/replay/pins/trading_smoke.json'))['events_hash'])") && grep -qF "Phase 13: trading-smoke events.hash before: $p" CHANGELOG.md && grep -qF "Phase 13: trading-smoke events.hash after: $p" CHANGELOG.md
uv run pumpgrok verify --fixture smoke-10m | grep -q b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d
python3 ci/gates/check_ownership.py --validate-manifest
```

### 13-07: Phase 13 close: STATE, verification record, progress table

- seat bot-00-chief; wave 6; PR-16; depends_on: 13-01, 13-02, 13-03, 13-04, 13-05, 13-06; order_after 12-05; requirements: PRC-06.
- files: .planning/STATE.md, .planning/ROADMAP.md, .planning/phases/13-curve-truth-live-market-data-recorder/13-VERIFICATION.md.
- acceptance (run from the repo root, each exits 0):

```sh
grep -q 'Phase 13' .planning/STATE.md
./scripts/check.sh
test -f .planning/phases/13-curve-truth-live-market-data-recorder/13-VERIFICATION.md
python3 ci/gates/check_ownership.py --validate-manifest
```
