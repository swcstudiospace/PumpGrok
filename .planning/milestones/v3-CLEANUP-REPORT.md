# v3 cleanup report

Run: v3 closeout, 2026-11-01. Branch bot-00-chief/v3-closeout (PR 27).

## Removed from the repository

- .planning/REQUIREMENTS.md, removed with git rm after the archive. The archived copy is .planning/milestones/v3-REQUIREMENTS.md. The original stays in git history on the branch (commit c8e81b0 and its ancestors).

## Removed untracked run scratch

- .planning/pre-run-snapshot/: the run-start copy of .planning, taken before any edit and verified when created.
- .planning/state.json: written by gsd-tools during this run. gsd-tools regenerates it on next use.

## Removed worktrees created by this run

- /root/src/repos/pumpgrok-wt/bot-02-waiver: the PR 28 worktree. PR 28 merged as 9588bc0. Its branch bot-02-risk/gate-waiver-pr-27 is kept, because deleting a branch needs approval.
- /root/src/repos/pumpgrok-wt/combined-scratch2: a detached scratch merge of PRs 23 to 25 (d3c7c00). It was never pushed.

## Kept on purpose

- Branch bot-00-chief/v3-closeout: PR 27 is open.
- Branch bot-02-risk/gate-waiver-pr-27: merged; kept until deletion is approved.
- Local annotated tag v3: on the closeout commit; not pushed.
- Owner checkout /root/src/repos/pumpgrok: its own work (M tests/upgrade/test_scheduled_promotion.py and untracked .claude/) is untouched.
- Other worktrees in git worktree list: owner and other seats' work; not removed.
- Historical marker lines recorded in .planning/BACKLOG-INVENTORY.md (28 lines, all PARKED): left in place, because removing them would erase the migration record.

## Verification after cleanup

- make check: exit 0 on the closeout tree, before the documentation corrections (log /tmp/make-check-closeout.txt). It ended with "ok: 35 skills, 10 agents, 322 markdown files checked" and "PumpGrok repository structure looks healthy."
- uv run pumpgrok verify --fixture smoke-10m: exit 0, events.hash=b69c29593954129b52a8c9ab1cad390441b7b356dd482b8c7a4345bea55ad32d, verify=CONSISTENT seq=2 events=41.
- uv run pumpgrok run --mode live --once: exit 3, refusing to start.
- After the documentation corrections (MILESTONES phase 6 entry, CLAUDE.md citation, closeout record, audit correction): uv run python -m pytest tests/docs: exit 0, 44 tests, 0 failures, 0 errors; ./scripts/verify_doc_commands.sh: exit 0, pass=2 skip=9 fail=0; ./scripts/check.sh: exit 0.
