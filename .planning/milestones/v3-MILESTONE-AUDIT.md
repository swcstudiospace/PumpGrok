---
milestone: v3
audited: 2026-11-01T08:43:58Z
status: tech_debt
scores:
  requirements: 34/34 verified by a passing phase verification (0 unsatisfied, 0 orphaned; 3 satisfied in all three sources, 31 partial on SUMMARY metadata)
  phases: 7/7 verification status passed (6, 7, 8, 9, 10, 20, 21)
  integration: 0 blocking; 2 closed in this run (LIV-01 by phase 20, DOC-03 by phase 21); 1 accepted by owner (UPG-03 operator command)
  flows: 1 checked (replay smoke and verify CONSISTENT); no separate end-to-end flow audit
gaps:
  requirements: []
  integration: []
  flows: []
tech_debt:
  - phase: "06"
    items:
      - "Criterion 17 owner-waived for the phase PR (PROJECT V3-5); later correction and supersession notes in 06-VERIFICATION.md"
      - "Phase 6 evidence paths cite /root/src/repos/pumpgrok, a different checkout"
  - phase: "07"
    items:
      - "OVERRIDE-A to OVERRIDE-D deviation judgements recorded in 07-VERIFICATION.md (re-checked: still valid)"
      - "docs/ROSTER.md and docs/FOUNDATION_STACK.md: design documents outside the DOC-04 fixed set (scope decision for the owner)"
      - "Criterion 4 re-baselined from origin/main to f3887bb (phase start point), dated note in ROADMAP"
  - phase: "08"
    items:
      - "Criteria 3, 4, 5, 9 evidenced by a targeted run rather than a standalone command (verifier note)"
      - "Path drift in SUMMARY references (BT-06 path drift)"
  - phase: "09"
    items:
      - "docs/RISK_POLICY.md line 25 still paraphrases clause 10 (recorded as non-FAIL in 09-VERIFICATION.md; not re-verified)"
  - phase: "10"
    items:
      - "Earlier PASS on the import-graph claim was wrong; corrected by phase 20 (correction note in 10-VERIFICATION.md)"
  - phase: "20"
    items:
      - "AST guard does not see dynamic imports (pkgutil, importlib); reviewer F-01 minor, no present false negative"
  - phase: "21"
    items:
      - "Out-of-scope docs still say eight roles or name absent helpers: agents/README.md, skills/desk-operating-model/SKILL.md, skills/pumpgrok-setup/SKILL.md, scripts/hermes-bootstrap.sh, scripts/README.md, skills/holder-and-flow-analysis/SKILL.md"
      - "Design and history docs keep trading-desk, paper_sim, ticket_helper and eight wording (D-10): docs/ROSTER.md, docs/upgrade-plan-desk-v2.md, docs/FOUNDATION_STACK.md, docs/DISCOVERY.md, docs/MIGRATION_MAP.md, docs/design/*"
      - "docs/VENDOR_PIN.md:9 names the absent vendored license path (historical provenance; retained copy in src/pumpgrok/engine)"
      - "Plugin manifest description parenthetical lists eight names (.claude-plugin/plugin.json:3)"
      - "Literal reading of DOC-03 each change appears in CHANGELOG: entries are per document, row-level list in 21-01-SUMMARY (owner to confirm the interpretation)"
      - "tests/docs does not cover the ARCHITECTURE diagram or read-only wording; no recurrence guard"
      - "Placeholder org name your-org in SETUP.md and marketplace manifests (allowlisted in scripts/check.sh)"
  - phase: "all"
    items:
      - "requirements-completed frontmatter present only in 06-05 (INT-08), 20-01 (LIV-01) and 21-01 (DOC-03); 31 requirements are partial on this metadata alone"
      - "Operator rollback command absent: restore_active_set has tests only; UPG-03 is met by its own definition and Phase 9 criterion 5, accepted by the owner"
      - "Nyquist VALIDATION.md missing for every v3 phase (validate-phase hook active; discovery only, a coverage item, not a blocker)"
      - "Phase verification evidence written in a checkout other than the worktree in the first run (corrected by re-verification at the worktree)"
      - "28 historical marker lines, all PARKED, in .planning/BACKLOG-INVENTORY.md"
      - "Operator readiness visibility deferred by owner decision (PARKED)"
