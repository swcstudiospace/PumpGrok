---
phase: 13-curve-truth
verified: 2026-11-22
status: passed
score: 7/7 plans summarized
---

# Phase 13: Curve truth, live market data and recorder Verification Report

**Phase Goal:** The curve account layout is corrected to the official token-first order and probed read-only against live accounts; the paper fee model v2 is selectable and the paper adapter has a paper factory and an entry-gate hook; a bounded, rate-limited, read-only live feed produces integer ticks, a LivePriceSource that fails closed, marks for held mints, and a recorder that seals self-verifying datasets with gaps recorded; the datafeed events are bridged onto the Phase 12 bus. `LAYOUT_STATUS` and `EVENT_DECODE_STATUS` become `VERIFIED` only after a human review.

**Verified:** 2026-11-22
**Status:** passed
**Score:** 7/7 plans summarized

## Per-plan evidence

All seven plans are on main via merged PR #134 (merge `d3d7d5f`). CI evidence on main is recorded in `.planning/milestones/v4-MILESTONE-AUDIT.md`: CI, Quality Gates, and Security PR Gate all success. This record maps each SUMMARY claim to evidence paths on main; it cites already-recorded evidence and adds no new test output.

| Plan | SUMMARY claim | Evidence on main | Merged via |
|------|----------------|------------------|------------|
| 13-01 Datafeed foundation + recorder | `DatafeedSettings`/`RecorderSettings` bounded defaults off by default; integer-only `CurveTick`/`GapEvent`, bounded `WatchSet` with pinned held mints and overflow counter, `MintBook`, `bridge.py` onto one `EventKind` catalog with one `gap` kind; recorder seals datasets passing `load_dataset`, torn last line truncated, `import_data.py` preserves timestamps, `trim.py` cuts sealed windows | `src/pumpgrok/datafeed/`, `src/pumpgrok/config/sections/v4.py`, `src/pumpgrok/events/models.py`, `src/pumpgrok/replay/live_recorder.py`, `src/pumpgrok/replay/import_data.py`, `src/pumpgrok/replay/trim.py`; tests under `tests/datafeed/test_watchset.py`, `tests/datafeed/test_mintbook.py`, `tests/datafeed/test_bridge.py`, `tests/events/test_models_v4_kinds.py`, `tests/replay/test_live_recorder.py`, `tests/replay/test_live_recorder_manifest_strings.py` | PR #134 (`d3d7d5f`) |
| 13-02 LivePriceSource + graduation + marks | Fail-closed `LivePriceSource` (`None` when disconnected or unverified, completed curve refuses entry, gap holds last good, timeout marks zero); entry-only graduation refusal; `MarksLoop` marks every held mint within 60s on injected Clock, empty book inert, no wall time under `datafeed/` | `src/pumpgrok/datafeed/price.py`, `src/pumpgrok/datafeed/graduation.py`, `src/pumpgrok/datafeed/marks.py`; tests under `tests/datafeed/test_price_source.py`, `tests/datafeed/test_graduation.py`, `tests/datafeed/test_marks.py` | PR #134 (`d3d7d5f`) |
| 13-03 Fee v2, factory, entry hook | `FeeModelV2` beside v1 (builder fee, ATA rent first-buy, capped priority fee, integer floored), default v1; paper factory as only constructor path, entry hook enforces buys-only allowlist plus graduation gate, sells pass | `src/pumpgrok/execution/fees.py`, `src/pumpgrok/execution/paper_factory.py`, `src/pumpgrok/execution/entry_hook.py`, `src/pumpgrok/config/sections/v4.py`; tests under `tests/execution/test_fee_model_v2.py`, `tests/execution/test_paper_factory.py`, `tests/execution/test_entry_gate_hook.py`, `tests/safety/test_import_graph_no_live.py`, `tests/characterization/execution` | PR #134 (`d3d7d5f`) |
| 13-04 Token-first decode + price gate | 49- and 166-byte token-first decode, bad discriminator/length rejected, `CurveState.token_mint` added, `encode_curve_fixture` builds both sizes; `EVENT_DECODE_STATUS = "ASSUMED"` with helper; `rpc_curve_price_allowed` allowlist (replay/fixture/rest/pumpportal allowed, rpc refused while ASSUMED, unknown refused) | `src/pumpgrok/tools/onchain/curve_layout.py`, `src/pumpgrok/tools/onchain/pump_events.py`; tests under `tests/tools/onchain/test_curve_layout.py`, `tests/tools/onchain/test_pump_events.py`, `tests/tools/onchain/test_price_gate.py`, `tests/tools/onchain/test_event_decode_status.py`, `tests/tools/onchain/test_probe_record.py`, `tests/execution`, `tests/cli/test_review_trade_prices.py`, `tests/safety/test_blind_advisory.py` | PR #134 (`d3d7d5f`) |
| 13-05 Probe record (human-gated) | Probe writer (`format_record_markdown`/`write_record_doc`, `--record-doc`), never writes VERIFIED, discriminator checked before decode; `docs/CURVE_LAYOUT_PROBE.md` states `Status: ASSUMED` with exact probe error and `decoded_pending_review` contract | `scripts/probe_pump_accounts.py`, `docs/CURVE_LAYOUT_PROBE.md`; tests under `tests/tools/onchain/test_probe_record.py`, `tests/desk/test_probe_pump_accounts.py`, `tests/docs` | PR #134 (`d3d7d5f`) |
| 13-06 PumpPortal/logs feed, resync, readonly | Free PumpPortal methods only, shared 30/10s `RateLimiter`, TIMEOUT reconnect with gap events and signature dedup; `logsSubscribe` trades with bounded `getTransaction` follow-ups; resync seeds held mints; five-method readonly allowlist enforced before outbound calls; stale fallback with no transport | `src/pumpgrok/datafeed/portal.py`, `src/pumpgrok/datafeed/logs.py`, `src/pumpgrok/datafeed/resync.py`, `src/pumpgrok/datafeed/readonly.py`, `src/pumpgrok/datafeed/fallback.py`, `tests/datafeed/fake_feed.py`; tests under `tests/datafeed/test_feed.py`, `tests/datafeed/test_readonly.py`, `tests/datafeed/test_resync.py`, `tests/test_network_block.py` | PR #134 (`d3d7d5f`) |
| 13-07 Phase gates + CHANGELOG pairs | Gate evidence recorded in SUMMARY; Phase 13 CHANGELOG entry with both before/after pairs, probe outcome ASSUMED, fee default v1 | `CHANGELOG.md` (Phase 13 entry); gate evidence in `13-07-SUMMARY.md` and audit final gate proof | PR #134 (`d3d7d5f`) |

