# Phase 7 Plan 01 (DOC-01): Root CLAUDE.md — Summary

## One-liner

New root `CLAUDE.md` codebase map with the nine criterion-2 sections; every bullet cites a backticked repo path.

## Tasks completed

| Task | Commit | Files |
| ---- | ------ | ----- |
| Write root CLAUDE.md | d42bee4 | `CLAUDE.md` (new) |
| Fix four source-check statements (Main follow-up) | 5c068e3 | `CLAUDE.md` (4 lines) |

## Changed files

- `CLAUDE.md` (new, 107 lines): nine `##` sections (Purpose, Stack, Layout, Commands, Architecture, Conventions, GSD artifact, Safety, Known gaps); facts verified by grep before writing (ten seats per `ownership.yaml` + `agents/*.md`; 35 skill dirs via `ls -d skills/*/`; package `0.1.0` via `pyproject.toml`; `PUMPGROK_RPC__ENDPOINTS` env form; no `--rpc` flag; serve needs `--replay` without `--once` per `src/pumpgrok/cli.py:583-590`; price curve `getAccountInfo` vs `exec.quote` adapter route; Jupiter informational-only `QUOTE_URL`; ASSUMED curve layout; replay-vs-checkpoint path difference).

## Deviations

None from the plan — only `CLAUDE.md` touched (the plan's sole `files_modified` entry). No `scripts/verify_doc_commands.sh`, no `CHANGELOG.md`.

## Post-acceptance corrections (Main follow-up, commit 5c068e3)

1. Line 12: `skills/market-price/SKILL.md` did not exist — replaced with `skills/momentum-signals/SKILL.md` (verified present).
2. Line 38: `agents/` has no `bot-*.md` files (role names: `chief.md`, `risk.md`, …) — replaced with 'ten role files such as `agents/risk.md`'.
3. Line 63: unsourced `asyncio.Task` clause — replaced with roster-order wording citing `TICK_S = 1.0`, `src/pumpgrok/supervisor/scheduler.py:89-90`.
4. Line 96: 'runs only `--mode paper --once --replay`' was wrong (`--serve --replay` also supported) — replaced with the two-mode sentence citing `src/pumpgrok/cli.py` `_run` lines 581-596.

Acceptance greps re-run after the fix: exit 0.

## Acceptance commands (exact, run from worktree root)

```bash
test "$(grep -cE '^## (Purpose|Stack|Layout|Commands|Architecture|Conventions|GSD artifact|Safety|Known gaps)' CLAUDE.md)" -ge 9 exits 0 AND ! grep -nE '^\s*[-*] ' CLAUDE.md | grep -v '`' exits 0 (no output)
```

Verified pre-commit: heading count is 9 and the bullet-backtick grep returns no output (exit 0).

## Self-check

- `CLAUDE.md` exists at worktree root: FOUND.
- Commit `d42bee4` present in `git log`: FOUND (single-task plan, one commit plus this summary commit to follow).