nyquist:
  compliant_phases: []
  partial_phases: []
  not_validated_phases: []
  missing_phases: ["06", "07", "08", "09", "10", "20", "21"]
  overall: missing (discovery only)
---

# Milestone v3 audit: PumpGrok Desk v3

Result: **tech_debt**. No requirement is unsatisfied and no integration gap remains open. The audit records accumulated debt that needs the owner's decision before archive. Audited 2026-11-01T08:43:58Z on branch bot-00-chief/v3-closeout.

## What changed since the first audit (gaps_found, commit 9bfb0f6)

- LIV-01 (phase 10 claim false at runtime): closed by phase 20 (commits 148dbfa, 02f5997, 21e99dd, c3898ec, e58920b). Runtime probe: live_adapter absent, live_gate present. Guard now models parent-package edges.
- UPG-03: the integration check read the requirement as needing an operator command. The requirement says one operation rolls back to the exact prior version, verified by a test, and Phase 9 criterion 5 is that test (9 of 9 pass). The owner accepted UPG-03 as met; the operator command is tech debt.
- Orphaned requirements (11 IDs absent from every VERIFICATION file): resolved by re-verifying phases 7, 8 and 10 with explicit IDs, and by phase 20 for LIV-01.
- DOC-03 (re-verification found it unmet): closed by phase 21 (red-first manifest test, manifest versions, ARCHITECTURE diagram, read-only wording, ticket next and VENDOR_PIN corrections, CLAUDE.md anchors). Phase 21 verification passed at HEAD da51664.
- PAP-02 integration warning (alert channel unverified): the requirement names no delivery channel; the breach raises an alert, blocks promotion, and the divergence test passes. Met.
- Phase 7 criterion 4: the literal comparison against origin/main could not pass after the merge. Re-baselined to f3887bb (423 lines, phase start point; HEAD 133 lines).

## Sources

- Phase VERIFICATION.md at HEAD: phases 6 and 9 (earlier, not stale); 7 (da51664), 8 and 10 (e58920b, product code unchanged since), 20 (c3898ec), 21 (da51664).
- REQUIREMENTS.md: 34 v3 IDs, all checked and traced.
- SUMMARY frontmatter requirements-completed: present for 06-05 (INT-08), 20-01 (LIV-01), 21-01 (DOC-03).
- Matrix script (read-only, /tmp/audit_matrix.py) on the committed tree.
- Canonical test target: make test exit 0 at 9cb6e66 (2404 tests in the phase 20 run; full run at 9cb6e66 reached 100 percent).

## Requirements