## ROADMAP success criteria verdict

Phase 13 has 16 ROADMAP success criteria (see `.planning/ROADMAP.md`, Phase 13 section). Verdicts below cite already-recorded evidence only.

| # | Criterion (short form) | Verdict |
|---|------------------------|---------|
| 1 | `make lint`, `make typecheck`, `make test`, `./scripts/check.sh` exit 0 and paper replay smoke exit 0 (PRC-01) | Satisfied per recorded gate evidence in `13-07-SUMMARY.md` and audit final gate proof at `ca6cff7` / `d3d7d5f` (see Gates table) |
| 2 | 49 and 166 byte decode, bad discriminator rejected, five event types round-trip, unverified sources refused (MKT-01, MKT-02, MKT-04) | Satisfied per `13-04-SUMMARY.md` evidence for `test_curve_layout.py`, `test_pump_events.py`, `test_price_gate.py` |
| 3 | Probe tests pass; `decoded_pending_review` present; VERIFIED only with human reviewer, otherwise ASSUMED with exact probe error (MKT-03) | Satisfied as ASSUMED per `13-05-SUMMARY.md`; human-review caveat applies (see Assumptions) |
| 4 | `EVENT_DECODE_STATUS` flip needs human-set `reviewed_by`, default ASSUMED (MKT-10) | Satisfied as ASSUMED per `13-04-SUMMARY.md`; human-review caveat applies (see Assumptions) |
| 5 | Execution tests status-agnostic under recorded status (MKT-04) | Satisfied per `13-04-SUMMARY.md` evidence for `tests/execution`, `test_review_trade_prices.py`, `test_blind_advisory.py` |
| 6 | Fee v2 selectable, v1 default, factory never imports live, characterization passes (FEE-01) | Satisfied per `13-03-SUMMARY.md` |
| 7 | Watch set never exceeds cap, pins held mints, counts overflow, events map onto bus kinds (MKT-05) | Satisfied per `13-01-SUMMARY.md` |
| 8 | TIMEOUT reconnect yields no duplicate signature, emits gap events, honors 30 per 10s limiter (MKT-06) | Satisfied per `13-06-SUMMARY.md` |
| 9 | Price None when disconnected, completed curve refuses entry, gap holds, timeout marks zero (MKT-07) | Satisfied per `13-02-SUMMARY.md` |
| 10 | Every held mint marked within 60s on fake Clock, no timer while flat (MKT-08) | Satisfied per `13-02-SUMMARY.md` |
| 11 | Sealed dataset passes `load_dataset`, ticks only, non-decreasing timestamps (REC-01) | Satisfied per `13-01-SUMMARY.md` |
| 12 | Gaps written to `gaps.jsonl`, torn last line recovered on startup (REC-02) | Satisfied per `13-01-SUMMARY.md` |
| 13 | Only allowlisted RPC and PumpPortal methods reachable (MKT-09, first half) | Satisfied per `13-06-SUMMARY.md`; composition-root completion is Phase 15 scope |
| 14 | `contracts/` diff empty against `v4-base` (MKT-05) | Satisfied per `13-07-SUMMARY.md` evidence (0 files) |
| 15 | smoke-10m events.hash `b69c2959…` before == after, trading-smoke `bdcbe2d3…` before == after, pins pass, CHANGELOG pairs present (PRC-03) | Satisfied per `13-07-SUMMARY.md` and audit final gate proof; both hashes equal |
| 16 | `run --mode live` exits 3 (LIV-07) | Satisfied per `13-07-SUMMARY.md` and audit live-still-refused proof |

