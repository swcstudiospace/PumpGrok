# Phase 14 Plan Check — 14-01 to 14-09 vs 14-CONTEXT, ROADMAP, REQUIREMENTS

Verdict: FAIL (0 blockers, 4 warnings, 3 advisories). Phase goal is reachable; the four warnings leave ROADMAP criteria only partly checkable and should be fixed before execution.

## Coverage (all 16 ROADMAP requirement ids claimed and checked)

EVT-08: 14-03 (parity test from 12-03, zero-skip proof). EVT-10: 14-03 wake plus 14-05 cycles. EVT-12: 14-03 timers plus 14-07 idle-zero, hang, triple-wired gate. EVT-13: 14-04 cutover plus 14-06 rollup replacement plus 14-07 doctor refusal. GRK-01 to GRK-04: 14-01 prefilter, explicit cache-key payload, coalescing, layered budget. GRK-05: 14-01 plus 14-02 adapters. GRK-06: 14-01 ladder on signal_scoring_mode values verified live in degraded.py. GRK-07: 14-01 import-graph test plus 14-07 hang test. GRK-08: 14-01 replay backend. GRK-09: 14-02, signal never calls GrokAgent.run. GRK-10: 14-04 metrics_events, NINE_FAMILIES intact. GRK-11: 14-01 evidence-50 fixture with at-least-50 production-filter assertion plus 14-04 ratio gate with min-candidates 50 on evidence-50 and soak-3d, so soak-3d vacuity (D-15) cannot pass silently. RT-01: 14-05 plus 14-06, all ten seats. MKT-03: 14-04 deletes scripts/probe_curve_layout.py with repo-wide grep proof. PRC-03/PRC-06: 14-08 equal hash pairs plus golden lines, 14-09 close. All D-01 to D-18 and OD-13 traced to plans. Live-refused exit 3 and replay-hash pins asserted in every execution plan. No signing or key code anywhere. No collect-only, --co, --no-verify, swallowed-error, or dry-run flags in any plan.

## Seat purity

PASS. Last-match-wins ownership resolves every files_modified path to its plan seat: 14-01 risk owns grok, core, tests/grok, tests/safety, fixtures; 14-02 signal owns engine/agents and tests/engine; 14-03 to 14-06 chief owns supervisor, scripts, hermes, skills/hermes-cron-desk, docs/runbooks, and tests/desk only (D-16 satisfied, no chief test outside tests/desk); 14-07 risk owns doctor, cli, tests, ci, Makefile, ci.yml; 14-08 journal owns CHANGELOG; 14-09 chief owns .planning. No executor writes approved_by. Summaries go to /tmp/v4/summaries.

## Dependencies and waves

Acyclic. 14-01 wave 1; 14-02 wave 2 on 14-01; 14-03 wave 1 on prior phases only; 14-04 and 14-05 wave 3 on 14-01/02/03; 14-06 wave 4 on 14-04/05; 14-07 wave 5; 14-08 wave 6; 14-09 wave 7. PR merge order 17 to 22 matches. Parity test (12-03) and trading-smoke pins (11-01) pre-exist as required. 14-08 golden lines correctly ordered after the 14-05 golden test.

## Warnings

1. [criterion 7] No plan runs tests/supervisor/test_scheduler.py, yet ROADMAP criterion 7 names it and 14-03 edits serve.py which hosts run_once_replay. Fix: add the scheduler test to the 14-03 acceptance list.
2. [criterion 16] No plan runs the contracts-unchanged check (git diff name-only v4-base -- contracts). scripts/check.sh is a docs and skills linter and does not cover it. Fix: add the contracts diff command to 14-09 acceptance.
3. [criterion 1] No plan runs make test or the paper replay smoke run; only lint, typecheck, targeted pytest, and check.sh are wired. Fix: add make test and the paper --once replay command to 14-09 acceptance (or document check.sh as covering them, which it currently does not).
4. [GRK-07 new code] The import-graph test proven in 14-01 covers legacy exit, risk, execution, watcher modules, but the new chief-owned event_cycles.py in 14-05 will host the exit cycle body while importing the gateway. The must_haves truth claims the exit path never waits on the gateway, but no static check pins the new file. Fix: extend test_no_grok_in_exit_risk (or the 14-05 cycle test) to assert the exit cycle path imports nothing from pumpgrok.grok and awaits no gateway call.

## Advisories

1. [shared receipt] 14-04 and 14-05 are both wave 3 on the same branch appending to the same receipt file. Different source files, but concurrent appends can conflict. Fix: run them ordered within the wave or split the receipt fragment merge explicitly.
2. [stale text] REQUIREMENTS GRK-02 still says the cache key comes from canonical_request_hash while locked D-07, ROADMAP criterion 2, and plan 14-01 correctly use the explicit payload (canonical_request_hash drops _at/seed/span keys and _freeze rejects Decimal). Fix: update the GRK-02 wording to match D-07; no plan change needed.
3. [cross-phase dep] 14-01 verification runs the trading-smoke pin from 11-01 but lists only 12-02 in depends_on. Phase order covers it. Fix: add 11-01 to 14-01 depends_on for explicitness.
