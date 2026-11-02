# Phase 13 plan check — PASS with warnings

Verdict: PASS. No blockers. 2 warnings, 2 advisories. Plans will achieve the phase goal as written.

## Coverage — all 11 phase requirements claimed with real commands

ROADMAP Phase 13 requires MKT-01, 02, 03, 04, 05, 06, 07, 08, 10, REC-01, REC-02.
FEE-01 is also in goal, deliverables, and criterion 6.

| Requirement | Plans | Check command present |
|---|---|---|
| MKT-01 layout token-first | 13-04 | tests/tools tests/execution tests/safety |
| MKT-02 five event types | 13-05 | test_pump_events round-trip plus truncation |
| MKT-03 probe record | 13-02, 13-05 | test_probe_record, decoded_pending_review grep |
| MKT-04 allowlist gate | 13-03, 13-04 | test_price_gate, test_curve_source_gate |
| MKT-05 watchset bridge | 13-01 | test_watchset, test_bridge, tests/events |
| MKT-06 reconnect dedup | 13-02 | test_feed, test_network_block |
| MKT-07 fail-closed price | 13-02 | test_price_source, test_graduation |
| MKT-08 marks 60 s | 13-02 | test_marks on fake Clock |
| MKT-10 decode status | 13-05 | test_event_decode_status |
| REC-01 sealed loads back | 13-01 | test_live_recorder via load_dataset |
| REC-02 gaps plus torn line | 13-01 | test_live_recorder -k gap or torn |
| FEE-01 v2 selectable v1 default | 13-03 | test_fee_model_v2 |

## Evidence of checks run

- Seat purity: sampled every files_modified entry through resolve_owner; all resolve to the plan seat (risk for datafeed, replay, conftest, docs probe, cli, safety; sniper for execution; rug for tools onchain; journal for CHANGELOG; chief for STATE, ROADMAP, VERIFICATION). G-1 manifest validates: 10 bots, 192 rules. Receipts live under .receipts/SEAT, no approved_by written anywhere; SUMMARIES go to /tmp/v4/summaries; only 13-07 touches .planning.
- Curve facts verified in src/pumpgrok/tools/onchain/curve_layout.py: swapped unpack at line 66 (disc, vsol, vtok, rsol, rtok), exact-length check lines 63-64, no discriminator comparison, fail-open gate line 161, encode_curve_fixture keyword signature lines 105-113. Foreign importers match the plan (tests/safety, tests/tools/market, tests/tools/safety). Fixture layout.json confirms repo-order versus idl-order. 13-04 task 1 quotes all four facts.
- Dependencies: frontmatter depends_on matches CONTEXT for all 7 plans; waves 1,2,1,3,4,5,6 consistent; dep plan files 11-01, 11-06, 11-07, 11-09, 12-01, 12-02, 12-03 exist; shared branch pairs (13-01 with 13-02, 13-04 with 13-05) are ordered by declared edges; no same-wave shared files between 13-01 and 13-03.
- Honesty: no collect-only, --co, error swallowing, dry-run, force, or live-enable flags in any command (one mention is the explicit prohibition text). TDD red-green stated for 13-01 through 13-05. Live refusal exit 3 in every acceptance. Hash b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d pinned in all relevant accepts; trading-smoke value read from pins file, never hand-copied.
- No-send proof: 13-01 AST test forbids send and signing calls outside readonly.py plus paid streams never subscribed; 13-02 single PumpPortal connection with 30 per 10 s limiter and dedup; 13-03 factory never imports live plus import-graph test and data_unavailable fail-closed at buy and confirm; 13-05 ASSUMED closure keeps buys fail-closed.
- Scope: D-01 through D-16 all addressed; deferred ideas excluded (trades.jsonl stays off); live refused; no signing or key code; money integer lamports with Clock-only time in every behavior plan.

## Warnings

### W1 — 13-03 over-claims LIV-06 and RSK-05
Plan: 13-03. Evidence: requirements frontmatter lists LIV-06 and RSK-05, but no task runs their canonical checks (tests/live/test_registry.py, tests/risk/test_entry_checks.py); those files belong to later phases and do not exist in this phase scope. The plan delivers only the phase-13 contribution (factory plus Protocol).
Fix: remove LIV-06 and RSK-05 from the 13-03 requirements list, keeping MKT-04, FEE-01, and the MKT-09 first-half contribution.

### W2 — 13-05 human gate has no automated provenance check
Plan: 13-05. Evidence: the reviewed_by human record is searched in agent-writable paths (docs, tests/fixtures/rpc, tools/onchain); an executor could self-author such a line and the conditional status tests would still pass. Detection today rests only on owner diff review at CP14 (draft PR, failing G-2 by design, batch human approval).
Fix: require the reviewed_by record to arrive in a commit outside the PR-14 branch, add a flip-task check that fails unless git log shows the record introduced outside the plan branch, and quote the record plus its commit author in the SUMMARY and in 13-VERIFICATION.md.

## Advisories

### A1 — MKT-09 claimed without first-half scoping
Plans 13-01 and 13-03 list MKT-09, but deliver only the allowlist and AST half; the composition-root half (test_live_paper_root) completes in Phase 15 per ROADMAP criterion 13. Annotate both plans as first-half delivery.

### A2 — 13-02 conftest.py edit has no pre-merge foreign-suite regression
The shared root conftest websocket patch is verified only by the plan's own suites; cross-suite breakage is caught only by PR CI and the 13-07 check.sh full run. Acceptable, noted for merge-order awareness (PR-12 merges before PR-14).

## Structured issues

```yaml
issues:
  - plan: "13-03"
    dimension: "requirement_coverage"
    severity: "warning"
    required_property: "A plan claims only requirement ids whose canonical checks it runs"
    description: "13-03 lists LIV-06 and RSK-05 but runs neither tests/live/test_registry.py nor tests/risk/test_entry_checks.py"
    fix_hint: "Drop LIV-06 and RSK-05 from 13-03 requirements"
  - plan: "13-05"
    dimension: "context_compliance"
    severity: "warning"
    required_property: "No executor path can flip VERIFIED on a self-authored human record"
    description: "reviewed_by is searched only in agent-writable paths with no commit-provenance check; conditional tests pass on a fabricated record"
    fix_hint: "Gate the flip on a record committed outside the PR-14 branch and quote record plus commit author"
  - plan: "13-01"
    dimension: "requirement_coverage"
    severity: "info"
    required_property: "Partial requirement delivery is labeled as partial"
    description: "MKT-09 listed without noting only the first half is delivered here"
    fix_hint: "Annotate MKT-09 as first-half, composition root in Phase 15"
  - plan: "13-02"
    dimension: "scope_sanity"
    severity: "info"
    required_property: "Shared-file edits name their blast radius"
    description: "tests/conftest.py affects all suites but no acceptance runs a foreign-suite regression pre-merge"
    fix_hint: "Note reliance on PR CI and 13-07 check.sh for cross-suite coverage"
```
