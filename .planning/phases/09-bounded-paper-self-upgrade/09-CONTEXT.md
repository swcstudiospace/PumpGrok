# Phase 9 CONTEXT: Bounded paper self-upgrade

Milestone v3, Phase 9. Goal per ROADMAP: paper parameter sets are content-hashed
and held within version-controlled bounds; a candidate is promoted only through
the gate; every promotion records its evidence and one operation rolls back to
the exact prior version; SAFE-4 and SAFE-8 BLIND results are advisory while no
paid RPC provider is recorded; the approved constitution amendment lands with
the code it describes.

Depends on: Phase 8 (verified 13 of 13). Phase 9 reuses without re-implementing:
CandidateParams with validated filter and exits overrides, evaluate_window,
fold_windows in src/pumpgrok/backtest/evaluate.py; run_search, trial ledger and
holdout-once in src/pumpgrok/backtest/harness.py; render in
src/pumpgrok/backtest/report.py; D7 constants and check in
src/pumpgrok/backtest/divergence.py; param_set_hash and dataset_digest in
src/pumpgrok/backtest/manifest.py; SharedResult.compare in
src/pumpgrok/backtest/results.py. Trial caps come from
src/pumpgrok/backtest/trials.py: MAX_ELIGIBLE_TRIALS 20, MAX_ALLOWED_TRIALS 50.
Autonomy reads through src/pumpgrok/ledger/autonomy.py read_autonomy.
Manual-ticket guard precedent: tests/safety/test_manual_ticket_no_upgrade.py.

## Locked decisions (NON-NEGOTIABLE)

- D-01: Money as integers in base units; Decimal only for ratios. No float money.
- D-02: ULIDs from core/ids.py; time through the Clock; no direct asyncio.sleep
  or time.time in new code.
- D-03: Paper only. No live order path. Live stays refused with exit 3.
- D-04: Parameter sets are content-hashed. The hash identifies the exact set.
  Identity hashing with sha256 is allowed. No hash, random value or digest may
  act as a score, a metric or a verdict. This was the Phase 8 failure and the
  plan checker must reject it.
- D-05: Promotion goes only through the gate: the Phase 8 divergence check
  (D7 defaults) on the same window, the trial limits (above 20 trials is
  ineligible, above 50 is rejected), and the holdout rule. A promotion never
  bypasses the gate. Rollback restores the exact prior content hash and is
  tested as a real round-trip, not a wiring check.
- D-06: Every promotion records its evidence (the backtest run id, the
  divergence verdict, the holdout id, the prior and new hashes) in the ledger
  or a manifest file. The record is real, not a placeholder.
- D-07: Bounds are version-controlled. A value outside bounds is rejected with
  a typed error, never clamped silently.
- D-08: BLIND handling per the approved amendment: BLIND for SAFE-4 and SAFE-8
  is advisory only; all other BLIND behavior is unchanged.
- D-09: The replay smoke command must still complete one cycle. The active-set
  record may change replay output, so both before and after hashes are recorded;
  equal values are acceptable.
- D-10: Style: mypy --strict on src/pumpgrok, ruff, no dead code, no swallowed
  errors, no TODO or placeholder text, ASCII-only new docs, constitutional
  strings keep their exact bytes (U+2013 dashes) in code.
- D-11: Criterion 9 hashes: no executor runs pumpgrok verify. The after hash is
  measured by the orchestrator at the gate. CHANGELOG lines carry UPPERCASE
  placeholders the orchestrator replaces.
- D-12: Manual-ticket never runs an upgrade. The existing guard test keeps
  passing and is extended to the active-set record.

## Grey-area defaults (each with a one-line reason)

- G-01: The active set is recorded as a ConfigChanged row with
  keys_changed holding active_param_set, plus a JournalNote, reusing the
  autonomy.py precedent. Reason: it reuses the single-writer and reconcile
  paths with no schema migration.
- G-02: Bounds live at src/pumpgrok/config/upgrade_bounds.toml with filter and
  exits range tables. Reason: it matches the TOML overlay precedent and the
  exact path criterion 2 parses.
- G-03: ParamSet hash is sha256 over the canonical_json of the normalized
  overrides, identity only and never a score. Reason: canonical_json already
  grounds run ids in manifest.py, which keeps hashing consistent and avoids a
  repeat of the Phase 8 digest-as-score failure.
- G-04: Out-of-bounds values raise typed OutOfBoundsError naming the key, the
  value and the allowed range. Reason: the locked constraint demands a typed
  rejection, mirroring TooManyTrialsError, so misconfiguration fails closed.
- G-05: Promotion evidence is a JSON manifest file under
  var/upgrade/promotions/ named by the new hash, referenced from a ledger
  JournalNote. Reason: it mirrors the trial-ledger JSONL precedent while the
  ledger stays hash-chained and small.
