# Phase 19 CONTEXT: Observability, docs, hardening and milestone audit

Final v4 phase. Phases 11-18 land as draft-PR branches first; this phase
only starts once they merge (ROADMAP Execution Order 11->...->19). Live
trading stays refused throughout: `run --mode live` exits 3 on every
default start, no key or signing code enters the desk package, the paper-only
invariant holds. No hosted image is built, pushed or deployed in this phase
without owner approval (REQUIREMENTS HOST scope note).

## Locked decisions

- D-01: Paper-only invariant. Live stays refused end to end. Every plan
  preserves `uv run pumpgrok run --mode live --once; test $? -eq 3`
  (LIV-07 / OBS-05 final proof, success criterion 10). No live adapter is
  registered, no signing symbol or key enters `src/pumpgrok/`.
- D-02: Doctor v4 (OBS-01) reports event bus, source states, Grok budget
  windows, strategy stages, kills and signer attestation, read-only, in
  `src/pumpgrok/doctor.py`. No doctor probe writes state or sends.
- D-03: health.json and metrics (OBS-02) carry event, strategy and
  promotion sections plus the per-strategy P and live L metric families in
  `supervisor/health.py` and `supervisor/metrics_events.py`. No existing
  metric family is renamed or removed.
- D-04: Alert rules (OBS-03) live in `docs/observability/alerts.yaml` and
  every alert expression names a metric the registry exposes; nothing is
  alerted on a non-existent metric. Covered: dead letters, stale sources,
  Grok budget exhaustion, strategy kills, signer UNKNOWN.
- D-05: Docs (OBS-04) describe v4 and every documented command runs:
  `ARCHITECTURE.md`, `CLAUDE.md`, `AGENTS.md`, `README.md`, `SETUP.md`, the
  market-data, replay-and-backtest, doctor and monitoring skills, and the
  datafeed, recorder and promotion runbooks. Verified by
  `./scripts/verify_doc_commands.sh` plus `tests/test_skill_manifests.py`.
- D-06: Nightly event-mode soak (OBS-06) guards the idle-zero-Grok
  invariant with its golden hash: `tests/soak/test_soak_event_mode.py`
  under `PUMPGROK_REQUIRE_SOAK=1` with `-m slow`, scheduled in
  `.github/workflows/ci.yml`. The default `make test` path stays fast
  (QLT-01); soak never enters it.
- D-07: The amendment-PR waiver is removed after merge and the waiver set
  is empty again (PRC-08, success criterion 7). Removal is human-gated
  (plan 19-08 per the roadmap list of record) and is committed only as the
  owner-approved change; no new waiver is added.
- D-08: Hosted runtime (HOST-01..HOST-16) ships as code plus checks only.
  No hosted run starts, with or without the compose named volume
  (HOST-02), until HARD-07 passes (success criterion 12). HOST-15 labels
  every hosted replay health body and metric family as a replay demo
  (`replay_demo` true, `ledger_source` replay) until live-data paper
  lands; the label cannot be false before then. HOST-16 runs the
  live-data paper root in compose only after Phase 15 and the OD-04 probe
  review; the bundled fixture stays the default otherwise.
- D-09: HOST-03 owner design choice (halted state on /readyz) stays as
  specified: /livez is 200 while the loop runs regardless of halt/kill,
  /readyz is 503 on failed ledger verification or stale tick, and a
  halted desk is 200 on both with the halt in the body. If the owner
  changes the choice, the check is updated by the owner, not invented here.
- D-10: The milestone audit (OBS-05) at
  `.planning/milestones/v4-MILESTONE-AUDIT.md` traces every v4 requirement
  id (157 ids, see `.planning/REQUIREMENTS.md`) to evidence and records
  live-still-refused (criterion 8 + criterion 10). One CHANGELOG entry
  and one chief close record per phase 11-19 (PRC-06, criterion 9).
- D-11: Replay hashes are load-bearing. Smoke-10m events.hash stays
  `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`
  (PRC-03) and the trading-smoke pin is unchanged since the Phase 15
  flip. Any move is recorded in CHANGELOG with before and after hashes;
  an unrecorded move blocks closeout. Hash commands run in a fresh git
  worktree (no `var/ledger.sqlite`), because `verify` reads the
  working-directory ledger.
- D-12: Receipts are approved by the owner as `human:SomeRandmGuyy` in
  batches at the Phase 19 ship checkpoint (REQUIREMENTS v4 source note).
  This discuss+plan run writes planning files only: no code edits, no
  commits, no gates/lint/tests run. The orchestrator owns commit,
  verification and receipt approval.

## Grey areas with defaults and one-line reasons

- G-01: Each plan owns disjoint files inside a wave, because parallel
  executors must never write the same file. Waves follow the dependency
  chain: observability core before alerts/soak, hosted core before
  hosted edge, docs after behavior, waiver before audit.
- G-02: The audit is written last (plan 19-09) because it traces evidence
  from every earlier plan; writing it earlier would trace intentions,
  not results.
- G-03: `make test-all` runs once at closeout (criterion 1), not per
  plan, because the full soak-scale suite is too slow for every plan.
- G-04: No new package is added by any plan; if one proves necessary, the
  package-legitimacy audit and a human checkpoint are required before
  any install (STRIDE T-19-SC).
- G-05: HOST-16 is implemented as a compose command change gated by the
  Phase 15 root plus the OD-04 review flag, not by deleting the fixture
  path, because the replay demo profile still needs the fixture command.

## Scope boundary

In scope: doctor v4, health.json and metric sections, alert rules, v4
docs/skills/runbooks with runnable commands, nightly event soak, waiver
removal, hosted runtime code and checks, milestone audit and closeout
records, unchanged replay hashes, live-still-refused proof.

Out of scope: enabling or arming live, signing/custody/key material,
hosted image builds, pushes or deploys, paid RPC procurement, legal or
custody decisions, any product behavior beyond observability and hosted
readiness, edits outside `.planning/phases/19-observability/` in this
planning run, and any commit (orchestrator-owned).
