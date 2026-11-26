# Wireframes - PumpGrok operator console (lofi ASCII, PROVISIONAL)

Tokens: docs/design/tokens.json v1.0.0. Fidelity lofi, provisional true
(no brand guide, no Figma). ASCII only per NFR-A1/NFR-I1. Every screen
has default/loading/error/empty/success frames below; regions label the
ds/* ref they use. Interactive ids match ux-spec.json focus_order.
Motion: fade 150ms, slide 200ms, both with reduced-motion (instant)
variant; max 300ms. Targets: 44x44 CSS px minimum.

## SCR-MilestoneTracker (default)
+-----------------------------------------------------------+
| [Input: Filter milestone]  [Button: Refresh tracker]      |
+-----------------------------------------------------------+
| [Table: milestone|units|evidence|owner]                   |
| Phase 11           | 12/12  | exit 0   | chief          |
| Phase 12           | 0/8    | pending  | release-owner  |
| [Badge: status per row]                                   |
+-----------------------------------------------------------+
loading: [Progress determinate] "Loading milestones..."
error.network: [Alert error] "ERROR code=1 msg=tracker-unavailable"
error.validation: [Alert error] "ERROR code=1 msg=invalid-filter"
empty.milestones: "No milestones match filter."
success: [Badge success] "16 of 16 milestone groups tracked"

## SCR-GateDashboard (default)
+-----------------------------------------------------------+
| [Button: Rerun gates]                                     |
| [Table: gate|exit-code|job|status]                        |
| lint/typecheck/test/audit | 0 | ... | [Badge status]     |
| [Alert error single-line ASCII on failure]                |
+-----------------------------------------------------------+
loading: [Progress] "Running gates..."
error.network: "ERROR code=1 msg=ci-unavailable"
error.validation: "ERROR code=1 msg=invalid-gate-selection"
empty.gates: "No gate runs recorded."
success: [Badge success] "4 of 4 canonical gates exit 0"

## SCR-QualitySweeps (default)
+-----------------------------------------------------------+
| [Button: Export sweep report]                             |
| [Table: sweep|check|count|result] B00-B09                 |
| [Progress determinate] [Badge status per sweep]           |
+-----------------------------------------------------------+
loading: "Running sweep checks..."
error.network: "ERROR code=1 msg=sweep-source-unavailable"
error.validation: "ERROR code=1 msg=invalid-sweep-selection"
empty.sweeps: "No sweeps in scope."
success: [Badge success] "0 open findings"

## SCR-ReplayDesk (default)
+-----------------------------------------------------------+
| [Input: Seed] [Button: Run replay smoke]                  |
| [Table: run|seed|event-hash|cycle]                        |
| smoke-10m seed 7 | sha256 b69c... | 1 full cycle          |
+-----------------------------------------------------------+
loading: "Replaying..." (determinate progress)
error.network: "ERROR code=1 msg=replay-data-unavailable"
error.validation: "ERROR code=1 msg=invalid-seed"
empty.replay: "No replay runs yet."
success: [Badge success] "hash identical on rerun"

## SCR-AuditEvidence (default)
+-----------------------------------------------------------+
| [Button: Rerun transcript]                                |
| [Table: claim|command|exit-code|output-hash] 8 claims     |
| [Alert info] "Transcripts rerunnable verbatim"            |
+-----------------------------------------------------------+
loading: "Rerunning transcripts..."
error.network: "ERROR code=1 msg=transcript-store-unavailable"
error.validation: "ERROR code=1 msg=invalid-claim-selection"
empty.evidence: "No evidence recorded."
success: [Badge success] "8 of 8 commands exit 0"

## SCR-OperatorDocs (default)
+-----------------------------------------------------------+
| [Button: Verify doc commands]                             |
| [Table: document|command|expected-exit|actual-exit] 24    |
+-----------------------------------------------------------+
loading: "Executing documented commands..."
error.network: "ERROR code=1 msg=docs-unavailable"
error.validation: "ERROR code=1 msg=invalid-document-selection"
empty.docs: "No documents in scope."
success: [Badge success] "24 of 24 documented exit codes"

## SCR-SafetyPaperOnly (default)
+-----------------------------------------------------------+
| [Button: Check live refusal]                              |
| [Table: check|precondition|result|exit-code]              |
| live refusal exit 3 | 0 live adapters | 0 keys            |
| [Alert error] "ERROR code=3 msg=live-mode-refused ..."    |
+-----------------------------------------------------------+
loading: "Running safety checks..."
error.network: "ERROR code=1 msg=safety-store-unavailable"
error.validation: "ERROR code=1 msg=invalid-check-selection"
empty.receipts: "No receipts recorded."
success: [Badge success] "paper-only holds: 0 fund-moving paths"
Note: this screen never renders a seed phrase, private key, or
live-trade control; there is no such field to focus.