- G-06: The paid-provider signal is env PUMPGROK_PAID_RPC_PROVIDER, empty or
  unset meaning none recorded, with the human recording kept in STATE.md.
  Reason: the secrets policy keeps provider material in env and out of TOML,
  and env is the only runtime-readable signal.
- G-07: Rollback is one operation restore_active_set that writes the exact
  prior hash as a new ConfigChanged row plus a JournalNote, verified by a
  promote-then-rollback round-trip test. Reason: criterion 5 demands an exact
  round-trip restore, not a wiring check.
- G-08: Gate check order is bounds, then trials, then autonomy level, then
  holdout, then divergence, with the first failure winning as the typed
  reason. Reason: cheapest checks run first and escalation names one
  deterministic cause.
- G-09: The upgrade package exposes no CLI verb and imports nothing from
  execution.live, proven by a static guard test. Reason: it keeps the Phase 10
  import-graph proof green by construction.
- G-10: Escalation emits an Escalation event plus a JournalNote decision
  request naming the blocking reason. Reason: it follows the existing
  escalation channel in RISK_POLICY section 5 instead of inventing a new one.

## Scope boundary

In scope: src/pumpgrok/upgrade/ package (params, bounds, gate, evidence,
rollback, escalate); src/pumpgrok/config/upgrade_bounds.toml;
src/pumpgrok/ledger/active_set.py; SAFE-4 and SAFE-8 advisory BLIND handling
in src/pumpgrok/tools/safety/; the amendment applied verbatim to
rules/pumpgrok-team.mdc, skills/desk-operating-model/SKILL.md,
prompts/_shared/core-directives.xml, regenerated agents files, regenerated
prompts, docs/RISK_POLICY.md and .planning/PROJECT.md; the frozen amendment
oracle and its test; tests/upgrade/ and tests/safety/test_blind_advisory.py;
CHANGELOG before and after replay hash lines; the manual-ticket guard
extension; the no-live-import static guard.

Out of scope: any live adapter, signing, custody or wallet code; new signal
families or alpha research; paid RPC procurement or spend; external historical
data; the manual-ticket exit approval path (PAPER-007, deferred); the Phase 10
import-graph proof itself; Telegram verification and other human actions.

## Amendment copies found (executor plan 09-06 applies all of these)

Verbatim constitution carriers per the amendment scope section, confirmed by
grep on this checkout:

- rules/pumpgrok-team.mdc: description line, line 8 role sentence, clause 2
  append, clause 8 replacement, SIGNAL and JOURNAL bullets.
- skills/desk-operating-model/SKILL.md: L2 lines 24, 31 and 32.
- agents/risk.md clause 10. All ten agents files carry the same clause 10 text
  (chief, exit, journal, risk, rug, scout, shill, signal, sniper, whale) because
  they are generated from prompts/_shared/core-directives.xml by
  scripts/generate-templates.py. The executor edits the prompt source and
  regenerates; it never hand-edits agents files.
- prompts/_shared/core-directives.xml clause 10 (generator source).
- docs/RISK_POLICY.md: the row 8 quote and section 2.4 heading plus paragraph.
- .planning/PROJECT.md: BLIND constraint and strategy out-of-scope row.
- Regenerated outputs: agents/*.md via make prompts, verified with
  generate-templates --check; prompts-assembled outputs if make prompts
  rewrites them.
- New frozen oracle for tests/safety/test_constitution_amendment.py, exact
  filename chosen by the executor.

Checked and intentionally not amended (outside amendment scope): docs/ROSTER.md
references, docs/SAFETY_INVARIANTS.md notes, skills/browser-ops/SKILL.md,
skills/pumpgrok-setup/SKILL.md, rules/README.md, tests/docs fixtures.

## Criterion map (ROADMAP success criteria to plans)

- Criterion 1 (lint, typecheck, test, check.sh, smoke): plan 09-07 Task 2.
- Criterion 2 (param hash test, active-set ledger test, toml parse): 09-01
  Task 1 carries the hash test and the toml parse command; 09-02 Task 2
  carries the ledger test command.
- Criterion 3 (promotion gate blocks five cases): plan 09-03 Task 2.
- Criterion 4 (promotion evidence): plan 09-03 Task 2.
- Criterion 5 (exact rollback): plan 09-04 Task 1.
- Criterion 6 (escalation): plan 09-04 Task 2.
- Criterion 7 (BLIND advisory): plan 09-05 Task 2.
- Criterion 8 (generate-templates check plus amendment test): plan 09-06
  Task 2.
- Criterion 9 (replay before and after hashes in CHANGELOG): plan 09-07
  Task 1. The verify-twice portion runs at the gate by the orchestrator per
  D-11, not in any executor.
- Criterion 10 (live refused with upgrade modules present): plan 09-07 Task 2.

Every criterion maps to a task. Nothing is unmapped.