| Requirement | Class | Verification phases | SUMMARY phases |
|---|---|---|---|
| BT-01 | partial | 08-backtest-and-paper-evaluation | - |
| BT-02 | partial | 08-backtest-and-paper-evaluation | - |
| BT-03 | partial | 08-backtest-and-paper-evaluation | - |
| BT-04 | partial | 08-backtest-and-paper-evaluation | - |
| BT-05 | partial | 08-backtest-and-paper-evaluation | - |
| BT-06 | partial | 08-backtest-and-paper-evaluation | - |
| BT-07 | partial | 08-backtest-and-paper-evaluation | - |
| DOC-01 | partial | 07-documentation-upgrade | - |
| DOC-02 | partial | 07-documentation-upgrade | - |
| DOC-03 | satisfied | 07-documentation-upgrade, 21-close-gap-doc-03-documentation-accuracy | 21-close-gap-doc-03-documentation-accuracy |
| DOC-04 | partial | 07-documentation-upgrade | - |
| INT-01 | partial | 06-integrity-closure | - |
| INT-02 | partial | 06-integrity-closure | - |
| INT-03 | partial | 06-integrity-closure | - |
| INT-04 | partial | 06-integrity-closure | - |
| INT-05 | partial | 06-integrity-closure | - |
| INT-06 | partial | 06-integrity-closure | - |
| INT-07 | partial | 06-integrity-closure | - |
| INT-08 | satisfied | 06-integrity-closure | 06-integrity-closure |
| INT-09 | partial | 06-integrity-closure | - |
| INT-10 | partial | 06-integrity-closure | - |
| LIV-01 | satisfied | 10-live-readiness-kept-disabled, 20-close-gap-liv-01-live-adapter-import-path | 20-close-gap-liv-01-live-adapter-import-path |
| LIV-02 | partial | 10-live-readiness-kept-disabled | - |
| PAP-01 | partial | 08-backtest-and-paper-evaluation | - |
| PAP-02 | partial | 08-backtest-and-paper-evaluation | - |
| PAP-03 | partial | 08-backtest-and-paper-evaluation | - |
| PRC-01 | partial | 06-integrity-closure, 07-documentation-upgrade | - |
| PRC-02 | partial | 06-integrity-closure | - |
| UPG-01 | partial | 09-bounded-paper-self-upgrade | - |
| UPG-02 | partial | 09-bounded-paper-self-upgrade | - |
| UPG-03 | partial | 09-bounded-paper-self-upgrade | - |
| UPG-04 | partial | 09-bounded-paper-self-upgrade | - |
| UPG-05 | partial | 09-bounded-paper-self-upgrade | - |
| UPG-06 | partial | 09-bounded-paper-self-upgrade | - |

Classes: satisfied = passed verification and listed in SUMMARY frontmatter. partial = passed verification, SUMMARY frontmatter omits the ID (metadata debt, verified manually against the passing verification). No row is unsatisfied or orphaned.

## Phases

| Phase | Verification | Notes |
|---|---|---|
| 06 integrity closure | passed | criterion 17 owner-waived |
| 07 documentation upgrade | passed (da51664) | DOC-01 to DOC-04 satisfied after phase 21; criterion 4 re-baselined |
| 08 backtest and paper evaluation | passed (e58920b) | PAP-02 met by its requirement text |
| 09 bounded paper self-upgrade | passed | not re-verified; no covered file changed |
| 10 live readiness, kept disabled | passed (e58920b) | corrected by phase 20 |
| 20 close gap LIV-01 | passed (c3898ec) | import path closed; reviewer minor F-01 |
| 21 close gap DOC-03 | passed (da51664) | red-first test; two closure rounds |

## Tech debt

Listed in the YAML above. Decision for the owner: accept this debt and archive (complete milestone), or plan a cleanup phase first (see routing).

## Routing

- Status tech_debt: archive requires the owner's explicit decision. The archive is irreversible; the tag lands on the bot branch HEAD until merge.
- Verification counts used here are from the phase records and the orchestrator runs; no full re-run of phase 9 was made.

## Correction (2026-11-01)

INT-10 is partially met, not satisfied. The requirement says the bonding-curve layout is probed read-only against live mainnet accounts. The probe script exists (scripts/probe_curve_layout.py). No bonding-curve account is configured in this checkout, so the probe makes no RPC call and records Status ASSUMED (docs/CURVE_LAYOUT_PROBE.md). The layout stays ASSUMED (src/pumpgrok/tools/onchain/curve_layout.py:33), and RPC-derived curve entries fail closed with data_unavailable. Phase 6 verification row 11a passed on that recorded ASSUMED result, so the requirement count above overstates INT-10. This item was not on the debt list the owner reviewed. The status stays tech_debt, because the fail-closed behaviour is verified and the live probe is recorded as debt.


## Method note (2026-11-01)

The traceability scores above count requirement IDs that appear in each phase's VERIFICATION prose. The workflow's table-based rule (requirement rows in each VERIFICATION file) was not applied. Under that rule, phases 06, 09 and 20 have no requirement rows, and phases 07, 08, 10 and 21 have 4, 10, 2 and 1 rows. The owner accepted the mention-based result as documented on 2026-11-01; the archived status stays tech_debt.
