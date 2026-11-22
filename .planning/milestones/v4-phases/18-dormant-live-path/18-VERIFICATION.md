---
phase: 18-dormant-live-path
verified: 2026-11-22
status: gaps_found
score: 0/11 plans executed
---

# Phase 18 Verification: Dormant live path

**Verdict:** gaps_found — Phase 18 is not executed. No Phase 18 code is on main, so none of the Phase 18 success criteria in `.planning/ROADMAP.md` (Phase 18 section) can be verified as met. This file records that honestly; it does not claim the phase passed.

## Evidence state

- Phase 18 has plans only: `18-01` through `18-11` PLANs exist under `.planning/milestones/v4-phases/18-dormant-live-path/` (plus `18-CONTEXT.md`). There are no `18-0N-SUMMARY.md` files.
- No Phase 18 code is on main:
  - no `src/pumpgrok/ledger/stop_state.py` (LIV-05 deliverable, absent),
  - no `src/pumpgrok/core/signer_protocol.py` (signer protocol deliverable, absent),
  - no `services/desk-signer/` (signer service deliverable, absent).
- Score: 0/11 plans executed.

## Gaps

### G1 — Dormant live path unbuilt (owner-accepted tech_debt)

Per `.planning/milestones/v4-MILESTONE-AUDIT.md` (G1 block, `status: tech_debt`): Phase 18 plans 18-01..18-11 were not merged; the amendment gate 18-07 is a HUMAN GATE (owner PR). The 21 Phase 18 requirements (LIV-03..LIV-20, RSK-06, RSK-09, PRC-07) have no merged evidence beyond the live-still-refused proof (`run --mode live` exits 3) and the existing `execution/live/live_gate.py` refusal lists.

### Amendment gate — 18-07 requires owner human-approved PR (OD-01)

Plan `18-07-PLAN.md` is `type: checkpoint`, `autonomous: false`: agents never apply, paraphrase, or merge the constitution amendment text. The owner must apply the approved amendment (`amendment-exact-text-2026-11-17.md`, OD-01 approval given 2026-11-17) in one human-approved PR with exactly one step-scoped G-1 waiver. Plans 18-03..18-06, 18-08 and 18-09 are amendment_wait and merge only after that PR lands. Until then live stays refused.

### G3 — Phase 18 CHANGELOG hash lines owed

Per the audit G3 block and the gap section of `.planning/milestones/v4-phases/19-observability/19-VERIFICATION.md`: CHANGELOG.md has no `Phase 18: smoke-10m events.hash before/after` or `Phase 18: trading-smoke events.hash before/after` lines. The journal seat owes all four lines (smoke-10m `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d` before/after; trading-smoke `bdcbe2d321eea3e4ff814e91434f5ffb8ab84963cea1237c2f453500f5093e54` before/after), after G1 lands — there is currently no Phase 18 tree to hash.

## Next action

`next_action: owner decides amendment text, then plans execute.`

The owner first decides/confirms the amendment text via the OD-01 human-approved PR (plan 18-07). Only after that amendment lands do the amendment_wait plans (18-03..18-06, 18-08, 18-09) and the remaining Phase 18 plans execute, after which a re-verification (and the G3 CHANGELOG lines, via the journal seat) can close this phase.
