# Phase 18 verification checklist (agent-assist only)

Owner 2026-11-22 decision: agent-assist only. No agent edits the amendment text.
Phase 18 stays blocked until the owner PR merges. This file is the review guide.

## Owner action (human only)

1. Apply `amendment-exact-text-2026-11-17.md` (points A1-A9, B1-B9, C1-C4)
   in one human-approved pull request, byte-identical to the approved draft.
2. The PR includes every C1 copy (AGENTS.md, CLAUDE.md, rules/README.md,
   docs/RISK_POLICY.md), the decision record (B9), the recreated frozen
   oracle (C4), and exactly one step-scoped G-1 waiver pinned by test.
3. The owner confirms the oracle file/test names before applying
   (18-07 stale-ref note: criterion 18 names the 2026-10-28 files).

## Verify after the owner PR (agent may run, never merge)

- `uv run pytest -q tests/safety/test_constitution_amendment_2026_10_28.py tests/safety/test_constitution_amendment.py tests/safety/test_amendment_copies_complete.py`
- `python3 scripts/generate-templates.py --check`
- `uv run pytest -q ci/tests/test_no_pr_waivers.py`
- `make lint && make typecheck && make test && ./scripts/check.sh`
- `uv run pumpgrok run --mode live --once` still exits 3 unless the
  separate arming runbook step is executed by the owner.
- `uv run pumpgrok verify --fixture smoke-10m` hash unchanged:
  `b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d`.

## What stays true in the meantime

- `run --mode live` exits 3 on this tree (verified 2026-11-22). No live
  adapter is registered; no key or signing code enters the desk package.
- G1 (plans only, no code), G2 (19-08 landing pending), G3 (Phase 18
  CHANGELOG lines owed by journal) remain open per v4-MILESTONE-AUDIT.md.
