# Live Readiness Record (Deferred)

status: deferred

The desk stays paper-only in this release. This record claims no
measured readiness: no live evaluation window has been run, no custody
arrangement exists, no venue adapter is registered, and no legal review
has been completed. Any future live decision must satisfy all four
requirement groups below and meet all nine preconditions of the live
gate. Until then the desk runs in paper mode only.

This file is prose only. It adds no signing code, no custody code, no
venue client, and no adapter registration. Live trading stays refused
end to end.

## 1. Custody model

Owner: human
Status: deferred

A future live decision requires a custody model that satisfies the
constitution clause 1 and RISK_POLICY section 6:

- Only a dedicated throwaway wallet funded with at most 200 USDC plus
  SOL for fees is ever connected. The balance is treated as already lost.
- The human connects the wallet by screen hand-off only. The desk never
  requests, accepts, stores, prints, or reasons about seed phrases,
  private keys, or recovery phrases.
- The desk sees only the public address in live.wallet_allowlist. No key
  material enters settings, environment files, logs, receipts, or ledger
  payloads.

Current state: no wallet is allowlisted, live.wallet_allowlist is not a
setting in this release, and there is nothing to custody in paper mode.
The custody group is deferred to a human decision with its own change
document and audit.

## 2. Venue

Owner: human
Status: deferred

A future live decision requires a named venue and a registered live
adapter built for it. Current state:

- build_adapter returns a PaperAdapter only. No live adapter is
  registered or enabled.
- The LiveAdapterStub is a refusing stub: place and cancel append
  LiveWriteAttempted and raise LiveGateError. No code path builds,
  signs, or sends a transaction.
- Precondition 8 adapter_registered is structurally unmet in this
  release with reason "no live adapter implementation ships in this
  release".
- No venue client is imported and no socket is opened on the live path.
  Modules under src/pumpgrok/execution/live import no venue client.

Registering a live adapter is a separate, later decision with its own
change document, a human-approved risk receipt, and a re-run of the full
paper window. Nothing in the current roadmap schedules it. The venue
group is deferred.

## 3. Legal review

Owner: human
Status: deferred

A future live decision requires a completed legal review covering at
least the manipulation boundary of RISK_POLICY section 4:

- Prohibited in paper or live mode on any venue or social platform:
  coordinated buying, wash trading, volume generation, shilling, social
  posting, spoofing, layering, front-running of desk-adjacent flow, and
  insider or bundle participation.
- The SHILL seat is detection only: it classifies social velocity and
  quality as Organic, Mixed, or Coordinated/Paid and never posts,
  promotes, or generates volume. notify.alert is the single outbound
  exception and may target only the configured allowlist.
- The absence checks that prove the boundary are the static tests in
  tests/safety/test_no_manipulation_tools.py.

Current state: no legal review has been recorded. The legal group is
deferred to a human owner.

## 4. Nine-precondition evidence

Owner: human
Status: deferred

The live gate in src/pumpgrok/execution/live/live_gate.py evaluates the
nine preconditions in R21 order. The current unmet reasons quoted from
the gate are:

| # | Precondition id | Current unmet reason from the gate |
|---|-----------------|------------------------------------|
| 1 | mode_live | effective mode is paper |
| 2 | live_enable_env | PUMPGROK_LIVE_ENABLE is not 1 |
| 3 | min_paper_days | no source=paper ledger at var/ledger.sqlite |
| 4 | performance_thresholds | no source=paper ledger at var/ledger.sqlite |
| 5 | wallet_allowlist | live.wallet_allowlist is not a setting in this release |
| 6 | notional_cap | live.notional_cap_sol is not a setting in this release |
| 7 | confirmation_record | var/live_confirmation.json missing |
| 8 | adapter_registered | no live adapter implementation ships in this release |
| 9 | no_active_stop | halt, kill switch and breaker state are not readable in this release |

Notes on the evidence above:

- Preconditions 3 and 4 are measured only on ledger events with
  source=paper. Replay ledgers write under var/replay/DATASET and never
  count, and any source=replay row refuses both metrics. When a paper
  ledger exists, precondition 3 reports elapsed days as "N of 14 days on
  source=paper events" and precondition 4 reports "closed C, pf P, dd D
  pct on source=paper events" against closed_trades at least 50,
  profit_factor at least 1.2, and drawdown within 0.15.
- The nine ids above are the exact PRECONDITION_IDS the gate checks and
  the refusal output names. The roadmap nine grep passes on this record
  because it names all nine preconditions with their ids.
- A future decision re-evaluates every line. Meeting preconditions 1-7
  and 9 still leaves precondition 8 unmet, so the gate stays closed in
  this release.

## Refusal proof and exit contract

The desk proves live stays refused with these owning tests:

- tests/safety/test_live_refusal_lists_nine.py: run with mode live
  exits 3 and stderr lists all nine precondition ids in R21 order with
  number, id, and reason, plus the LIVE GATE header and the closing
  paper-mode line.
- tests/safety/test_no_live_adapter_registered.py: build_adapter
  returns a PaperAdapter, no live adapter symbol or registry entry is
  exported, and the gate reports adapter_registered unmet.
- tests/safety/test_import_graph_no_live.py: no transitive import path
  from the backtest package, the execution paper adapter, the upgrade
  package, the supervisor package, or the CLI reaches the live adapter
  module. Imports of the gate module live_gate by the CLI and the weekly
  report stay allowed; only the adapter module is quarantined.
- tests/safety/test_live_disabled_overlays.py: every overlay under
  src/pumpgrok/config/overlays ships with live disabled.

Exit contract: pumpgrok run --mode live --once exits 3 whenever any
precondition is unmet, prints every unmet line, and attempts no
transaction. No bypass flag and no operator override short of meeting
all nine preconditions exists, which is structurally impossible in this
release because precondition 8 has no implementation.

## What this record does not claim

- No paper evaluation window has produced the statistics preconditions
  3 and 4 require. Section 4 quotes the gate reasons, not results.
- No custody, venue, or legal requirement is approved. Each group above
  names owner human with status deferred.
- No signing, custody, or adapter code was added with this record.
