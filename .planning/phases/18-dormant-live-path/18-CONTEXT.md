# Phase 18: Dormant live path, amendment-gated — planning context

**Created:** 2026-11-21 · **Mode:** PLAN ONLY (no implementation, no amendment application).
**Branch:** bot-00-chief/phase-12-verification · **Correlation:** 1482cee0

## Paper-only invariant (binding on every plan)

No live adapter is registered or reachable. With overlays disabled, no env flag and no arm
record, `uv run pumpgrok run --mode live --once` exits 3 listing the nine preconditions
(C5, LIV-07). Every overlay keeps `live.enabled = false`. The desk holds no key and no
signing symbol. No plan introduces network calls, key material, or a live send path beyond
the dormant signer design. Live stays refused until a human runs the go_live runbook.

## Sources (read first, in this order)

1. `.planning/ROADMAP.md` lines 292–331 (Phase 18 goal, criteria 1–20, deliverables, plan list).
2. `.planning/REQUIREMENTS.md`: LIV-03…LIV-20, RSK-06, RSK-09, PRC-03, PRC-07.
3. `/root/src/repos/pumpgrok-parked/amendment-decisions-2026-11-17.md` (owner decisions D-1…D-13).
4. `/root/src/repos/pumpgrok-parked/amendment-exact-text-2026-11-17.md` (APPROVED 2026-11-17, not applied — agents never apply, paraphrase or merge it).
5. Ultrathink n7 synthesis, session 44628d30-b210-4d4d-a036-003ca86e0f6f (units U1–U8, waves, open decisions).

## Amendment gate

Owner approves the exact text (OD-01, already given 2026-11-17) → owner applies it in one
human-approved pull request (**plan 18-07**) → amendment-wait plans **18-03, 18-04, 18-05,
18-06, 18-08, 18-09** merge only after 18-07 merges. Plans may be *built* in their waves
before then; only the merge waits. Approval model: arm-once (D-1) — inside a human-created
arm record the desk sends without per-ticket approval, bound to (strategy id, parameter-set
hash), SOL cap ≤ 1.0, expiry ≤ 168 h. Exit/flatten sells of held positions proceed on a
latched halt (D-2), on a KILL (D-3), and on an expired or absent arm record (V4-12, A4).
No $20 increment rule (D-10); the $200 cap is the only hard cap. Zero-loss paper record ⇒
row 4 unmet, profit factor not measurable (D-11). Sends only through the signer instruction
allowlist; reads only through the Phase 13 read-only allowlist (D-12).

## Unit → plan map (ultrathink n7 U1–U8)

| Plan | Unit | Scope | Criteria | Wave | Gate |
|---|---|---|---|---|---|
| 18-01 | U1 | stop state + signer protocol | 2, 12 (protocol) | 1 | — |
| 18-02 | U2 | live event source + contract | 3, 4 | 1 | — |
| 18-03 | U3 | gate, arm, order boundary | 5, 6, 7 | 2 | amendment-wait |
| 18-04 | U6 | desk-signer service (new tree) | 10, 11, 12 | 2 | amendment-wait |
| 18-05 | U4 | signer client, registry, reconcile, shadow, mirror | 8 (registry), 13, 15, 16 | 3 | amendment-wait |
| 18-06 | U5 | doctor key check | 14 | 4 | amendment-wait |
| 18-08 | U7 | live factory, dispatch, guard tests | 8 (factory), 17 | 4 | amendment-wait |
| 18-09 | U8 | runbooks + dormant wiring | 9, 13 (dormant) | 4 | amendment-wait |
| 18-07 | — | owner amendment PR (human only) | 18, 19 | 5 | HUMAN GATE |
| 18-10 | — | closeout verification | 1 | 6 | — |
| 18-11 | — | CHANGELOG entry (JOURNAL-owned) | 20 | 7 | — |

Dependencies: 18-03/18-04 after 18-01+18-02; 18-05 after 18-03+18-04; 18-06/18-08/18-09 after
18-05; 18-07 gate merges before amendment-wait merges; 18-10 after 18-07; 18-11 last.
Every wave is file-disjoint (no file is modified by two plans in the same wave).
`registry.py` is owned by 18-05; 18-08 runs after 18-05 because of it.

## Open owner decisions (with planning defaults)

1. **Criterion 20 literal** — roadmap names `b69c29…` for Phase 18, but the 2026-11-17
   amendment moves the baseline to `1dffa784…` (PRC-03, PRC-06, V4-9). **Default: 1dffa784.**
   Owner confirms. [STALE REF — criterion 20]
2. **Criterion 18 / deliverable 5 oracle names** — roadmap/requirements name
   `tests/safety/amendment_2026_10_28_frozen.txt` and `test_constitution_amendment_2026_10_28.py`,
   both absent from the tree. **Default: keep the names, recreate the oracle for the approved
   2026-11-17 text.** Owner confirms. [STALE REF — criterion 18 oracle]
3. **Exit carve-out with no arm record ever** — approved clause 2 does not refuse exits for
   lack of a record, but no criterion tests it. **Default: exits allowed.** Add the test in 18-03.
4. **Criterion 1 paper smoke** — exits 1 in this checkout (roster tools lack operator
   authority). **Default: recorded deferral to deployment, never recorded as passed** (as
   Phases 14–16 did).

## Verified tree facts (planning baseline, fae18ca)

Absent: `services/desk-signer/`, `tests/live/`, `tests/core/test_signer_protocol.py`,
`tests/safety/test_signer_isolation.py`, `tests/safety/amendment_2026_10_28_frozen.txt`,
`tests/safety/test_constitution_amendment_2026_10_28.py`. Present: `tests/safety/test_constitution_amendment.py`,
`tests/safety/test_constitution_constants.py`, `tests/safety/amendment_2026_10_25_frozen.txt`,
`.planning/AMENDMENT-2026-10-25.md`, `src/pumpgrok/execution/live/live_gate.py`,
`src/pumpgrok/execution/live/live_adapter.py`, `contracts/changes/`, `contracts/events/*.schema.json`,
`scripts/generate-event-schemas.py`, `ci/gates/check_contracts.py`, `docs/runbooks/go_live.md`,
`docker-compose.yml`, overlays `dev/paper/live.toml`.