## Gates table

Evidence is cited from records already in the repo. No new gate runs are claimed here.

| Gate | Evidence already recorded | Source |
|------|---------------------------|--------|
| `make lint` | exit 0 | `13-07-SUMMARY.md`; audit final gate proof (`ca6cff7`) |
| `make typecheck` | exit 0 (no issues in 251 source files) | `13-07-SUMMARY.md` |
| `./scripts/check.sh` | exit 0 (35 skills, 10 agents, 513 docs healthy) | `13-07-SUMMARY.md` |
| Paper replay smoke | exit 0 | `13-07-SUMMARY.md`; audit final gate proof |
| Pin tests (`test_replay_hash_pin.py`, `test_trading_smoke_pin.py`) | exit 0 | `13-07-SUMMARY.md`; audit final gate proof |
| Contracts diff vs `v4-base` | 0 files | `13-07-SUMMARY.md` |
| Live refusal | exit 3 | `13-07-SUMMARY.md`; audit live-still-refused proof |
| Full `make test` | Full runs were green at merge: CI, Quality Gates, and Security PR Gate all success on main post-#134 at `d3d7d5f`; final gate proof at `ca6cff7` records `make test` exit 0 with 90.05% coverage | `.planning/milestones/v4-MILESTONE-AUDIT.md` |
| CI on main (PR #134) | CI success, Quality Gates success, Security PR Gate success at `d3d7d5f` | `.planning/milestones/v4-MILESTONE-AUDIT.md` (CI evidence section) |

Note on `13-07-SUMMARY.md`: that SUMMARY recorded that the full `make test` run exceeded its 300s harness window and that a coverage-excluded subset passed, with a longer full run still owed. That full-run debt is closed by the milestone audit records above (CI green post-#134 and final gate proof at `ca6cff7`), which are the merge-time gates cited here.

## Assumptions (unverified human review)

The following are recorded as assumptions, not as passes:

- `LAYOUT_STATUS` and `EVENT_DECODE_STATUS` remain `ASSUMED`. No `reviewed_by` is set, no literal was flipped to `VERIFIED`, and the `checkpoint:human-verify` in 13-05 is deferred. The MKT-03/MKT-10 ROADMAP caveat is in force: VERIFIED requires a human reviewer.
- While ASSUMED, `rpc_curve_price_allowed` refuses `curve_source == "rpc"` with `data_unavailable`. RPC-derived prices do not authorize paper entries until a human review lands.
- MKT-09 second half (composition-root test) is Phase 15 scope; only the read-only allowlist first half is claimed here.
- Fee model v2 default flip and its trading-smoke re-pin are Phase 15 scope; the v1 default is what keeps the trading hash stable in this phase.
- Recorder CLI verbs (`run --record`, `replay trim`, `replay import`) are Phase 16 scope; this phase ships library functions and tests only.
- The Phase 13 PRC-03 hash pair is recorded as equal before/after pairs (smoke-10m `b69c2959…`, trading-smoke `bdcbe2d3…`).

## Conclusion

Phase 13's 7 plans are summarized, the deliverables are on main via PR #134 with CI green, and the ROADMAP criteria are satisfied except for the explicitly deferred human review, which is honestly recorded as ASSUMED rather than fabricated as VERIFIED.
