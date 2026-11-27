# PumpGrok release T1482 docs bundle

Status: release blocked, do not promote. Paper-only. ASCII only.
Correlation: 1482cee0-ef94-43e4-8400-e343d6141fbe. Task: T1482-docs.

This bundle is the A15 render of the T1482 upstream artifacts. It changes
no code, no contract and no SLO number. If a fact below differs from an
upstream artifact, the upstream artifact wins and this file is fixed.

## Gate verdicts

| Gate | Result | Source |
|---|---|---|
| review | pass | T1482-rev.r2, rules pass, semantic pass |
| security | pass | T1482-sec.r2, secrets pass, sast pass |
| quality | fail | T1482-qa.r2, QF-001 tenacity env, 0 failing |
| release | fail | T1482-rel, REL-T1482-be, do not promote |

Review pass and security pass are the r2 verdicts. The earlier security
fail and quality fail are superseded by r2 for review and security only.
Quality still fails on the environment: pytest cannot load conftest because
tenacity is not installed in the QA environment. Release fails because
quality fails on T1482-be, T1482-fe and T1482-data, and because no
build artifact provenance is registered. Do not promote. No canary step
starts until quality passes and provenance is registered.

## Pull requests

- PR128: feat(fe) paper-only operator console, 7 screens, branch
  bot-00-chief/T1482-fe, state OPEN. It is blocked by the release fail.
  Do not merge until quality passes.
- PR129: feat(be) consume M-2026-1120 indexes in ledger _SCHEMA, branch
  bot-02-risk/T1482-be, state OPEN. Head 72f8a36 holds the r2 fixes.
  It is blocked by the release fail. Do not merge until quality passes.

## Upstream render table

- Requirements: docs/requirements/spec.md, 26 stories US-001 to US-026,
  30 criteria AC-001 to AC-030, 5 NFRs NFR-P1, NFR-S1, NFR-A1, NFR-I1,
  NFR-C1. Paper-only per NFR-C1.
- Architecture: docs/architecture/blueprint.md, contract
  docs/architecture/contracts/pumpgrok-gateway.yaml v1.0.0, ADR-0001 to
  ADR-0004. ADR render coverage is checked with the coverage report.
- UX: docs/design/ux-spec.json, 7 screens SCR-MilestoneTracker,
  SCR-GateDashboard, SCR-QualitySweeps, SCR-ReplayDesk, SCR-AuditEvidence,
  SCR-OperatorDocs, SCR-SafetyPaperOnly. All screens are ASCII-only
  operator views, paper-only, no key or fund movement surface.
- Data: docs/data/data-model.md, SQLite ledger, append-only events,
  18 event types, M-2026-1120 indexes idx_events_type_ts,
  idx_events_correlation, idx_events_ts_seq.
- API: docs/api-reference.md, 2 endpoints GET /healthz and
  POST /mcp/{short}.
- Runbook: docs/runbooks/slo_canary.md, canary 5/25/50/100, error 0.005,
  p95 320ms.

## SLO guardrails

Release plan REL-T1482-be is canary with steps 5/25/50/100 percent.
Guardrails are error_rate_max 0.005, p95_ms_max 320, slo_burn_max 2.0,
soak_min 15. Rollback triggers are error rate above 0.005 over 5m,
p95 latency above 320ms over 5m, SLO burn above 2.0x over 1h, a
rollback-suggested telemetry verdict, a sev2 or higher incident naming
this release, or monitoring degraded. On any trigger, halt at the
current step and roll back. The release is blocked, so no step runs now.

## Coverage

- docs/ scope: docs_bundle status ok, 0 findings, packages documented 100
  percent, docs with title 100 percent.
- Full repo scan: 339 markdown files, 97 findings, 11 major broken-link
  findings in .planning history outside docs/. Those majors are
  pre-existing and out of the A15 zone. They do not block this docs/
  bundle. They are backlogged for the owning seat.
- API coverage, ADR coverage, readability and runbook ratio are reported
  in the coverage report section below.

## Changelog

CHANGELOG.md holds the Keep-a-Changelog Unreleased section for T1482.
It records PR128 and PR129, the gate verdicts and the blocked state.
Entries come from conventional commits only, never from memory.

## Checks run

- docs_bundle python and bun twins, full root and docs/ scope.
- docs_heading_order on the changelog fragment.
- docs_changelog_section_order on the new section.
- docs_conventional_groups on recent commit subjects.
- docs_api_endpoint_coverage on the gateway contract.
- docs_adr_render_coverage on ADR-0001 to ADR-0004.
- docs_flesch_grade on the user-facing prose.
- docs_runbook_schema_check and docs_runbook_verified_ratio on the new
  runbook.
- docs_stale_doc_age on the new docs.
