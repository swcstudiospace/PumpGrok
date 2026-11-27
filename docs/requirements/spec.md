# Requirements specification - PumpGrok outstanding milestones (T1482-req)

Version 1.0. Status: VALIDATED pending publish gate. Owner: A02.

## 1. Purpose

Program the outstanding PumpGrok milestones as Linear Issues with
Sub-Issues and gate every delivery on machine-checkable criteria. Scope
covers v4 Phases 11-14, the Phase 17 series, sweeps B00-B09 and the
L1-P1 fix set. The desk runs paper-only: no live adapter, no keys and
no fund movement ship at any point.

## 2. Scope and assumptions

- In scope: 16 milestone groups (4 phases, 1 phase series, 10 sweeps,
  1 fix set), the canonical gate suite, replay determinism, live
  refusal, gateway tests, per-PR CI and merge discipline.
- Out of scope: live trading enablement, key custody, any design or
  schedule decision (A03 and A01 own those).
- Assumption A-1: sweep B00-B09 map in order to typing, lint, money,
  time, contracts, fail-closed, determinism, tests, dependency audit
  and documentation sweeps. The mapping is the A02 reading of the
  brief; the owner confirms or corrects it at the next review.
- Assumption A-2: mypy strict, ruff, int base units, Clock-only time
  and typed contracts from the proven v3 gate set apply unchanged to
  every v4 milestone.
- Assumption A-3: each sweep closes with 0 open findings before its
  phase counts as delivered.

## 3. User stories

26 stories live in docs/requirements/stories.md with stable IDs
US-001 to US-026. All 26 carry MoSCoW class Must except US-015
(Should). Prioritisation uses MoSCoW because the backlog holds 26
items over 20 while the WSJF threshold counts stories above 20 only
for ranking evidence; the Must set defines the release cut line.

## 4. Acceptance criteria

30 criteria live in docs/acceptance.md as AC-001 to AC-030, each
named by its story with Given, When and Then clauses. All 30 carry
automated true. Manual-only share is 0 percent.

## 5. Non-functional requirements

5 NFRs live in docs/requirements/nfr.md: NFR-P1 (performance),
NFR-S1 (security), NFR-A1 (accessibility), NFR-I1
(internationalisation) and NFR-C1 (compliance). Each states a
numeric target and an owner. Compliance NFR-C1 is non-negotiable:
paper-only and the manipulation boundary cannot be waived.

## 6. Traceability

docs/requirements/traceability.md links all 26 stories and 5 NFRs to
their criteria and checks. Coverage target is 100 percent.

## 7. Quality bar

Every milestone meets the State-of-the-Art bar through the same
evidence: mypy --strict with 0 errors, ruff with 0 violations,
integer base-unit money with 0 float money fields, Clock-only time
with 0 wall-clock reads, typed contracts with unknown-field
rejection, fail-closed refusal on every uncertain state, replay
hash equality across reruns, make lint typecheck test audit all
exit 0, replay smoke exit 0, live refusal exit 3, gateway pytest
exit 0 and per-PR CI 100 percent green before merge. Paper-only
holds throughout.
