# Phase 17 CONTEXT: Risk hardening and promotion lifecycle

Phase 17 is the first point where the whole paper desk runs end to end on
recorded data (ROADMAP checkpoint). Phases 11-16 supply the base: pinned
replay hashes, event runtime, feed and entry hook, gateway and wake, strategy
core with allocation, backtest evidence. This phase adds per-strategy risk
slices and kills, fail-closed entry checks and feed health, promotion stages
on recorded evidence, and the event desk composition root with restart
recovery. Paper-only invariant holds throughout: no live adapter, no keys,
no signing code, `run --mode live` exits 3.

## Goal (ROADMAP Phase 17)

The risk engine enforces per-strategy slices and strategy kills on existing
R34 rows (19 rows and the risk_json shape unchanged), entry checks and feed
health fail closed, live failure classes feed the exec-error breaker,
strategies move BACKTEST to PAPER to LIVE_ELIGIBLE and back on recorded
evidence under version-controlled thresholds with no timers and no Grok, and
the event desk composition root wires all of it, recovers from restarts, and
refuses to build unless paper.

Requirements (14): RSK-01, RSK-02, RSK-03, RSK-04, RSK-05, RSK-08, PRM-01,
PRM-02, PRM-03, PRM-04, PRM-05, PRM-06, RT-03, RT-04.

## Locked decisions

- D-01: Slices and kills land on existing R34 rows only. STEP_IDS stays at
  19 rows and the risk_json shape is unchanged (RSK-08). No new risk row
  type, no schema migration. A slice breach is capped or rejected on
  `max_token_fraction` with the reason recorded on the existing row
  (RSK-01). A kill row blocks buys but never exits, and clears only with a
  human (RSK-02). No auto-clear, no timer clear.
- D-02: Entry checks fail closed. Authority, Token-2022 extension, holder
  concentration, mint-list and BLIND cases are rejected (RSK-05). The mint
  list lives in version-controlled `config/mint_lists.toml` which must
  parse as TOML. Checks plug into the Phase 13 entry-gate hook
  (`execution/entry_hook.py`); they add no new order entry point and every
  check runs before any order reaches a signer (choke-point posture, even
  though RSK-06 itself lands in Phase 18).
- D-03: Feed staleness is lazy and idle-quiet. Staleness is evaluated on
  read, never on a timer; an idle desk with no tick is not stale (RSK-03).
  A required feed that has never ticked fails closed in live mode. Live
  failure classes feed the existing exec-error breaker, and any UNKNOWN
  outcome sets a halt (RSK-04). Breaker wiring extends
  `risk/breakers.py`; it does not create a second breaker.
- D-04: Promotion stages are ledger rows with a decision log: BACKTEST,
  PAPER, LIVE_ELIGIBLE, plus demotion back (PRM-01). LIVE is derived from
  LIVE_ELIGIBLE plus the arm record, never stored (V4-11). Thresholds live
  in version-controlled `config/promotion_thresholds.toml` and load
  fail-closed: any threshold looser than the LiveGate floors (14 days, 50
  closed trades, profit factor 1.2, drawdown 0.15) refuses to load
  (PRM-02). Promotion reuses the upgrade gate checks; there is no second
  search engine (PRM-03).
- D-05: Promotion is event-triggered only. No timers, no clocks that sleep,
  no Grok import anywhere under `src/pumpgrok/promotion/` (PRM-05). The
  evaluator subscribes to bus events through the composition root; it never
  polls. A strategy parameter-hash change resets the pair to BACKTEST
  automatically, demotion is automatic on evidence, and one operation
  (`pumpgrok promotion demote`) rolls a strategy back (PRM-04). Writer
  discipline: only `is_writer` callers write, stored content is verified
  before use (PRM-06).
- D-06: The event desk composition root is `supervisor/event_desk.py`. It
  wires bus, sources, strategy runtime, gateway, intent router and
  promotion edges, exhausts a real LayeredBudget in e2e, and refuses to
  build unless mode is paper (RT-03, PRM-05). An idle desk stays silent:
  zero Grok calls, zero ledger writes beyond health. Entry-gate wiring
  lands in `supervisor/live_paper.py` reusing the Phase 15 paper root.
- D-07: Restart recovery (`supervisor/recovery.py`) re-arms exit deadlines
  and restores strategy tapes, peaks, probation and the watch set from the
  ledger (RT-04, completing the Phase 15 library half). No second sniper
  BUY on resume (HARD-07 posture). Recovery is idempotent: a crash during
  recovery resumes clean.
- D-08: Every new behaviour is config-gated off by default. With flags off
  the replay hashes are byte-identical to Phase 16: smoke-10m stays
  `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` and
  the trading-smoke pin is unchanged. No contract surface changes:
  `git diff --name-only v4-base -- contracts` is empty at phase close
  (PRM-01). Live stays refused with exit 3 (LIV-07).
- D-09: The CHANGELOG Phase 17 entry is written only by the last plan
  (17-07), with both before/after hash pairs. Earlier plans touch no
  CHANGELOG lines and run no `pumpgrok verify` for the pair.

## Discarded alternatives

- A new risk row type or risk_json shape change: discarded. RSK-08 pins
  the 19 rows and the shape; a new row would break the Phase 11 pin and
  every hash that folds risk output.
- A promotion timer or cron: discarded. PRM-05 forbids it; a timer is a
  second scheduler and would wake strategies on cadence the desk just
  removed.
- A second search engine for promotion: discarded. PRM-03 requires reuse
  of the upgrade gate checks; BT-07 already removed the grid search.
- A live-capable composition root: discarded. The root refuses to build
  unless paper; the dormant live path is Phase 18.

## Grey areas with defaults

- G-01: Slice enforcement caps first, rejects when the cap cannot be
  honoured, because a silent fill above the slice would defeat the slice.
- G-02: Kill clearing requires a human CLI action with an approval record,
  because R22 makes halts human-clear only and a kill is a halt of one
  strategy.
- G-03: A never-ticked required feed in paper mode is degraded, not
  failed-closed, because paper has no live rows to protect and the Phase 13
  LivePriceSource already fails closed at the data plane.
- G-04: UNKNOWN always halts, including a single UNKNOWN, because E2 makes
  a failed send halt like UNKNOWN and a retry would double-send.

## Scope boundary

In scope: `risk/strategy_slice.py`, `risk/entry_checks.py`,
`risk/feed_health.py`, breaker extensions, engine reason mapping,
`config/mint_lists.toml`, `src/pumpgrok/promotion/`,
`config/promotion_thresholds.toml`, the `upgrade/gate.py` paper parameter,
the `promotion demote` verb, `supervisor/event_desk.py`, entry-gate wiring
in `supervisor/live_paper.py`, `supervisor/recovery.py`, their tests, and
the Phase 17 CHANGELOG entry.

Out of scope: the dormant live path, signer service, arm records and
amendment application (Phase 18, PRC-07); observability docs, alert rules
and the milestone audit (Phase 19); any change to STEP_IDS, risk_json, or
`contracts/`; any live adapter, key, or signing symbol; flipping
`wake_mode` default (OD-20, deferred beyond v4); executing gates, lint,
tests, or commits (orchestrator and executor own that).
