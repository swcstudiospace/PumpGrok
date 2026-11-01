# Phase 07 Plan 02 (DOC-02): AGENTS.md trim + verify_doc_commands.sh — Summary

## One-liner

Trimmed AGENTS.md from 423 to 133 lines with a CLAUDE.md pointer (no placeholders),
and added an executable offline `scripts/verify_doc_commands.sh` that RUNs finite
commands, LISTs make/serve targets without executing them, and fails closed.

## Frontmatter

- phase: 07-documentation-upgrade
- plan: 2 (DOC-02, wave 2, depends on 07-01)
- status: complete
- commits: b9046ef (AGENTS.md trim), ca337f8 (verify script)
- changed files: AGENTS.md, scripts/verify_doc_commands.sh
- acceptance: criterion 4 (AGENTS.md shorter, links CLAUDE.md, no placeholder),
  criterion 5 (`./scripts/verify_doc_commands.sh` exits 0 — to be run by orchestrator)

## What was built

### Task 1 — Trim AGENTS.md (commit b9046ef)

- Removed the generated GSD research dump (`<!-- GSD:stack-start -->` through
  `<!-- GSD:stack-end -->`, the Technology Stack / verdict / installation /
  alternatives / upstream-surface / risks / sources sections, 263 lines).
- Removed the four placeholder GSD blocks (conventions, architecture, skills,
  profile — "not yet …" / "No project skills found" content).
- Kept verbatim: title/intro, rules table, ten-seat table, before-first-edit,
  receipts, secrets, run-the-checks fence, the GSD project and workflow marker
  blocks, and the rules index.
- Added a CLAUDE.md pointer paragraph (`[CLAUDE.md](CLAUDE.md)` present).
- Result: 133 lines vs 423 on origin/main; no case-variant of "placeholder".

### Task 2 — Create scripts/verify_doc_commands.sh (commit ca337f8)

- Executable (`chmod +x`) bash script using only bash/awk/grep/sed/uv.
- Extracts fenced ```bash lines AND inline `command` spans from the Commands
  sections of CLAUDE.md (`## Commands`) and AGENTS.md (`## Run the checks`) only.
- RUN (finite, offline): `uv run pumpgrok doctor`, one-shot
  `run --mode paper --once --replay tests/fixtures/replay/smoke`; exit code
  compared to trailing `# exits N` (default 0); any undocumented nonzero fails.
- LIST-but-SKIP (never executed): `make lint|typecheck|test|audit|check`
  (each target name verified with `grep -qE "^<t>:" Makefile`), `uv sync`
  (network), `./scripts/check.sh` (whole-repo lint is the orchestrator's job;
  presence + executable bit verified), `docker compose …` (daemon).
- `run --serve` (and any `--serve` command): NEVER executed, no long-lived
  process; `--serve`/`--replay` flags verified in `uv run pumpgrok run --help`.
- Fail-closed: curl/wget/ssh or any unallowlisted command fails the script.
- Deduplicates commands named in both files; prints PASS/SKIP/FAIL lines and a
  `pass=/skip=/fail=` summary; exits 1 on any failure, 0 otherwise.

## Verification (acceptance commands for the orchestrator)

Task 1 (already exercised during execution, all green):

```bash
test "$(wc -l < AGENTS.md)" -lt "$(git show origin/main:AGENTS.md | wc -l)" \
  && grep -q "CLAUDE.md" AGENTS.md && ! grep -niE "placeholder" AGENTS.md
```

Task 2 (NOT run by the executor — running it executes pumpgrok, which is the
orchestrator's job per the assignment constraints; static `bash -n` passes):

```bash
./scripts/verify_doc_commands.sh   # must exit 0
```

## Deviations

1. Branch-namespace prescription vs assigned branch. The executor protocol
   expects worktree commits on `agent-*` branches; this repo's convention (and
   the orchestrator-assigned worktree branch) is `bot-00-chief/p7-02`.
   Committed on the assigned branch after verifying HEAD is neither detached
   nor a protected branch (`main|master|develop|trunk|release/*`). No code impact.
2. Two self-caught transcription slips in the AGENTS.md rewrite (intro line had
   gained "memecoin"; Tech-stack bullet had lost "only") were found by
   re-diffing against HEAD and restored — final diff adds only the 3-line
   CLAUDE.md pointer; all other kept lines are byte-identical to HEAD.
3. The verify script was not executed by the executor (assignment rule: no
   pumpgrok/make/test-suite runs, no long-lived processes). `bash -n` syntax
   check passes; executable bit set. First live run belongs to the orchestrator.

## Files

- Created: scripts/verify_doc_commands.sh (208 lines, mode +x)
- Modified: AGENTS.md (423 → 133 lines)
- Untouched: CHANGELOG.md (plan 07-06 owns it), rules/, src/, tests/, docs/
