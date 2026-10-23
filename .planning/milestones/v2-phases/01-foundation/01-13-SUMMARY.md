# Phase 01 Plan 13 Summary: tools/ manual ruff fixes (FOUND-002)

## One-liner
Legacy tools/ tree cleared of all non-autofixable ruff findings (UP035/RUF001/RUF002/E501/F401/T201/PLR0911/PLW2901/SIM102/SIM103) with byte-identical CLI stdout; tests/test_tools_cli.py passes unmodified (11 passed).

## Tasks

### Task 1: import modernization, unicode hyphens, line lengths — done (commit 9d586a2)
- `typing.Dict/List/Tuple` imports and all annotations (incl. nested subscripts) rewritten to builtin generics (`dict`/`list`/`tuple`) in all eight files (UP035). This also cleared the overlapping UP006 annotation sites; remaining UP045/UP017/I001 left for the orchestrator `--fix` pass.
- Removed unused `import os` in tools/paper_sim.py (F401).
- Replaced 9 en-dash (U+2013) codepoints with hyphen-minus: 8 module-docstring first lines + the `FLOOR HALTED -` marker f-string in desk_state.py write_halt (RUF001/RUF002).
- Wrapped all 14 E501 lines past col 100 (holder_check 2, jupiter_quote 5, priority_fee 5, ticket_helper 2); multi-line strings split via implicit concatenation so runtime values are unchanged.
- Verify: `ruff check --select UP035,F401,RUF001,RUF002,E501 tools/` → no issues.

### Task 2: print-to-stream conversion and control-flow bounds — done (commit 270577a)
- All 23 `print(...)` sites converted to `sys.stdout.write(... + "\n")` (T201); every file already imported `sys`, no import changes needed. Wrapped forms kept ≤100 cols.
- desk_state.py: extracted `read_command_payload()` for the four read subcommands; `main()` went from 8 returns to 5 (PLR0911). Dispatch, payloads, exit codes unchanged.
- pipeline_evidence.py: loop variable renamed to `raw_line` (PLW2901); nested `if candidates:` merged (SIM102); the merge exposed SIM103, resolved with `return not (...)` and removal of the orphaned `return True`.
- pipeline_evidence.py `payload: Dict[str, Any]` annotation (missed UP035 overlap from Task 1, a live NameError) fixed to `dict[str, Any]`.
- Verify: `ruff check --select T201,PLR0911,PLW2901,SIM102 tools/` → no issues; `pytest tests/test_tools_cli.py` → 11 passed, exit 0.

## Verification results
- `ruff check --select T201,E501,F401,RUF001,RUF002,UP035,PLR0911,PLW2901,SIM102 tools/` → exit 0.
- Residual tools/ findings: 23 total, all safe-autofixable — I001 (3), UP017 (7), UP045 (13) — for the orchestrator pass. (UP006 fully cleared as a side effect of the UP035 rewrites.)
- `pytest tests/test_tools_cli.py` → 11 passed, exit 0 (run unmodified, owned by plan 01-12).
- Byte-equivalence (old code at 9d586a2^ vs new): desk_state `status` payloads equal; pipeline_evidence `--block` output raw-byte-identical (modulo the log path arg, ends `]}\n`); ticket_helper `next` identical modulo desk path. jupiter_quote `--help` crashes identically before/after (pre-existing argparse `%`-format bug in the `(lamports for SOL)` help string, unrelated to this plan — not touched).

## Deviations / auto-fixes
- [Rule 1 - Bug] Task 1 left `payload: Dict[str, Any]` in pipeline_evidence.py:282 after removing the `Dict` import (NameError at runtime). Found by re-grep before Task 2 verify; fixed to `dict[str, Any]`. In commit 270577a.
- [Rule 1 - Bug] SIM102 merge created SIM103 (`if ...: return False; return True`); fixed with direct negated return. In commit 270577a.
- Pre-existing, out of scope: jupiter_quote `--help` ValueError (argparse `%` expansion vs `(lamports for SOL)`). Logged, not fixed (help-text change would alter bytes and is outside files_modified intent; no test covers it).

## Files
- Modified: tools/authority_check.py, tools/desk_state.py, tools/holder_check.py, tools/jupiter_quote.py, tools/paper_sim.py, tools/pipeline_evidence.py, tools/priority_fee.py, tools/ticket_helper.py
- Created: .planning/phases/01-foundation/01-13-SUMMARY.md (this file)

## Commits
- 9d586a2 fix(01-13): modernize tools imports, hyphen-minus docstrings, wrap long lines (Task 1)
- 270577a fix(01-13): stream writes and bounded control flow in tools (Task 2)

## Self-Check: PASSED
- All eight tools/*.py present and modified as committed; both commit hashes resolve in `git log`.
