# Root cause: gsd-autonomous stall at the milestone audit step

Verified facts (read-only):
- `node /root/.agents/gsd-core/bin/gsd-tools.cjs query init.milestone-op` returns `milestone_version = v3`, `phase_count = 5`, `completed_phases = 5`.
- The workflow (`~/.agents/gsd-core/workflows/autonomous.md`, about lines 666-672) reads `.planning/v${milestone_version}-MILESTONE-AUDIT.md` and greps `^status:`.
- Before the fix, only `.planning/MILESTONE-AUDIT.md` existed and had no `status:` line, so `AUDIT_STATUS` was empty and the run went to `handle_blocker`.
- Phase review is not the stall: no phase is STATUS_DRIFT or INCOMPLETE. Phases 7-10 are COMPLETE_VERIFIED.

Fix applied in this repo: `git mv` to `.planning/v3-MILESTONE-AUDIT.md`, frontmatter `status: tech_debt`. Dry check of the workflow grep returns `tech_debt`.

Not fixed here: the global workflow was not edited (installer-managed, shared). The audit is hand-written, not produced by gsd-audit-milestone. Fixture regression test for the review step is not possible in this repo, because that step lives in ~/.agents/gsd-core.
